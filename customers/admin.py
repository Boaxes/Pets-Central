from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['last_name', 'first_name', 'email', 'phone', 'home_store', 'marketing_opt_in', 'created_at']
    list_filter = ['marketing_opt_in', 'home_store__region']
    search_fields = ['first_name', 'last_name', 'email', 'phone']
    autocomplete_fields = ['home_store']
    list_select_related = ['home_store']
    date_hierarchy = 'created_at'
