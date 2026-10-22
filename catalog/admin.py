from django.contrib import admin

from .models import Brand, Category, Department, Product, ProductPrice, Species


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']
    search_fields = ['code', 'name']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'department']
    list_filter = ['department']
    search_fields = ['name', 'department__name']


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_house_brand']
    list_filter = ['is_house_brand']
    search_fields = ['name']


@admin.register(Species)
class SpeciesAdmin(admin.ModelAdmin):
    list_display = ['common_name', 'scientific_name', 'department']
    list_filter = ['department']
    search_fields = ['common_name', 'scientific_name']


class ProductPriceInline(admin.TabularInline):
    model = ProductPrice
    extra = 0
    ordering = ['-valid_from']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'category', 'brand', 'species', 'introduced_on', 'discontinued_on']
    list_filter = ['category__department', 'category', 'brand']
    search_fields = ['sku', 'name', 'brand__name']
    autocomplete_fields = ['category', 'brand', 'species']
    list_select_related = ['category__department', 'brand', 'species']
    inlines = [ProductPriceInline]
