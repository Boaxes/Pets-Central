from decimal import Decimal

from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce

MONEY = DecimalField(max_digits=12, decimal_places=2)
ZERO = Value(Decimal('0.00'), output_field=MONEY)

def line_total(prefix=''):
    """A sale line's amount after its discount. `prefix` reaches the lines from another model, e.g. 'lines__'."""
    return ExpressionWrapper(F(f'{prefix}quantity') * F(f'{prefix}unit_price') - F(f'{prefix}discount_amount'),
                             output_field=MONEY)


LINE_TOTAL = line_total()


class SaleQuerySet(models.QuerySet):
    def with_totals(self):
        """Totals are calculated from the lines, never stored, so they can't drift from them."""
        return self.annotate(
            net_total=Coalesce(
                Sum(line_total('lines__')),
                ZERO,
            ),
            item_count=Coalesce(Sum('lines__quantity'), 0),
        )


class Sale(models.Model):
    class Channel(models.TextChoices):
        IN_STORE = 'in_store', 'In store'
        ONLINE = 'online', 'Online (store pickup)'

    class Status(models.TextChoices):
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    receipt_number = models.CharField(max_length=32, unique=True)
    store = models.ForeignKey('stores.Store', on_delete=models.PROTECT, related_name='sales')
    # Null means a guest checkout. PROTECT keeps a customer's history from being deleted with them.
    customer = models.ForeignKey(
        'customers.Customer',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sales',
    )
    employee = models.ForeignKey(
        'stores.Employee',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sales',
    )
    channel = models.CharField(max_length=16, choices=Channel, default=Channel.IN_STORE)
    status = models.CharField(max_length=16, choices=Status, default=Status.COMPLETED)
    sold_at = models.DateTimeField()
    cancelled_at = models.DateTimeField(null=True, blank=True)
    # Code from a loyalty platform coupon, as typed at the register.
    coupon_code = models.CharField(max_length=32, blank=True)
    # When the row last changed. The warehouse loader picks up changed rows by it.
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = SaleQuerySet.as_manager()

    class Meta:
        ordering = ['-sold_at']
        indexes = [
            models.Index(fields=['store', 'sold_at'], name='sale_store_sold_at_idx'),
            models.Index(fields=['sold_at'], name='sale_sold_at_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status='completed', cancelled_at__isnull=True)
                | Q(status='cancelled', cancelled_at__isnull=False),
                name='sale_cancelled_at_matches_status',
            ),
        ]

    def __str__(self):
        return self.receipt_number

    def total(self):
        return self.lines.aggregate(total=Coalesce(Sum(LINE_TOTAL), ZERO))['total']


class SaleLine(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='lines')
    line_number = models.PositiveSmallIntegerField()
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT, related_name='sale_lines')
    # Set when the line sells a live animal. An animal can be sold only once.
    animal = models.OneToOneField(
        'inventory.Animal',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sale_line',
    )
    quantity = models.PositiveIntegerField()
    # Price and cost at the time of sale, copied from the product's price history.
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    # When the row last changed. The warehouse loader picks up changed rows by it.
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ['sale', 'line_number']
        indexes = [models.Index(fields=['product'], name='sale_line_product_idx')]
        constraints = [
            models.UniqueConstraint(fields=['sale', 'line_number'], name='sale_line_unique_number'),
            models.CheckConstraint(condition=Q(quantity__gt=0), name='sale_line_quantity_positive'),
            models.CheckConstraint(condition=Q(animal__isnull=True) | Q(quantity=1), name='sale_line_one_animal'),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name='sale_line_price_not_negative'),
            models.CheckConstraint(condition=Q(unit_cost__gte=0), name='sale_line_cost_not_negative'),
            models.CheckConstraint(
                condition=Q(discount_amount__gte=0) & Q(discount_amount__lte=F('quantity') * F('unit_price')),
                name='sale_line_discount_within_price',
            ),
        ]

    def __str__(self):
        return f'{self.sale.receipt_number} line {self.line_number}'

    @property
    def line_total(self):
        return self.quantity * self.unit_price - self.discount_amount


class SaleReturn(models.Model):
    class Reason(models.TextChoices):
        DAMAGED = 'damaged', 'Damaged or defective'
        WRONG_ITEM = 'wrong_item', 'Wrong item'
        PET_REFUSED = 'pet_refused', 'Pet would not eat or use it'
        CHANGED_MIND = 'changed_mind', 'Changed mind'
        OTHER = 'other', 'Other'

    return_number = models.CharField(max_length=32, unique=True)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='returns')
    # Items can be returned at any store, not only the one that sold them.
    store = models.ForeignKey('stores.Store', on_delete=models.PROTECT, related_name='returns')
    employee = models.ForeignKey(
        'stores.Employee',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='returns',
    )
    reason = models.CharField(max_length=16, choices=Reason)
    returned_at = models.DateTimeField()

    class Meta:
        ordering = ['-returned_at']
        indexes = [models.Index(fields=['returned_at'], name='return_returned_at_idx')]

    def __str__(self):
        return self.return_number


class SaleReturnLine(models.Model):
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name='lines')
    sale_line = models.ForeignKey(SaleLine, on_delete=models.PROTECT, related_name='return_lines')
    quantity = models.PositiveIntegerField()
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    # False when the item can't go back on the shelf, such as opened food.
    restocked = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name='return_line_quantity_positive'),
            models.CheckConstraint(condition=Q(refund_amount__gte=0), name='return_line_refund_not_negative'),
        ]

    def __str__(self):
        return f'{self.sale_return.return_number}: {self.quantity} x {self.sale_line.product.sku}'
