from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

PROJECT_APPS = {'stores', 'catalog', 'customers', 'inventory', 'sales'}


class AdminPagesTests(TestCase):
    """Every registered project model's list and add pages load. Prices and lines are edited inline."""

    def setUp(self):
        self.client.force_login(User.objects.create_superuser('admin', 'admin@example.com', 'unused'))

    def test_list_and_add_pages_load(self):
        models = [m for m in admin.site._registry if m._meta.app_label in PROJECT_APPS]
        self.assertEqual(len(models), 13)
        for model in models:
            for page in ['changelist', 'add']:
                url = reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_{page}')
                with self.subTest(url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_animal_availability_filter(self):
        for value in ['yes', 'no']:
            response = self.client.get(reverse('admin:inventory_animal_changelist'), {'available': value})
            self.assertEqual(response.status_code, 200)
