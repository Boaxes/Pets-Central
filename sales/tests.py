from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from catalog.models import Brand, Category, Department, Product, ProductPrice, Species
from customers.models import Customer
from inventory.models import Animal, StockLevel
from stores.models import Region, Store

from .models import Sale, SaleLine
from .services import (
    InsufficientStock, LineRequest, ReturnRequest, SaleError, cancel_sale, record_return, record_sale,
)

JAN_1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
JUN_1 = datetime(2026, 6, 1, tzinfo=timezone.utc)


class SalesTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        region = Region.objects.create(code='PNW', name='Pacific Northwest')
        cls.store = Store.objects.create(
            store_code='PC-0001', name='Bellingham', region=region, address_line='1 Main St', city='Bellingham',
            state='WA', postal_code='98225', time_zone='America/Los_Angeles', opened_on=date(2020, 1, 1),
        )
        cls.other_store = Store.objects.create(
            store_code='CC/WA/017', name='Seattle', region=region, address_line='2 Pike St', city='Seattle',
            state='WA', postal_code='98101', time_zone='America/Los_Angeles', opened_on=date(2021, 1, 1),
            original_chain=Store.Chain.CRITTER_CORNER,
        )
        dogs = Department.objects.create(code='DOG', name='Dogs')
        reptiles = Department.objects.create(code='REP', name='Reptiles')
        brand = Brand.objects.create(name='Trail Hound')
        cls.kibble = Product.objects.create(
            sku='DOG-0001', name='Trail Hound Adult Kibble 30 lb', brand=brand,
            category=Category.objects.create(department=dogs, name='Dry Food'), introduced_on=date(2020, 1, 1),
        )
        # The kibble got more expensive on June 1.
        ProductPrice.objects.create(product=cls.kibble, list_price=Decimal('50.00'), unit_cost=Decimal('30.00'),
                                    valid_from=JAN_1, valid_to=JUN_1)
        ProductPrice.objects.create(product=cls.kibble, list_price=Decimal('55.00'), unit_cost=Decimal('32.00'),
                                    valid_from=JUN_1)
        gecko = Species.objects.create(department=reptiles, common_name='Leopard gecko',
                                       scientific_name='Eublepharis macularius')
        cls.gecko_product = Product.objects.create(
            sku='REP-LIVE-0001', name='Leopard gecko', species=gecko,
            category=Category.objects.create(department=reptiles, name='Live Animals'), introduced_on=date(2020, 1, 1),
        )
        ProductPrice.objects.create(product=cls.gecko_product, list_price=Decimal('79.99'),
                                    unit_cost=Decimal('25.00'), valid_from=JAN_1)
        cls.customer = Customer.objects.create(first_name='Sam', last_name='Rivera', email='Sam.Rivera@Example.com')

    def setUp(self):
        self.stock = StockLevel.objects.create(store=self.store, product=self.kibble, quantity_on_hand=10)
        self.gecko = Animal.objects.create(product=self.gecko_product, store=self.store, name='Mango',
                                           received_on=date(2026, 2, 1), born_on=date(2025, 11, 1))


class RecordSaleTests(SalesTestData):
    def test_lowers_stock_and_copies_price_and_cost(self):
        sale = record_sale(self.store, [LineRequest(self.kibble, quantity=3)], customer=self.customer,
                           sold_at=JUN_1 + timedelta(days=1))
        line = sale.lines.get()
        self.assertEqual((line.unit_price, line.unit_cost), (Decimal('55.00'), Decimal('32.00')))
        self.assertEqual(sale.total(), Decimal('165.00'))
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, 7)

    def test_uses_the_price_in_effect_when_sold(self):
        sale = record_sale(self.store, [LineRequest(self.kibble)], sold_at=datetime(2026, 3, 15, tzinfo=timezone.utc))
        self.assertEqual(sale.lines.get().unit_price, Decimal('50.00'))

    def test_not_enough_stock_saves_nothing(self):
        with self.assertRaises(InsufficientStock):
            record_sale(self.store, [LineRequest(self.gecko_product, animal=self.gecko),
                                     LineRequest(self.kibble, quantity=11)])
        self.assertFalse(Sale.objects.exists())
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, 10)
        self.assertTrue(Animal.objects.available().filter(pk=self.gecko.pk).exists())

    def test_same_product_on_two_lines_is_checked_together(self):
        with self.assertRaises(InsufficientStock):
            record_sale(self.store, [LineRequest(self.kibble, quantity=6), LineRequest(self.kibble, quantity=5)])

    def test_animal_can_be_sold_only_once(self):
        record_sale(self.store, [LineRequest(self.gecko_product, animal=self.gecko)])
        self.assertFalse(Animal.objects.available().filter(pk=self.gecko.pk).exists())
        with self.assertRaises(SaleError):
            record_sale(self.store, [LineRequest(self.gecko_product, animal=self.gecko)])

    def test_animal_must_be_at_the_selling_store(self):
        with self.assertRaises(SaleError):
            record_sale(self.other_store, [LineRequest(self.gecko_product, animal=self.gecko)])

    def test_live_animal_needs_a_specific_animal(self):
        with self.assertRaises(SaleError):
            record_sale(self.store, [LineRequest(self.gecko_product)])

    def test_with_totals_matches_total(self):
        sale = record_sale(self.store, [LineRequest(self.kibble, quantity=2, discount_amount=Decimal('5.00')),
                                        LineRequest(self.gecko_product, animal=self.gecko)])
        annotated = Sale.objects.with_totals().get(pk=sale.pk)
        self.assertEqual(annotated.net_total, sale.total())
        self.assertEqual(annotated.item_count, 3)


class CancelSaleTests(SalesTestData):
    def test_restores_stock_and_releases_the_animal(self):
        sale = record_sale(self.store, [LineRequest(self.kibble, quantity=4),
                                        LineRequest(self.gecko_product, animal=self.gecko)])
        cancel_sale(sale)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.CANCELLED)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, 10)
        self.assertTrue(Animal.objects.available().filter(pk=self.gecko.pk).exists())

    def test_cannot_cancel_twice(self):
        sale = record_sale(self.store, [LineRequest(self.kibble)])
        cancel_sale(sale)
        with self.assertRaises(SaleError):
            cancel_sale(sale)


class RecordReturnTests(SalesTestData):
    def test_refunds_price_paid_and_restocks_at_the_returning_store(self):
        sale = record_sale(self.store, [LineRequest(self.kibble, quantity=4, discount_amount=Decimal('20.00'))])
        line = sale.lines.get()
        sale_return = record_return(sale, self.other_store, [ReturnRequest(line, quantity=1)],
                                    reason='damaged')
        self.assertEqual(sale_return.lines.get().refund_amount, (line.line_total / 4).quantize(Decimal('0.01')))
        self.assertEqual(StockLevel.objects.get(store=self.other_store, product=self.kibble).quantity_on_hand, 1)

    def test_cannot_return_more_than_was_sold(self):
        sale = record_sale(self.store, [LineRequest(self.kibble, quantity=2)])
        line = sale.lines.get()
        record_return(sale, self.store, [ReturnRequest(line, quantity=2)], reason='changed_mind')
        with self.assertRaises(SaleError):
            record_return(sale, self.store, [ReturnRequest(line, quantity=1)], reason='changed_mind')

    def test_returned_animals_are_not_restocked(self):
        sale = record_sale(self.store, [LineRequest(self.gecko_product, animal=self.gecko)])
        sale_return = record_return(sale, self.store, [ReturnRequest(sale.lines.get(), quantity=1)], reason='other')
        self.assertFalse(sale_return.lines.get().restocked)
        self.assertFalse(Animal.objects.available().filter(pk=self.gecko.pk).exists())


class HistoryIsProtectedTests(SalesTestData):
    """The original Reptile Central cascaded deletes through order history. These must not."""

    def test_deleting_a_sale_keeps_the_animals_it_sold(self):
        sale = record_sale(self.store, [LineRequest(self.gecko_product, animal=self.gecko)])
        sale.delete()
        self.assertTrue(Animal.objects.filter(pk=self.gecko.pk).exists())

    def test_customer_with_sales_cannot_be_deleted(self):
        record_sale(self.store, [LineRequest(self.kibble)], customer=self.customer)
        with self.assertRaises(ProtectedError):
            self.customer.delete()

    def test_only_one_current_price_per_product(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductPrice.objects.create(product=self.kibble, list_price=Decimal('60.00'),
                                        unit_cost=Decimal('33.00'), valid_from=JUN_1 + timedelta(days=30))

    def test_animal_line_quantity_must_be_one(self):
        sale = record_sale(self.store, [LineRequest(self.kibble)])
        with self.assertRaises(IntegrityError), transaction.atomic():
            SaleLine.objects.create(sale=sale, line_number=2, product=self.gecko_product, animal=self.gecko,
                                    quantity=2, unit_price=Decimal('79.99'), unit_cost=Decimal('25.00'))
