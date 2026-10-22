from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class StockLevel(models.Model):
    """How many units of a regular product a store has. Live animals are counted in Animal instead."""

    store = models.ForeignKey('stores.Store', on_delete=models.PROTECT, related_name='stock_levels')
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT, related_name='stock_levels')
    quantity_on_hand = models.PositiveIntegerField(default=0)
    reorder_point = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['store', 'product']
        constraints = [
            models.UniqueConstraint(fields=['store', 'product'], name='stock_level_unique_store_product'),
        ]

    def __str__(self):
        return f'{self.store.store_code} {self.product.sku}: {self.quantity_on_hand}'

    def clean(self):
        if self.product_id and self.product.is_live_animal:
            raise ValidationError({'product': 'Live animals are tracked one by one as Animals, not as stock.'})

    @property
    def needs_reorder(self):
        return self.quantity_on_hand <= self.reorder_point


class AnimalQuerySet(models.QuerySet):
    def available(self):
        """Animals still in a store: not sold and not removed. Animal.is_available is the same rule for one animal."""
        return self.filter(sale_line__isnull=True, removed_on__isnull=True)


class Animal(models.Model):
    class Sex(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'
        UNKNOWN = 'unknown', 'Unknown'

    class RemovalReason(models.TextChoices):
        DECEASED = 'deceased', 'Deceased'
        RETURNED_TO_BREEDER = 'returned_to_breeder', 'Returned to breeder'
        TRANSFERRED_OUT = 'transferred_out', 'Transferred out of the chain'

    # The species comes from the product, so it is never stored twice.
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        related_name='animals',
        limit_choices_to={'species__isnull': False},
    )
    store = models.ForeignKey('stores.Store', on_delete=models.PROTECT, related_name='animals')
    caretakers = models.ManyToManyField('stores.Employee', blank=True, related_name='animals_in_care')
    name = models.CharField(max_length=64, blank=True)
    sex = models.CharField(max_length=8, choices=Sex, default=Sex.UNKNOWN)
    # A date, not an age, so it never goes stale.
    born_on = models.DateField(null=True, blank=True)
    received_on = models.DateField()
    removed_on = models.DateField(null=True, blank=True)
    removal_reason = models.CharField(max_length=32, choices=RemovalReason, blank=True)
    # When the row last changed. The warehouse loader picks up changed rows by it.
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = AnimalQuerySet.as_manager()

    class Meta:
        ordering = ['store', 'received_on']
        constraints = [
            models.CheckConstraint(
                condition=Q(removed_on__isnull=True, removal_reason='')
                | Q(removed_on__isnull=False) & ~Q(removal_reason=''),
                name='animal_removal_date_and_reason_together',
            ),
            models.CheckConstraint(
                condition=Q(born_on__isnull=True) | Q(born_on__lte=models.F('received_on')),
                name='animal_born_before_received',
            ),
        ]

    def __str__(self):
        return f'{self.display_name} ({self.store.store_code})'

    @property
    def display_name(self):
        """The species and the animal's name, or its ID when it has none: "Ball python Monty", "Betta fish #812"."""
        return f'{self.product.species.common_name} {self.name or f"#{self.pk}"}'

    def clean(self):
        if self.product_id and not self.product.is_live_animal:
            raise ValidationError({'product': 'Choose a live animal product.'})

    @property
    def is_available(self):
        return self.removed_on is None and not hasattr(self, 'sale_line')
