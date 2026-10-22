from django.contrib import admin

from .models import Animal, StockLevel


@admin.register(StockLevel)
class StockLevelAdmin(admin.ModelAdmin):
    list_display = ['store', 'product', 'quantity_on_hand', 'reorder_point', 'needs_reorder']
    list_filter = ['store__region', 'product__category__department']
    search_fields = ['store__store_code', 'product__sku', 'product__name']
    autocomplete_fields = ['store', 'product']
    list_select_related = ['store', 'product']

    @admin.display(boolean=True)
    def needs_reorder(self, obj):
        return obj.needs_reorder


class AvailableFilter(admin.SimpleListFilter):
    title = 'availability'
    parameter_name = 'available'

    def lookups(self, request, model_admin):
        return [('yes', 'Available'), ('no', 'Sold or removed')]

    def queryset(self, request, queryset):
        available = queryset.available()
        if self.value() == 'yes':
            return available
        if self.value() == 'no':
            return queryset.exclude(pk__in=available.values('pk'))
        return queryset


@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'product', 'sex', 'born_on', 'received_on', 'is_available']
    list_filter = [AvailableFilter, 'product__species__department', 'sex', 'removal_reason']
    search_fields = ['name', 'product__species__common_name', 'store__store_code']
    autocomplete_fields = ['product', 'store', 'caretakers']
    list_select_related = ['product__species', 'store', 'sale_line']

    @admin.display(boolean=True)
    def is_available(self, obj):
        return obj.is_available
