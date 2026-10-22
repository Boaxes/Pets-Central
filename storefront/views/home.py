from datetime import date, timedelta

from django.db.models import Count, F, Max, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import render

from customers.models import Customer
from inventory.models import Animal, StockLevel
from sales.models import LINE_TOTAL, Sale, SaleLine
from stores.models import Employee

from ..charts import bar_chart, column_chart
from .access import store_required

@store_required
def home(request):
    """A store manager's start page: the numbers that matter and what needs attention, for this store only."""
    store = request.store
    sales = Sale.objects.filter(store=store, status=Sale.Status.COMPLETED)
    lines = SaleLine.objects.filter(sale__store=store, sale__status=Sale.Status.COMPLETED)
    # The data's "now" is the store's latest sale, so recent figures count back from it.
    latest = sales.aggregate(latest=Max('sold_at'))['latest']
    since = latest - timedelta(days=30) if latest else None
    stock = StockLevel.objects.filter(store=store)
    available = Animal.objects.available().filter(store=store)

    # Months follow the store's own clock, so a late-evening sale on the 30th counts in that month.
    months = list(lines.annotate(month=TruncMonth('sale__sold_at'))
                  .values('month').annotate(sales=Count('sale', distinct=True), revenue=Sum(LINE_TOTAL)).order_by('month'))
    departments = []
    if since:
        departments = (lines.filter(sale__sold_at__gt=since)
                       .values(name=F('product__category__department__name'))
                       .annotate(revenue=Sum(LINE_TOTAL)).order_by('-revenue'))

    revenue_30 = (lines.filter(sale__sold_at__gt=since).aggregate(t=Sum(LINE_TOTAL))['t'] or 0) if since else 0
    revenue_prior = (lines.filter(sale__sold_at__gt=since - timedelta(days=30), sale__sold_at__lte=since)
                     .aggregate(t=Sum(LINE_TOTAL))['t'] or 0) if since else 0
    sales_30 = sales.filter(sold_at__gt=since).count() if since else 0
    long_stay = available.filter(received_on__lte=date.today() - timedelta(days=45)).count()
    available_count = available.count()
    stocked = stock.count()
    out_of_stock = stock.filter(quantity_on_hand=0).count()
    low = stock.filter(quantity_on_hand__lte=F('reorder_point')).count()

    context = {
        'latest': latest,
        'stats': [
            ('Revenue, last 30 days', f'${revenue_30:,.0f}', _change(revenue_30, revenue_prior)),
            ('Sales, last 30 days', f'{sales_30:,}', None),
            ('Average sale', f'${revenue_30 / sales_30:,.2f}' if sales_30 else '-', 'last 30 days'),
            ('Animals available', f'{available_count:,}', f'{long_stay} here over 45 days' if long_stay else None),
            ('Home-store customers', f'{Customer.objects.filter(home_store=store).count():,}', None),
            ('Current staff', f'{Employee.objects.filter(store=store, terminated_on__isnull=True).count():,}', None),
        ],
        'attention': [
            (out_of_stock, 'products out of stock', _share(out_of_stock, stocked), '/products/?show=out'),
            (low, 'products at or below their reorder point', _share(low, stocked), '/products/?show=reorder'),
            (long_stay, 'animals here over 45 days', _share(long_stay, available_count, 'available animals'),
             '/animals/?status=long'),
        ],
        'revenue_chart': column_chart([(m['month'].strftime('%b %y'), float(m['revenue'])) for m in months],
                                      width=900, height=230, label_every=3),
        'department_chart': bar_chart([(d['name'], float(d['revenue'])) for d in departments], width=400,
                                      label_width=105),
        'recent': sales.select_related('customer').with_totals().order_by('-sold_at')[:8],
    }
    return render(request, 'storefront/home.html', context)


def _change(now, before):
    """'up 4% on the prior 30 days', or None when there's nothing to compare with."""
    if not before:
        return None
    percent = (now - before) / before * 100
    return f"{'up' if percent >= 0 else 'down'} {abs(percent):.0f}% on the prior 30 days"


def _share(count, total, of='stocked products'):
    """'0.9% of 13,732 stocked products'. Shares of 10% or more are rounded to whole percents."""
    if not total:
        return None
    share = count / total
    percent = f'{share:.1%}' if share < 0.1 else f'{share:.0%}'
    return f'{percent} of {total:,} {of}'
