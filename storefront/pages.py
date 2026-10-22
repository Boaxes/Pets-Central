"""The table pages. Every queryset is filtered to request.store, so a manager only ever sees their own store."""

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db.models import Count, F, OuterRef, Subquery

from catalog.models import Category, ProductPrice
from customers.models import Customer
from inventory.models import Animal, StockLevel
from stores.models import Employee

from . import forms
from .tables import Column, TablePage, Tab

CURRENT_PRICE = Subquery(ProductPrice.objects.filter(product=OuterRef('product'), valid_to__isnull=True)
                         .values('list_price')[:1])


def _choice_filter(request, name, label, choices):
    value = request.GET.get(name, choices[0][0])
    value = value if value in dict(choices) else choices[0][0]
    return value, {name: {'label': label, 'choices': choices, 'value': value}}


# Customers -----------------------------------------------------------------------------------------------------

customers = TablePage(
    url_name='customers', title='Customers', singular='Customer',
    tabs=[Tab('browse', 'Browse Customers'), Tab('create', 'Create Customer'),
          Tab('update', 'Update Customer'), Tab('delete', 'Delete Customer')],
    columns=[Column('Customer ID', 'pk', 'id'), Column('First Name', 'first_name'),
             Column('Last Name', 'last_name'), Column('Email', 'email'), Column('Phone Number', 'phone'),
             Column('Postal Code', 'postal_code'), Column('Marketing Emails', 'marketing_opt_in', 'bool'),
             Column('Customer Since', 'created_at', 'date')],
    queryset=lambda request: Customer.objects.filter(home_store=request.store).order_by('last_name', 'first_name'),
    search_fields=['first_name', 'last_name', 'email', 'phone'],
    search_hint='name, email, phone or ID',
    label=lambda c: f'{c.first_name} {c.last_name} (#{c.pk})',
    create_form=forms.CustomerCreateForm, update_form=forms.CustomerUpdateForm,
    intro={'browse': 'Customers whose home store is this store.',
           'delete': 'Customers with purchases cannot be deleted; their history is kept.'},
)


# Employees -----------------------------------------------------------------------------------------------------

def _employee_filters(request, rows):
    value, filters = _choice_filter(request, 'status', 'Status', [('current', 'Current staff'), ('all', 'All staff')])
    if value == 'current':
        rows = rows.filter(terminated_on__isnull=True)
    return rows, filters


def _next_employee_number():
    numbers = Employee.objects.filter(employee_number__startswith='E').values_list('employee_number', flat=True)
    return f'E{max((int(n[1:]) for n in numbers if n[1:].isdigit()), default=100000) + 1:06d}'


def _hire(request, form):
    employee = form.save(commit=False)
    employee.store = request.store
    employee.employee_number = _next_employee_number()
    employee.save()
    return employee


def _terminate(request, employee, form):
    if employee.terminated_on:
        raise ValidationError(f'{employee} already left on {employee.terminated_on}.')
    if employee.role == Employee.Role.STORE_MANAGER:
        raise ValidationError('Store managers are changed by corporate.')
    last_day = form.cleaned_data['terminated_on']
    if last_day < employee.hired_on:
        raise ValidationError('The last day must be after the hire date.')
    employee.terminated_on = last_day
    employee.save(update_fields=['terminated_on'])
    return f'{employee} is set to leave on {last_day}.'


employees = TablePage(
    url_name='employees', title='Employees', singular='Employee',
    tabs=[Tab('browse', 'Browse Employees'), Tab('create', 'Hire Employee'),
          Tab('update', 'Update Employee'), Tab('delete', 'Terminate Employee')],
    columns=[Column('Employee #', 'employee_number'), Column('First Name', 'first_name'),
             Column('Last Name', 'last_name'), Column('Role', lambda e: e.get_role_display()),
             Column('Hourly Rate', 'hourly_rate', 'money'), Column('Hired', 'hired_on', 'date'),
             Column('Last Day', 'terminated_on', 'date'), Column('Email', 'email')],
    queryset=lambda request: Employee.objects.filter(store=request.store).order_by('terminated_on', 'last_name'),
    search_fields=['first_name', 'last_name', 'employee_number', 'email'],
    search_hint='name or employee number',
    label=lambda e: f'{e.first_name} {e.last_name} ({e.employee_number}, {e.get_role_display()})',
    create_form=forms.EmployeeHireForm, update_form=forms.EmployeeUpdateForm,
    on_create=_hire, delete_form=forms.TerminateForm, on_delete=_terminate,
    browse_filters=_employee_filters,
    intro={'delete': 'Employees are never deleted: their sales and animal care history stays. Set their last day.'},
)


# Animals -------------------------------------------------------------------------------------------------------

def _animal_status(animal):
    if animal.removed_on:
        return f'Removed ({animal.get_removal_reason_display().lower()})'
    return 'Available' if animal.is_available else 'Sold'


def _days_in_store(animal):
    end = animal.removed_on or (animal.sale_line.sale.sold_at.date() if hasattr(animal, 'sale_line') else date.today())
    return (end - animal.received_on).days


def _animal_filters(request, rows):
    value, filters = _choice_filter(request, 'status', 'Status', [
        ('available', 'Available'), ('long', 'In store over 45 days'), ('sold', 'Sold'), ('removed', 'Removed'),
        ('all', 'All animals')])
    if value in ('available', 'long'):
        rows = rows.available()
    if value == 'long':
        # The holding policy reviews any animal in store 45 days, and moves it on at 60.
        rows = rows.filter(received_on__lte=date.today() - timedelta(days=45)).order_by('received_on')
    elif value == 'sold':
        rows = rows.filter(sale_line__isnull=False)
    elif value == 'removed':
        rows = rows.filter(removed_on__isnull=False)
    return rows, filters


def _remove_animal(request, animal, form):
    if not animal.is_available:
        raise ValidationError(f'{animal} is not in the store any more.')
    animal.removed_on = form.cleaned_data['removed_on']
    animal.removal_reason = form.cleaned_data['removal_reason']
    if animal.removed_on < animal.received_on:
        raise ValidationError('An animal cannot leave before it arrived.')
    animal.save(update_fields=['removed_on', 'removal_reason'])
    return f'{animal} removed.'


animals = TablePage(
    url_name='animals', title='Animals', singular='Animal',
    tabs=[Tab('browse', 'Browse Animals'), Tab('create', 'Receive Animal'),
          Tab('update', 'Update Animal'), Tab('delete', 'Remove Animal')],
    columns=[Column('Animal ID', 'pk', 'id'), Column('Name', 'name'),
             Column('Species', 'product__species__common_name'), Column('Sex', lambda a: a.get_sex_display()),
             Column('Born', 'born_on', 'date'), Column('Received', 'received_on', 'date'),
             Column('Days in Store', _days_in_store, 'number'), Column('Price', 'price', 'money'),
             Column('Status', _animal_status)],
    queryset=lambda request: (Animal.objects.filter(store=request.store)
                              .select_related('product__species', 'store', 'sale_line__sale')
                              .annotate(price=CURRENT_PRICE).order_by('-received_on')),
    search_fields=['name', 'product__species__common_name'],
    search_hint='name, species or ID',
    label=lambda a: f'{a.display_name} (received {a.received_on})',
    create_form=forms.AnimalReceiveForm, update_form=forms.AnimalUpdateForm,
    delete_form=forms.RemoveAnimalForm, on_delete=_remove_animal,
    browse_filters=_animal_filters,
    intro={'delete': 'For animals that died, went back to the breeder or left the chain. Sold animals leave '
                     'through a sale.'},
)


# Animal caretakers ---------------------------------------------------------------------------------------------

Caretaker = Animal.caretakers.through


def _assign(request, form):
    animal, employee = form.cleaned_data['animal'], form.cleaned_data['employee']
    if Caretaker.objects.filter(animal=animal, employee=employee).exists():
        raise ValidationError(f'{employee} already cares for this animal.')
    return Caretaker.objects.create(animal=animal, employee=employee)


caretakers = TablePage(
    url_name='caretakers', title='Animal Caretakers', singular='Assignment',
    tabs=[Tab('browse', 'Browse Assignments'), Tab('create', 'Assign Caretaker'),
          Tab('delete', 'Remove Assignment')],
    columns=[Column('Assignment ID', 'pk', 'id'), Column('Animal ID', 'animal_id', 'id'),
             Column('Animal', lambda c: c.animal.name or '-'),
             Column('Species', 'animal__product__species__common_name'),
             Column('Caretaker', lambda c: f'{c.employee.first_name} {c.employee.last_name}'),
             Column('Role', lambda c: c.employee.get_role_display()),
             Column('Animal Status', lambda c: _animal_status(c.animal))],
    queryset=lambda request: (Caretaker.objects.filter(animal__store=request.store)
                              .select_related('animal__product__species', 'animal__sale_line', 'employee')
                              .order_by('-animal__received_on', 'pk')),
    search_fields=['animal__name', 'animal__product__species__common_name', 'employee__first_name',
                   'employee__last_name'],
    search_hint='animal, species or caretaker',
    label=lambda c: f'{c.animal.display_name} → {c.employee.first_name} {c.employee.last_name}',
    create_form=forms.AssignCaretakerForm, on_create=_assign,
    intro={'browse': 'Which staff look after which animals.'},
)


# Products (this store's stock) ---------------------------------------------------------------------------------

def _stock_filters(request, rows):
    value, filters = _choice_filter(request, 'show', 'Show', [('all', 'All products'),
                                                              ('reorder', 'Needs reordering'),
                                                              ('out', 'Out of stock')])
    if value == 'reorder':
        rows = rows.filter(quantity_on_hand__lte=F('reorder_point'))
    elif value == 'out':
        rows = rows.filter(quantity_on_hand=0)
    return rows, filters


products = TablePage(
    url_name='products', title='Products', singular='Product',
    tabs=[Tab('browse', 'Browse Products'), Tab('update', 'Update Stock')],
    columns=[Column('SKU', 'product__sku'), Column('Product Name', 'product__name'),
             Column('Brand', 'product__brand__name'), Column('Category', 'product__category__name'),
             Column('Department', 'product__category__department__name'), Column('Price', 'price', 'money'),
             Column('In Stock', 'quantity_on_hand', 'number'), Column('Reorder At', 'reorder_point', 'number')],
    queryset=lambda request: (StockLevel.objects.filter(store=request.store)
                              .select_related('product__brand', 'product__category__department')
                              .annotate(price=CURRENT_PRICE).order_by('product__sku')),
    search_fields=['product__sku', 'product__name', 'product__brand__name'],
    search_hint='SKU, product or brand',
    label=lambda s: f'{s.product.sku} {s.product.name} ({s.quantity_on_hand} in stock)',
    update_form=forms.StockForm,
    browse_filters=_stock_filters,
    intro={'browse': "The products this store carries, with today's price. The catalog itself is managed by "
                     'corporate.',
           'update': 'Correct the count after a stock take, or change when to reorder.'},
)


# Product categories --------------------------------------------------------------------------------------------

categories = TablePage(
    url_name='categories', title='Product Categories', singular='Category',
    tabs=[Tab('browse', 'Browse Product Categories')],
    columns=[Column('Category ID', 'pk', 'id'), Column('Department', 'department__name'),
             Column('Category', 'name'), Column('Products', 'product_count', 'number')],
    queryset=lambda request: (Category.objects.select_related('department').annotate(product_count=Count('products'))
                              .order_by('department__name', 'name')),
    search_fields=['name', 'department__name'],
    search_hint='category or department',
)
