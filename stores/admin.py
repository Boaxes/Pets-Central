from django.contrib import admin

from .models import Employee, Region, Store


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']
    search_fields = ['code', 'name']


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ['store_code', 'name', 'city', 'state', 'region', 'store_format', 'original_chain', 'opened_on',
                    'acquired_on', 'closed_on']
    list_filter = ['region', 'store_format', 'original_chain', 'state']
    search_fields = ['store_code', 'name', 'city']
    date_hierarchy = 'opened_on'


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_number', 'last_name', 'first_name', 'role', 'store', 'hired_on', 'terminated_on']
    list_filter = ['role', 'store__region']
    search_fields = ['employee_number', 'first_name', 'last_name', 'email', 'store__store_code']
    autocomplete_fields = ['store', 'user']
    list_select_related = ['store']
