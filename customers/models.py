from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class Customer(models.Model):
    """A customer as staff entered them at the register or online.

    Email and phone are stored as typed. The same person can exist twice with different capitalization or
    phone formats; the warehouse cleans and matches them, not this system.
    """

    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64)
    email = models.CharField(max_length=254, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    home_store = models.ForeignKey(
        'stores.Store',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='home_customers',
    )
    marketing_opt_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    # When the row last changed. The warehouse loader picks up changed rows by it.
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(Lower('email'), name='customer_email_lower_idx'),
            models.Index(fields=['phone'], name='customer_phone_idx'),
        ]

    def __str__(self):
        return f'{self.first_name} {self.last_name}'
