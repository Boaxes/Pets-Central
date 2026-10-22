from zoneinfo import available_timezones

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


def validate_time_zone(value):
    if value not in available_timezones():
        raise ValidationError(f'{value!r} is not an IANA time zone name.')


class Region(models.Model):
    code = models.CharField(max_length=8, unique=True)
    name = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Store(models.Model):
    class Chain(models.TextChoices):
        PETS_CENTRAL = 'pets_central', 'Pets Central'
        # Stores bought from Critter Corner keep that chain's store code scheme.
        CRITTER_CORNER = 'critter_corner', 'Critter Corner (acquired)'

    class Format(models.TextChoices):
        STANDARD = 'standard', 'Standard'
        FLAGSHIP = 'flagship', 'Flagship'
        EXPRESS = 'express', 'Express'

    store_code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=128)
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name='stores')
    original_chain = models.CharField(max_length=32, choices=Chain, default=Chain.PETS_CENTRAL)
    store_format = models.CharField(max_length=16, choices=Format, default=Format.STANDARD)
    address_line = models.CharField(max_length=255)
    city = models.CharField(max_length=128)
    state = models.CharField(max_length=2)
    postal_code = models.CharField(max_length=10)
    time_zone = models.CharField(max_length=64, validators=[validate_time_zone])
    opened_on = models.DateField()
    # Set for stores bought from another chain: the day they joined Pets Central and started selling in this system.
    acquired_on = models.DateField(null=True, blank=True)
    closed_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['store_code']
        constraints = [
            models.CheckConstraint(
                condition=Q(closed_on__isnull=True) | Q(closed_on__gte=models.F('opened_on')),
                name='store_closes_after_opening',
            ),
            models.CheckConstraint(
                condition=Q(acquired_on__isnull=True) | Q(acquired_on__gte=models.F('opened_on')),
                name='store_acquired_after_opening',
            ),
        ]

    def __str__(self):
        return f'{self.store_code} {self.name}'


class Employee(models.Model):
    class Role(models.TextChoices):
        STORE_MANAGER = 'store_manager', 'Store manager'
        ASSISTANT_MANAGER = 'assistant_manager', 'Assistant manager'
        ASSOCIATE = 'associate', 'Sales associate'
        ANIMAL_CARE = 'animal_care', 'Animal care specialist'
        GROOMER = 'groomer', 'Groomer'

    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name='employees')
    # Staff who sign in to the admin have a user account; most employees do not.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee',
    )
    employee_number = models.CharField(max_length=16, unique=True)
    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64)
    email = models.EmailField(blank=True)
    role = models.CharField(max_length=32, choices=Role)
    hourly_rate = models.DecimalField(max_digits=6, decimal_places=2)
    hired_on = models.DateField()
    terminated_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['last_name', 'first_name']
        constraints = [
            models.CheckConstraint(condition=Q(hourly_rate__gt=0), name='employee_hourly_rate_positive'),
            models.CheckConstraint(
                condition=Q(terminated_on__isnull=True) | Q(terminated_on__gte=models.F('hired_on')),
                name='employee_terminated_after_hired',
            ),
        ]

    def __str__(self):
        return f'{self.first_name} {self.last_name}'
