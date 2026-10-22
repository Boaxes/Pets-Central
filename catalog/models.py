from django.db import models
from django.db.models import Q


class Department(models.Model):
    """The kind of pet a product is for: dogs, cats, fish, birds, small animals, reptiles."""

    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Category(models.Model):
    """A kind of product within a department, such as Dog > Dry Food."""

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='categories')
    name = models.CharField(max_length=64)

    class Meta:
        ordering = ['department__name', 'name']
        verbose_name_plural = 'categories'
        constraints = [
            models.UniqueConstraint(fields=['department', 'name'], name='category_unique_per_department'),
        ]

    def __str__(self):
        return f'{self.department} > {self.name}'


class Brand(models.Model):
    name = models.CharField(max_length=128, unique=True)
    is_house_brand = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Species(models.Model):
    """Lookup table for live animals, so one species can't be spelled three ways."""

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='species')
    common_name = models.CharField(max_length=128, unique=True)
    scientific_name = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ['common_name']
        verbose_name_plural = 'species'

    def __str__(self):
        return self.common_name


class Product(models.Model):
    sku = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, null=True, blank=True, related_name='products')
    # Set only for live animals. Each animal is then tracked on its own in inventory.Animal.
    species = models.ForeignKey(Species, on_delete=models.PROTECT, null=True, blank=True, related_name='products')
    introduced_on = models.DateField()
    discontinued_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['sku']
        constraints = [
            models.CheckConstraint(
                condition=Q(discontinued_on__isnull=True) | Q(discontinued_on__gte=models.F('introduced_on')),
                name='product_discontinued_after_introduced',
            ),
        ]

    def __str__(self):
        return f'{self.sku} {self.name}'

    @property
    def is_live_animal(self):
        return self.species_id is not None


class ProductPrice(models.Model):
    """Price history. The row with no valid_to is the current price.

    Sale lines copy the price at the time of sale, so changing a price here never rewrites history.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='prices')
    list_price = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField(null=True, blank=True)
    # When the row last changed. The warehouse loader picks up changed rows by it.
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ['product', '-valid_from']
        constraints = [
            models.UniqueConstraint(
                fields=['product'],
                condition=Q(valid_to__isnull=True),
                name='one_current_price_per_product',
            ),
            models.CheckConstraint(condition=Q(list_price__gte=0), name='price_list_price_not_negative'),
            models.CheckConstraint(condition=Q(unit_cost__gte=0), name='price_unit_cost_not_negative'),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=models.F('valid_from')),
                name='price_valid_to_after_valid_from',
            ),
        ]

    def __str__(self):
        return f'{self.product.sku} {self.list_price} from {self.valid_from:%Y-%m-%d}'
