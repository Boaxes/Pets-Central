from django.contrib import admin

from .models import Sale, SaleLine, SaleReturn, SaleReturnLine


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0
    autocomplete_fields = ['product', 'animal']
    readonly_fields = ['line_total']

    @admin.display(description='Line total')
    def line_total(self, obj):
        return obj.line_total if obj.pk else '-'


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    """Sales are recorded through sales.services so stock and prices stay right; the admin is for looking."""

    list_display = ['receipt_number', 'sold_at', 'store', 'customer', 'channel', 'status', 'net_total']
    list_filter = ['status', 'channel', 'store__region']
    search_fields = ['receipt_number', 'store__store_code', 'customer__last_name', 'customer__email', 'coupon_code']
    autocomplete_fields = ['store', 'customer', 'employee']
    list_select_related = ['store', 'customer']
    date_hierarchy = 'sold_at'
    inlines = [SaleLineInline]

    def get_queryset(self, request):
        return super().get_queryset(request).with_totals()

    @admin.display(ordering='net_total', description='Total')
    def net_total(self, obj):
        return obj.net_total


class SaleReturnLineInline(admin.TabularInline):
    model = SaleReturnLine
    extra = 0
    raw_id_fields = ['sale_line']


@admin.register(SaleReturn)
class SaleReturnAdmin(admin.ModelAdmin):
    list_display = ['return_number', 'returned_at', 'sale', 'store', 'reason']
    list_filter = ['reason', 'store__region']
    search_fields = ['return_number', 'sale__receipt_number', 'store__store_code']
    autocomplete_fields = ['sale', 'store', 'employee']
    list_select_related = ['sale', 'store']
    date_hierarchy = 'returned_at'
    inlines = [SaleReturnLineInline]
