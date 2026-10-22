import sqlite3
import tempfile
from decimal import Decimal
from pathlib import Path

import pandas as pd

from django.db import connection
from django.test import SimpleTestCase, TestCase

from catalog.models import Product
from inventory.models import Animal, StockLevel
from sales.services import LineRequest, record_sale

from . import load
from .context import Context
from .reference import CITIES, CITY_COORDINATES
from .timeline import SIZES


def count(sql):
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchone()[0]


class ReferenceTests(SimpleTestCase):
    def test_every_city_has_map_coordinates(self):
        self.assertEqual({(c.name, c.state) for c in CITIES}, set(CITY_COORDINATES))


class GeneratedDataTests(TestCase):
    """Generates the tiny dataset once and checks that the history is consistent with itself."""

    @classmethod
    def setUpTestData(cls):
        ctx = Context(SIZES['tiny'], seed=7)
        ctx.log = lambda message: None
        cls.output = Path(tempfile.mkdtemp())
        cls.summary = load.generate(ctx, output_dir=cls.output)

    def assertNone(self, sql):
        self.assertEqual(count(sql), 0, sql)

    def test_sizes_are_close_to_target(self):
        self.assertEqual(self.summary['stores'], 6)
        self.assertGreater(self.summary['sale_lines'], 10_000)
        self.assertLess(self.summary['sale_lines'], 22_000)

    def test_lines_use_the_price_in_effect_when_sold(self):
        self.assertNone('''
            SELECT count(*) FROM sales_saleline l
            JOIN sales_sale s ON s.id = l.sale_id
            JOIN catalog_productprice p ON p.product_id = l.product_id
             AND p.valid_from <= s.sold_at AND (p.valid_to IS NULL OR p.valid_to > s.sold_at)
            WHERE p.list_price <> l.unit_price OR p.unit_cost <> l.unit_cost''')
        self.assertNone('''
            SELECT count(*) FROM sales_saleline l JOIN sales_sale s ON s.id = l.sale_id
            WHERE NOT EXISTS (SELECT 1 FROM catalog_productprice p WHERE p.product_id = l.product_id
                              AND p.valid_from <= s.sold_at AND (p.valid_to IS NULL OR p.valid_to > s.sold_at))''')

    def test_products_are_sold_only_while_on_the_shelf(self):
        self.assertNone('''
            SELECT count(*) FROM sales_saleline l
            JOIN sales_sale s ON s.id = l.sale_id
            JOIN stores_store st ON st.id = s.store_id
            JOIN catalog_product p ON p.id = l.product_id
            WHERE (s.sold_at AT TIME ZONE st.time_zone)::date < p.introduced_on
               OR (s.sold_at AT TIME ZONE st.time_zone)::date > p.discontinued_on''')

    def test_sales_happen_only_while_a_store_is_part_of_the_chain(self):
        self.assertNone('''
            SELECT count(*) FROM sales_sale s JOIN stores_store st ON st.id = s.store_id
            WHERE (s.sold_at AT TIME ZONE st.time_zone)::date < GREATEST(st.opened_on, COALESCE(st.acquired_on, st.opened_on))
               OR (s.sold_at AT TIME ZONE st.time_zone)::date > st.closed_on''')

    def test_stores_are_closed_on_christmas(self):
        self.assertNone('''
            SELECT count(*) FROM sales_sale s JOIN stores_store st ON st.id = s.store_id
            WHERE to_char(s.sold_at AT TIME ZONE st.time_zone, 'MM-DD') = '12-25' ''')

    def test_customers_exist_before_they_buy(self):
        self.assertNone('''
            SELECT count(*) FROM sales_sale s JOIN customers_customer c ON c.id = s.customer_id
            WHERE s.sold_at < c.created_at''')

    def test_cashiers_work_at_the_store(self):
        self.assertNone('''
            SELECT count(*) FROM sales_sale s JOIN stores_employee e ON e.id = s.employee_id
            WHERE e.store_id <> s.store_id''')

    def test_animals_are_sold_where_they_live_after_they_arrive(self):
        self.assertNone('''
            SELECT count(*) FROM sales_saleline l
            JOIN sales_sale s ON s.id = l.sale_id
            JOIN inventory_animal a ON a.id = l.animal_id
            WHERE a.store_id <> s.store_id OR a.received_on > s.sold_at::date OR a.product_id <> l.product_id''')
        self.assertNone('''
            SELECT count(*) FROM sales_saleline l JOIN catalog_product p ON p.id = l.product_id
            JOIN sales_sale s ON s.id = l.sale_id
            WHERE p.species_id IS NOT NULL AND s.status = 'completed' AND l.animal_id IS NULL''')
        self.assertGreater(Animal.objects.available().count(), 0)

    def test_returns_follow_their_sale(self):
        self.assertNone('''
            SELECT count(*) FROM sales_salereturn r JOIN sales_sale s ON s.id = r.sale_id
            WHERE r.returned_at < s.sold_at OR s.status <> 'completed' ''')
        self.assertNone('''
            SELECT count(*) FROM sales_salereturnline rl JOIN sales_saleline l ON l.id = rl.sale_line_id
            WHERE rl.quantity > l.quantity''')

    def test_discounts_only_come_with_a_coupon(self):
        self.assertNone('''
            SELECT count(*) FROM sales_saleline l JOIN sales_sale s ON s.id = l.sale_id
            WHERE l.discount_amount > 0 AND s.coupon_code = '' ''')
        self.assertGreater(count("SELECT count(*) FROM sales_sale WHERE coupon_code <> ''"), 0)

    def test_the_planned_mess_is_there(self):
        self.assertGreater(count("SELECT count(*) FROM sales_sale WHERE customer_id IS NULL"), 0)
        self.assertGreater(count("SELECT count(*) FROM sales_sale WHERE status = 'cancelled'"), 0)
        self.assertGreater(count("SELECT count(*) FROM stores_store WHERE store_code LIKE 'CC/%'"), 0)
        self.assertGreater(count('''
            SELECT count(*) FROM (SELECT lower(trim(email)) FROM customers_customer WHERE email <> ''
                                  GROUP BY 1 HAVING count(*) > 1) d'''), 0)
        self.assertGreater(count("SELECT count(DISTINCT length(phone)) FROM customers_customer WHERE phone <> ''"), 2)

    def test_the_app_keeps_working_on_generated_data(self):
        stock = StockLevel.objects.filter(quantity_on_hand__gte=1).select_related('store', 'product').first()
        before = stock.quantity_on_hand
        sale = record_sale(stock.store, [LineRequest(stock.product)])
        stock.refresh_from_db()
        self.assertEqual(stock.quantity_on_hand, before - 1)
        self.assertGreater(sale.total(), Decimal('0'))
        self.assertTrue(Product.objects.filter(pk=stock.product_id).exists())


    def loyalty(self, sql):
        with sqlite3.connect(self.output / 'loyalty.sqlite3') as db:
            return db.execute(sql).fetchone()

    def test_every_coupon_sale_is_a_redemption_with_the_same_totals(self):
        store = count("""SELECT count(*) FROM sales_sale WHERE coupon_code <> ''""")
        redemptions, voided = self.loyalty("SELECT count(*), sum(status = 'voided') FROM coupon_redemptions")
        self.assertEqual(redemptions, store)
        self.assertEqual(voided, count("SELECT count(*) FROM sales_sale WHERE coupon_code <> '' AND status = 'cancelled'"))
        with connection.cursor() as cursor:
            cursor.execute("""SELECT sum(l.quantity * l.unit_price - l.discount_amount) FROM sales_saleline l
                              JOIN sales_sale s ON s.id = l.sale_id WHERE s.coupon_code <> ''""")
            store_total = cursor.fetchone()[0]
        self.assertAlmostEqual(float(store_total), self.loyalty('SELECT sum(order_total) FROM coupon_redemptions')[0],
                               places=2)

    def test_truth_file_points_at_real_customers_who_mostly_share_an_email(self):
        truth = pd.read_csv(self.output / 'loyalty_member_truth.csv')
        customer_ids = set(truth.customer_id)
        self.assertEqual(count(f"SELECT count(*) FROM customers_customer WHERE id IN ({','.join(map(str, customer_ids))})"),
                         len(customer_ids))
        with sqlite3.connect(self.output / 'loyalty.sqlite3') as db:
            members = pd.read_sql('SELECT member_id, email FROM members', db)
        with connection.cursor() as cursor:
            cursor.execute('SELECT id, lower(trim(email)) FROM customers_customer')
            emails = dict(cursor.fetchall())
        pairs = truth.merge(members, on='member_id')
        same = (pairs.customer_id.map(emails).str.replace('.exmaple', '.example') == pairs.email).mean()
        self.assertGreater(same, 0.6)  # Most share an address once normalized; matching must handle the rest.
        self.assertLess(same, 0.95)

    def test_points_never_go_negative_and_late_rows_exist(self):
        self.assertEqual(self.loyalty('SELECT count(*) FROM members WHERE points_balance < 0')[0], 0)
        late = self.loyalty("""SELECT count(*) FROM email_events
                               WHERE julianday(recorded_at) - julianday(sent_at) > 1.5""")[0]
        self.assertGreater(late, 0)
