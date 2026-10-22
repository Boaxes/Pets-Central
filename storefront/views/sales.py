"""The Sales page: the old app's Orders page, built on the one-transaction workflows in sales.services."""

from django import forms
from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from customers.models import Customer
from inventory.models import Animal, StockLevel
from sales.models import Sale, SaleReturn
from sales.services import LineRequest, ReturnRequest, SaleError, cancel_sale, record_return, record_sale
from stores.models import Employee

from ..forms import StoreFormMixin
from ..pages import CURRENT_PRICE, _choice_filter
from ..tables import Column, TablePage, Tab, _picker, table_view
from .access import store_required

LINE_ROWS = 6


def _sale_filters(request, rows):
    value, filters = _choice_filter(request, 'status', 'Status',
                                    [('all', 'All sales'), ('completed', 'Completed'), ('cancelled', 'Cancelled')])
    if value != 'all':
        rows = rows.filter(status=value)
    return rows, filters


def _customer_name(sale):
    return f'{sale.customer.first_name} {sale.customer.last_name}' if sale.customer_id else 'Guest'


class NewSaleForm(StoreFormMixin, forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False, empty_label='Guest checkout')
    employee = forms.ModelChoiceField(queryset=Employee.objects.none(), label='Cashier')
    animals = forms.ModelMultipleChoiceField(queryset=Animal.objects.none(), required=False,
                                             widget=forms.SelectMultiple(attrs={'size': 6}),
                                             label='Live animals sold',
                                             help_text='Each animal is a line of its own. Hold Ctrl to pick several.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(home_store=self.store).order_by(
            'last_name', 'first_name')
        self.fields['customer'].label_from_instance = lambda c: f'{c.last_name}, {c.first_name} (#{c.pk})'
        self.fields['employee'].queryset = Employee.objects.filter(
            store=self.store, terminated_on__isnull=True,
            role__in=[Employee.Role.ASSOCIATE, Employee.Role.ASSISTANT_MANAGER, Employee.Role.STORE_MANAGER],
        ).order_by('last_name')
        self.fields['animals'].queryset = (Animal.objects.available().filter(store=self.store)
                                           .select_related('product__species').order_by('product__species__common_name'))
        self.fields['animals'].label_from_instance = lambda a: a.display_name
        for i in range(LINE_ROWS):
            self.fields[f'sku_{i}'] = forms.CharField(required=False, label='SKU')
            self.fields[f'qty_{i}'] = forms.IntegerField(required=False, min_value=1, label='Quantity')

    def line_fields(self):
        return [(self[f'sku_{i}'], self[f'qty_{i}']) for i in range(LINE_ROWS)]

    def clean(self):
        cleaned = super().clean()
        lines = []
        for i in range(LINE_ROWS):
            sku = (cleaned.get(f'sku_{i}') or '').strip().upper()
            if not sku:
                continue
            stock = StockLevel.objects.filter(store=self.store, product__sku=sku).select_related('product').first()
            if stock is None:
                self.add_error(f'sku_{i}', f'{sku} is not a product this store carries.')
                continue
            lines.append(LineRequest(stock.product, quantity=cleaned.get(f'qty_{i}') or 1))
        lines += [LineRequest(a.product, animal=a) for a in cleaned.get('animals') or []]
        if not lines and not self.errors:
            raise forms.ValidationError('Add at least one product or animal.')
        cleaned['lines'] = lines
        return cleaned


def new_sale(request, page, context):
    form = NewSaleForm(request.POST or None, request=request)
    if request.method == 'POST' and form.is_valid():
        try:
            sale = record_sale(request.store, form.cleaned_data['lines'], customer=form.cleaned_data['customer'],
                               employee=form.cleaned_data['employee'])
        except SaleError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, f'Sale {sale.receipt_number} recorded: ${sale.total():,.2f}.')
            return redirect(page.url(tab='details', id=sale.pk))
    find = request.GET.get('find', '').strip()
    found = []
    if find:
        found = (StockLevel.objects.filter(store=request.store)
                 .filter(Q(product__sku__icontains=find) | Q(product__name__icontains=find))
                 .select_related('product').annotate(price=CURRENT_PRICE).order_by('product__sku')[:10])
    context.update({'form': form, 'find': find, 'found': found})
    return render(request, 'storefront/sales.html', context)


def details(request, page, context):
    selected = _picker(request, page, context)
    if selected is not None:
        context.update(_detail_context(request, selected))
    return render(request, 'storefront/sales.html', context)


def _detail_context(request, sale):
    lines = list(sale.lines.select_related('product', 'animal').order_by('line_number'))
    returned = {}
    for line in lines:
        returned[line.pk] = line.return_lines.aggregate(n=Sum('quantity'))['n'] or 0
    returns = SaleReturn.objects.filter(sale=sale).select_related('store').prefetch_related('lines__sale_line__product')
    return {
        'sale': sale,
        'customer_name': _customer_name(sale),
        'lines': [(line, returned[line.pk], line.quantity - returned[line.pk]) for line in lines],
        'returns': returns,
        'total': sale.total(),
    }


def cancel(request, page, context):
    selected = _picker(request, page, context)
    if selected is not None:
        context.update(_detail_context(request, selected))
        if request.method == 'POST':
            try:
                cancel_sale(selected)
            except SaleError as error:
                messages.error(request, str(error))
            else:
                messages.success(request, f'Sale {selected.receipt_number} cancelled; its stock and animals are back.')
            return redirect(page.url(tab='details', id=selected.pk))
    return render(request, 'storefront/sales.html', context)


def return_items(request, page, context):
    selected = _picker(request, page, context)
    if selected is not None:
        detail = _detail_context(request, selected)
        context.update(detail)
        context['reasons'] = SaleReturn.Reason.choices
        if request.method == 'POST':
            requests = []
            for line, _, remaining in detail['lines']:
                raw = request.POST.get(f'return_{line.pk}', '').strip()
                if raw.isdigit() and int(raw) > 0:
                    requests.append(ReturnRequest(line, int(raw), restock=bool(request.POST.get(f'restock_{line.pk}'))))
            try:
                if not requests:
                    raise SaleError('Enter how many of at least one line are coming back.')
                sale_return = record_return(selected, request.store, requests, reason=request.POST.get('reason'))
            except SaleError as error:
                messages.error(request, str(error))
                return redirect(page.url(tab='return', id=selected.pk, q=context.get('q', '')))
            refund = sum(line.refund_amount for line in sale_return.lines.all())
            messages.success(request, f'Return {sale_return.return_number} recorded: refund ${refund:,.2f}.')
            return redirect(page.url(tab='details', id=selected.pk))
    return render(request, 'storefront/sales.html', context)


sales_page = TablePage(
    url_name='sales', title='Sales', singular='Sale',
    tabs=[Tab('browse', 'Sales Overview'), Tab('new', 'New Sale'),
          Tab('details', 'Sale Details'), Tab('cancel', 'Cancel Sale'),
          Tab('return', 'Return Items')],
    columns=[Column('Receipt', 'receipt_number'), Column('Sold At', 'sold_at', 'datetime'),
             Column('Customer', _customer_name), Column('Cashier', lambda s: str(s.employee) if s.employee_id else ''),
             Column('Channel', lambda s: s.get_channel_display()), Column('Status', lambda s: s.get_status_display()),
             Column('Items', 'item_count', 'number'), Column('Total', 'net_total', 'money')],
    queryset=lambda request: (Sale.objects.filter(store=request.store).select_related('customer', 'employee')
                              .with_totals().order_by('-sold_at')),
    search_fields=['receipt_number', 'customer__first_name', 'customer__last_name'],
    search_hint='receipt number or customer name',
    label=lambda s: f'{s.receipt_number} · {timezone.localtime(s.sold_at):%Y-%m-%d} · {_customer_name(s)} · ${s.net_total:,.2f}'
                    f'{" · cancelled" if s.status == Sale.Status.CANCELLED else ""}',
    browse_filters=_sale_filters,
    custom_tabs={'new': new_sale, 'details': details, 'cancel': cancel, 'return': return_items},
    intro={'new': 'Ring up a sale. Prices come from the price list, stock goes down and any animal sold is '
                  'claimed, all in one transaction: if anything fails, nothing is saved.',
           'cancel': "Cancelling puts the sale's stock back and returns any animals to sale. Sales are never "
                     'deleted.',
           'return': 'Refunds are the price paid after discounts. Returned animals go to quarantine and are '
                     'never resold.'},
)


@store_required
def sales(request):
    return table_view(request, sales_page)
