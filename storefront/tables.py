"""A small framework for table pages with Browse / Create / Update / Delete tabs, like the original app's ui_framework.

A TablePage describes one table: its store-scoped rows, the columns to show, how to search it, and the forms for
each tab. table_view() renders any TablePage. Pages that need more (Sales) add their own tabs on top.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

PAGE_SIZES = [10, 25, 50, 100]
PICKER_LIMIT = 12


@dataclass
class Column:
    label: str
    value: str | Callable[[Any], Any]
    kind: str = 'text'  # text, id, number, money, date, datetime, bool

    def cell(self, obj):
        raw = self.value(obj) if callable(self.value) else _attr(obj, self.value)
        if raw is None or raw == '':
            return ''
        if self.kind == 'money':
            return f'${Decimal(raw):,.2f}'
        if self.kind == 'number':
            return f'{raw:,}'
        if self.kind == 'bool':
            return 'Yes' if raw else 'No'
        if self.kind == 'datetime' and isinstance(raw, datetime):
            return timezone.localtime(raw).strftime('%Y-%m-%d %H:%M')
        if self.kind == 'date' and isinstance(raw, (date, datetime)):
            return raw.strftime('%Y-%m-%d')
        return raw

    @property
    def numeric(self):
        return self.kind in ('id', 'number', 'money')


def _attr(obj, path):
    for part in path.split('__'):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


@dataclass
class Tab:
    key: str  # browse, create, update, delete, or a key in TablePage.custom_tabs
    label: str


@dataclass
class TablePage:
    url_name: str
    title: str
    singular: str
    tabs: list[Tab]
    columns: list[Column]
    queryset: Callable  # (request) -> QuerySet, already filtered to request.store
    search_fields: list[str] = field(default_factory=list)
    search_hint: str = ''
    label: Callable[[Any], str] = str
    create_form: type | None = None
    update_form: type | None = None
    # (request, form) -> object. Default: form.save().
    on_create: Callable | None = None
    # (request, object) -> message. Default: delete it. Raise ValidationError to refuse with a message.
    on_delete: Callable | None = None
    delete_form: type | None = None
    browse_filters: Callable | None = None  # (request, queryset) -> (queryset, filter context)
    intro: dict = field(default_factory=dict)  # tab key -> sentence shown above the tab
    custom_tabs: dict = field(default_factory=dict)  # tab key -> view(request, page, context) -> response

    def search(self, queryset, text):
        if not text:
            return queryset
        query = Q()
        for name in self.search_fields:
            query |= Q(**{f'{name}__icontains': text})
        if text.isdigit():
            query |= Q(pk=int(text))
        return queryset.filter(query)

    def url(self, **params):
        query = '&'.join(f'{k}={v}' for k, v in params.items() if v not in (None, ''))
        return reverse(self.url_name) + (f'?{query}' if query else '')


def table_view(request, page: TablePage):
    tab = next((t for t in page.tabs if t.key == request.GET.get('tab')), page.tabs[0])
    context = {'page': page, 'tab': tab, 'tabs': page.tabs, 'intro': page.intro.get(tab.key, '')}
    if tab.key in page.custom_tabs:
        return page.custom_tabs[tab.key](request, page, context)
    handler = {'browse': _browse, 'create': _create, 'update': _update, 'delete': _delete}[tab.key]
    return handler(request, page, tab, context)


def _browse(request, page, tab, context):
    rows = page.queryset(request)
    filters = {}
    if page.browse_filters:
        rows, filters = page.browse_filters(request, rows)
    text = request.GET.get('q', '').strip()
    rows = page.search(rows, text)
    try:
        size = int(request.GET.get('size', PAGE_SIZES[0]))
    except ValueError:
        size = PAGE_SIZES[0]
    size = size if size in PAGE_SIZES else PAGE_SIZES[0]
    paginator = Paginator(rows, size)
    current = paginator.get_page(request.GET.get('page'))
    context.update({
        'columns': page.columns,
        'rows': [[(c.cell(obj), c.numeric) for c in page.columns] for obj in current.object_list],
        'current': current,
        'paginator': paginator,
        'size': size,
        'sizes': PAGE_SIZES,
        'q': text,
        'filters': filters,
        'prev_url': _page_url(request, current.previous_page_number()) if current.has_previous() else '',
        'next_url': _page_url(request, current.next_page_number()) if current.has_next() else '',
    })
    return render(request, 'storefront/table_page.html', context)


def _page_url(request, number):
    params = request.GET.copy()
    params['page'] = number
    return f'?{params.urlencode()}'


def _create(request, page, tab, context):
    form = page.create_form(request.POST or None, request=request)
    if request.method == 'POST' and form.is_valid():
        try:
            obj = page.on_create(request, form) if page.on_create else form.save()
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f'{page.singular} {page.label(obj)} created.')
            return redirect(page.url(tab=tab.key))
    context['form'] = form
    return render(request, 'storefront/table_page.html', context)


def _picker(request, page, context):
    """Find a record to update or delete: search, then pick one of the matches."""
    text = request.GET.get('q', '').strip()
    rows = page.queryset(request)
    matches = list(page.search(rows, text)[:PICKER_LIMIT]) if text else []
    selected = None
    if request.GET.get('id', '').isdigit():
        selected = rows.filter(pk=int(request.GET['id'])).first()
    context.update({'q': text, 'matches': [(m.pk, page.label(m)) for m in matches], 'selected': selected,
                    'selected_label': page.label(selected) if selected else ''})
    return selected


def _update(request, page, tab, context):
    selected = _picker(request, page, context)
    if selected is not None:
        form = page.update_form(request.POST or None, instance=selected, request=request)
        if request.method == 'POST' and form.is_valid():
            form.save()
            messages.success(request, f'{page.singular} {page.label(selected)} updated.')
            return redirect(page.url(tab=tab.key, id=selected.pk))
        context['form'] = form
    return render(request, 'storefront/table_page.html', context)


def _delete(request, page, tab, context):
    selected = _picker(request, page, context)
    if selected is not None:
        context['detail'] = [(c.label, c.cell(selected)) for c in page.columns]
        form = page.delete_form(request.POST or None, request=request) if page.delete_form else None
        context['form'] = form
        if request.method == 'POST' and (form is None or form.is_valid()):
            label = page.label(selected)
            try:
                if page.on_delete:
                    message = page.on_delete(request, selected, form)
                else:
                    selected.delete()
                    message = f'{page.singular} {label} deleted.'
            except ProtectedError:
                messages.error(request, f"{page.singular} {label} can't be deleted: other records depend on it, "
                                        'and their history is kept.')
                return redirect(page.url(tab=tab.key, id=selected.pk))
            except ValidationError as error:
                messages.error(request, ' '.join(error.messages))
                return redirect(page.url(tab=tab.key, id=selected.pk))
            messages.success(request, message)
            return redirect(page.url(tab=tab.key))
    return render(request, 'storefront/table_page.html', context)
