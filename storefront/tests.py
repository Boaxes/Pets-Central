from datetime import date, datetime, timezone
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Brand, Category, Department, Product, ProductPrice, Species
from customers.models import Customer
from inventory.models import Animal, StockLevel
from policies.models import Policy
from sales.models import Sale
from stores.models import Employee, Region, Store

from .scoping import CORPORATE_GROUP

PAGES = ['home', 'sales', 'customers', 'animals', 'employees', 'caretakers', 'products', 'categories', 'policies']


class StoreAppTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        region = Region.objects.create(code='PA', name='Pacific')

        def store(code, name, state, tz):
            return Store.objects.create(store_code=code, name=name, region=region, address_line='1 Main St',
                                        city=name, state=state, postal_code='00000', time_zone=tz,
                                        opened_on=date(2020, 1, 1))

        cls.seattle = store('PC-0001', 'Seattle', 'WA', 'America/Los_Angeles')
        cls.fresno = store('PC-0002', 'Fresno', 'CA', 'America/Los_Angeles')

        def employee(store, number, first, role):
            return Employee.objects.create(store=store, employee_number=number, first_name=first, last_name='Lee',
                                           role=role, hourly_rate=Decimal('20.00'), hired_on=date(2021, 1, 1))

        cls.seattle_manager = employee(cls.seattle, 'E000001', 'Morgan', Employee.Role.STORE_MANAGER)
        cls.fresno_manager = employee(cls.fresno, 'E000002', 'Riley', Employee.Role.STORE_MANAGER)
        cls.cashier = employee(cls.seattle, 'E000003', 'Casey', Employee.Role.ASSOCIATE)

        cls.user = User.objects.create_user('morgan')
        cls.user.groups.add(Group.objects.create(name='Store Managers'))
        cls.seattle_manager.user = cls.user
        cls.seattle_manager.save()

        cls.seattle_customer = Customer.objects.create(first_name='Sam', last_name='Rivera', home_store=cls.seattle)
        cls.fresno_customer = Customer.objects.create(first_name='Alex', last_name='Fresnoite', home_store=cls.fresno)

        dogs = Department.objects.create(code='DOG', name='Dogs')
        reptiles = Department.objects.create(code='REP', name='Reptiles')
        cls.kibble = Product.objects.create(sku='DOG-00001', name='Trail Hound Kibble, 30 lb',
                                            category=Category.objects.create(department=dogs, name='Dry Food'),
                                            brand=Brand.objects.create(name='Trail Hound'),
                                            introduced_on=date(2020, 1, 1))
        gecko = Product.objects.create(sku='REP-LIVE-001', name='Leopard gecko',
                                       species=Species.objects.create(department=reptiles, common_name='Leopard gecko'),
                                       category=Category.objects.create(department=reptiles, name='Live Reptiles'),
                                       introduced_on=date(2020, 1, 1))
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        ProductPrice.objects.create(product=cls.kibble, list_price=Decimal('50.00'), unit_cost=Decimal('30.00'),
                                    valid_from=start)
        ProductPrice.objects.create(product=gecko, list_price=Decimal('79.99'), unit_cost=Decimal('25.00'),
                                    valid_from=start)
        StockLevel.objects.create(store=cls.seattle, product=cls.kibble, quantity_on_hand=10, reorder_point=2)
        StockLevel.objects.create(store=cls.fresno, product=cls.kibble, quantity_on_hand=10, reorder_point=2)
        cls.seattle_gecko = Animal.objects.create(product=gecko, store=cls.seattle, name='Mango',
                                                  received_on=date(2026, 9, 1))
        cls.fresno_gecko = Animal.objects.create(product=gecko, store=cls.fresno, name='Kiwi',
                                                 received_on=date(2026, 9, 1))

        def policy(slug, states=''):
            return Policy.objects.create(slug=slug, title=slug.title(), category='staffing', version='1',
                                         effective_on=date(2026, 1, 1), status='published', owner='People',
                                         applies_to_states=states, summary='s', body='## 1. Rule\n\nText.')

        policy('scheduling')
        policy('california-overtime', 'CA')
        policy('pnw-scheduling', 'OR,WA')

    def setUp(self):
        self.client.force_login(self.user)


class SignInTests(StoreAppTestData):
    def test_pages_need_sign_in(self):
        self.client.logout()
        for name in PAGES:
            response = self.client.get(reverse(name))
            self.assertRedirects(response, f"{reverse('login')}?next={reverse(name)}", msg_prefix=name)

    def test_every_page_loads_for_a_manager(self):
        for name in PAGES:
            for tab in ['', 'create', 'update', 'delete', 'new', 'details', 'cancel', 'return']:
                with self.subTest(page=name, tab=tab):
                    self.assertEqual(self.client.get(reverse(name), {'tab': tab}).status_code, 200)

    @override_settings(DEMO_SIGN_IN=True, DEMO_PASSWORD='demo-pass')
    def test_demo_map_leads_to_a_prefilled_sign_in(self):
        self.client.logout()
        page = self.client.get(reverse('demo_sign_in'))
        self.assertContains(page, 'PC-0002 Fresno')
        self.assertContains(page, '"lat":')
        response = self.client.post(reverse('demo_sign_in'), {'store': self.fresno.pk})
        self.fresno_manager.refresh_from_db()
        user = self.fresno_manager.user
        self.assertTrue(user.check_password('demo-pass'))
        # Not signed in yet: the sign-in form arrives with the manager's username and the demo password filled in.
        self.assertRedirects(response, f"{reverse('login')}?username={user.username}")
        login = self.client.get(response['Location'])
        self.assertContains(login, f'value="{user.username}"')
        self.assertContains(login, 'value="demo-pass"')
        self.assertContains(login, 'manager of PC-0002 Fresno')
        self.client.post(response['Location'], {'username': user.username, 'password': 'demo-pass'})
        self.assertContains(self.client.get(reverse('home')), 'PC-0002')

    @override_settings(DEMO_SIGN_IN=False, DEMO_PASSWORD='demo-pass')
    def test_login_form_is_never_prefilled_outside_the_demo(self):
        self.client.logout()
        self.assertNotContains(self.client.get(reverse('login'), {'username': 'morgan'}), 'demo-pass')

    def test_a_user_without_a_store_is_refused(self):
        self.client.force_login(User.objects.create_user('no-store'))
        self.assertEqual(self.client.get(reverse('home')).status_code, 403)

    @override_settings(DEMO_SIGN_IN=False, DEMO_PASSWORD='demo-pass')
    def test_demo_sign_in_is_off_unless_turned_on(self):
        self.assertEqual(self.client.get(reverse('demo_sign_in')).status_code, 404)


class StoreScopingTests(StoreAppTestData):
    """A manager sees and changes only their own store's records, whatever the URL says."""

    def test_browse_shows_only_this_stores_customers(self):
        response = self.client.get(reverse('customers'))
        self.assertContains(response, 'Rivera')
        self.assertNotContains(response, 'Fresnoite')

    def test_another_stores_record_cannot_be_opened_by_id(self):
        for name, obj in [('customers', self.fresno_customer), ('animals', self.fresno_gecko)]:
            response = self.client.get(reverse(name), {'tab': 'update', 'id': obj.pk})
            self.assertIsNone(response.context['selected'], name)

    def test_another_stores_record_cannot_be_changed_by_posting(self):
        self.client.post(f"{reverse('customers')}?tab=update&id={self.fresno_customer.pk}",
                         {'email': 'stolen@example.com', 'phone': '', 'postal_code': ''})
        self.fresno_customer.refresh_from_db()
        self.assertEqual(self.fresno_customer.email, '')

    def test_search_does_not_reach_other_stores(self):
        response = self.client.get(reverse('animals'), {'tab': 'browse', 'status': 'all', 'q': 'Kiwi'})
        self.assertEqual(response.context['rows'], [])

    def test_managers_cannot_switch_stores(self):
        response = self.client.post(reverse('switch_store'), {'store': self.fresno.pk})
        self.assertEqual(response.status_code, 404)

    def test_corporate_users_can_switch_stores(self):
        self.user.groups.add(Group.objects.create(name=CORPORATE_GROUP))
        self.client.post(reverse('switch_store'), {'store': self.fresno.pk})
        self.assertContains(self.client.get(reverse('customers')), 'Fresnoite')

    def test_policies_are_filtered_to_the_stores_state(self):
        response = self.client.get(reverse('policies'))
        self.assertContains(response, 'Scheduling')
        self.assertContains(response, 'Pnw-Scheduling')
        self.assertNotContains(response, 'California-Overtime')
        self.assertEqual(self.client.get(reverse('policy', args=['california-overtime'])).status_code, 404)


class WorkflowTests(StoreAppTestData):
    def test_new_sale_records_the_sale_and_lowers_stock(self):
        response = self.client.post(f"{reverse('sales')}?tab=new", {
            'customer': self.seattle_customer.pk, 'employee': self.cashier.pk,
            'sku_0': 'dog-00001', 'qty_0': '2', 'animals': [self.seattle_gecko.pk],
        })
        sale = Sale.objects.get()
        self.assertRedirects(response, f"{reverse('sales')}?tab=details&id={sale.pk}")
        self.assertEqual(sale.total(), Decimal('179.99'))
        self.assertEqual(StockLevel.objects.get(store=self.seattle).quantity_on_hand, 8)
        self.assertFalse(Animal.objects.available().filter(pk=self.seattle_gecko.pk).exists())

    def test_new_sale_refuses_another_stores_animal(self):
        self.client.post(f"{reverse('sales')}?tab=new", {'employee': self.cashier.pk,
                                                       'animals': [self.fresno_gecko.pk]})
        self.assertFalse(Sale.objects.exists())

    def test_customers_with_sales_cannot_be_deleted(self):
        self.client.post(f"{reverse('sales')}?tab=new", {'customer': self.seattle_customer.pk,
                                                       'employee': self.cashier.pk, 'sku_0': 'DOG-00001'})
        self.client.post(f"{reverse('customers')}?tab=delete&id={self.seattle_customer.pk}")
        self.assertTrue(Customer.objects.filter(pk=self.seattle_customer.pk).exists())

    def test_terminating_keeps_the_employee(self):
        self.client.post(f"{reverse('employees')}?tab=delete&id={self.cashier.pk}", {'terminated_on': '2026-10-31'})
        self.cashier.refresh_from_db()
        self.assertEqual(self.cashier.terminated_on, date(2026, 10, 31))
