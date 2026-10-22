"""Bulk-loads the generated tables into Postgres with COPY."""

import io
import time
from pathlib import Path

import numpy as np
import pandas as pd
from django.conf import settings
from django.db import connection, transaction

from catalog.models import Brand, Category, Department, Product, ProductPrice, Species
from customers.models import Customer
from inventory.models import Animal, StockLevel
from sales.models import Sale, SaleLine, SaleReturn, SaleReturnLine
from stores.models import Employee, Region, Store

from . import build_catalog, build_customers, build_loyalty, build_org, build_sales
from .build_org import NO_DAY
from .timeline import day_start_seconds, days_to_strings, seconds_to_strings

LOAD_ORDER = [Region, Store, Employee, Department, Category, Brand, Species, Product, ProductPrice, Customer, Sale,
              Animal, SaleLine, SaleReturn, SaleReturnLine, Animal.caretakers.through, StockLevel]


def table(model):
    return connection.ops.quote_name(model._meta.db_table)


def nullable_id(values):
    """Integer ids where 0 means "none", as a column that writes NULL."""
    values = pd.array(np.asarray(values), dtype='Int64')
    values[values == 0] = pd.NA
    return values


def copy(model, frame, text_columns=()):
    """COPY a DataFrame into a model's table. Empty strings in `text_columns` stay empty strings, not NULL."""
    buffer = io.StringIO()
    frame.to_csv(buffer, header=False, index=False, float_format='%.2f')
    columns = ', '.join(connection.ops.quote_name(c) for c in frame.columns)
    options = 'FORMAT csv'
    if text_columns:
        options += ', FORCE_NOT_NULL (' + ', '.join(connection.ops.quote_name(c) for c in text_columns) + ')'
    with transaction.atomic(), connection.cursor() as cursor:
        with cursor.cursor.copy(f'COPY {table(model)} ({columns}) FROM STDIN WITH ({options})') as pg_copy:
            pg_copy.write(buffer.getvalue())


def has_data():
    return Store.objects.exists() or Sale.objects.exists()


def truncate():
    names = ', '.join(table(model) for model in LOAD_ORDER)
    with connection.cursor() as cursor:
        cursor.execute(f'TRUNCATE {names} RESTART IDENTITY CASCADE')


def reset_sequences():
    """Point each table's id sequence past the ids the generator assigned."""
    with connection.cursor() as cursor:
        for model in LOAD_ORDER:
            name = model._meta.db_table
            cursor.execute(f"SELECT setval(pg_get_serial_sequence(%s, 'id'), GREATEST(MAX(id), 1), MAX(id) IS NOT NULL) "
                           f'FROM {table(model)}', [name])


def coupon_codes(ctx, campaign_index):
    """Coupon codes as typed at the register: mostly exact, sometimes lowercase or with a stray space."""
    rng = ctx.rng
    codes = np.where(campaign_index >= 0, ctx.campaigns.code.to_numpy()[np.maximum(campaign_index, 0)], '')
    codes = pd.Series(codes, dtype=object)
    roll = rng.random(len(codes))
    used = codes != ''
    codes[used & (roll < 0.05)] = codes[used & (roll < 0.05)].str.lower()
    spaced = used & (roll >= 0.05) & (roll < 0.07)
    codes[spaced] = codes[spaced].str.replace('-', ' - ', regex=False)
    return codes.to_numpy()


def generate(ctx, output_dir):
    """Build the history and load it into Postgres. The loyalty data and the truth files go to output_dir."""
    started = time.monotonic()

    def step(message):
        ctx.log(f'[{time.monotonic() - started:6.1f}s] {message}')

    step('Building stores and staff')
    ctx.regions = build_org.build_regions()
    ctx.stores = build_org.build_stores(ctx)
    ctx.employees = build_org.build_employees(ctx)
    step('Building the catalog and price history')
    build_catalog.build_catalog(ctx)
    step('Building customers and campaigns')
    build_customers.build_customers(ctx)
    build_customers.build_campaigns(ctx)
    step('Building sales')
    build_sales.build_sales(ctx)

    step('Loading stores, staff, catalog and customers')
    _load_reference(ctx)
    step(f'Loading {len(ctx.sales):,} sales')
    _load_sales(ctx)

    maker = build_sales.LineMaker(ctx)
    animal_frames = []
    total_lines = 0
    # What each sale came to after discounts, and its discount, in cents: the loyalty data needs both.
    sale_net_cents = np.zeros(len(ctx.sales) + 1)
    sale_discount_cents = np.zeros(len(ctx.sales) + 1)
    for animals, lines in maker.chunks():
        _load_animals(animals)
        copy(SaleLine, lines.assign(animal_id=nullable_id(lines.animal_id)))
        animal_frames.append(animals[['id', 'store_id', 'received']])
        discount = lines.discount_amount.to_numpy() * 100
        net = lines.quantity.to_numpy() * lines.unit_price.to_numpy() * 100 - discount
        sale_net_cents += np.bincount(lines.sale_id, weights=net, minlength=len(sale_net_cents))
        sale_discount_cents += np.bincount(lines.sale_id, weights=discount, minlength=len(sale_net_cents))
        total_lines += len(lines)
        step(f'  {total_lines:,} sale lines loaded')

    step('Loading returns, animals still in stores, caretakers and stock')
    returns = maker.finish_returns()
    _load_returns(returns)
    extra = maker.extra_animals()
    _load_animals(extra)
    animal_frames.append(extra[['id', 'store_id', 'received']])
    all_animals = pd.concat(animal_frames, ignore_index=True)
    caretakers = maker.caretakers(all_animals.store_id.to_numpy(), all_animals.id.to_numpy(),
                                  all_animals.received.to_numpy())
    copy(Animal.caretakers.through, caretakers[['id', 'animal_id', 'employee_id']])
    stock = build_sales.build_stock_levels(ctx)
    copy(StockLevel, stock[['id', 'store_id', 'product_id', 'quantity_on_hand', 'reorder_point']])

    step('Resetting id sequences and updating planner statistics')
    reset_sequences()
    with connection.cursor() as cursor:
        cursor.execute('ANALYZE')

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_true_lift(ctx, output_dir)
    step('Building the loyalty platform data')
    loyalty = build_loyalty.build_loyalty(
        ctx, np.round(sale_net_cents).astype(np.int64), np.round(sale_discount_cents).astype(np.int64),
        output_dir / 'loyalty.sqlite3', output_dir / 'loyalty_member_truth.csv')

    summary = {
        'stores': len(ctx.stores), 'employees': len(ctx.employees), 'products': len(ctx.products),
        'customers': len(ctx.customers), 'sales': len(ctx.sales), 'sale_lines': total_lines,
        'returns': len(returns), 'animals': len(all_animals), 'stock_levels': len(stock),
        'campaigns': len(ctx.campaigns), **loyalty,
    }
    step('Done: ' + ', '.join(f'{v:,} {k.replace("_", " ")}' for k, v in summary.items()))
    return summary


def _load_reference(ctx):
    copy(Region, ctx.regions[['id', 'code', 'name']])

    s = ctx.stores
    copy(Store, pd.DataFrame({
        'id': s.id, 'store_code': s.store_code, 'name': s.name, 'region_id': s.region_id,
        'original_chain': s.chain, 'store_format': s.format, 'address_line': s.address_line, 'city': s.city,
        'state': s.state, 'postal_code': s.postal_code, 'time_zone': s.time_zone,
        'opened_on': days_to_strings(s.opened), 'acquired_on': days_to_strings(s.acquired, missing=NO_DAY),
        'closed_on': days_to_strings(s.closed, missing=NO_DAY),
    }))

    e = ctx.employees
    copy(Employee, pd.DataFrame({
        'id': e.id, 'store_id': e.store_id, 'employee_number': e.employee_number, 'first_name': e.first_name,
        'last_name': e.last_name, 'email': e.email, 'role': e.role, 'hourly_rate': e.hourly_rate,
        'hired_on': days_to_strings(e.hired), 'terminated_on': days_to_strings(e.terminated, missing=NO_DAY),
    }), text_columns=['email'])

    copy(Department, ctx.departments[['id', 'code', 'name']])
    copy(Category, ctx.categories[['id', 'department_id', 'name']])
    copy(Brand, ctx.brands[['id', 'name', 'is_house_brand']])
    copy(Species, ctx.species[['id', 'department_id', 'common_name', 'scientific_name']],
         text_columns=['scientific_name'])

    p = ctx.products
    copy(Product, pd.DataFrame({
        'id': p.id, 'sku': p.sku, 'name': p.name, 'category_id': p.category_id,
        'brand_id': nullable_id(p.brand_id.fillna(0).astype(int)),
        'species_id': nullable_id(p.species_id.fillna(0).astype(int)),
        'introduced_on': days_to_strings(p.introduced), 'discontinued_on': days_to_strings(p.discontinued, NO_DAY),
    }))

    pr = ctx.prices
    valid_to = seconds_to_strings(day_start_seconds(np.where(pr.valid_to == NO_DAY, 0, pr.valid_to)))
    valid_to[(pr.valid_to == NO_DAY).to_numpy()] = ''
    copy(ProductPrice, pd.DataFrame({
        'id': pr.id, 'product_id': pr.product_id, 'list_price': pr.list_cents / 100, 'unit_cost': pr.cost_cents / 100,
        'valid_from': seconds_to_strings(day_start_seconds(pr.valid_from)), 'valid_to': valid_to,
        # A price row last changed when the next price closed it.
        'updated_at': seconds_to_strings(day_start_seconds(np.where(pr.valid_to == NO_DAY, pr.valid_from, pr.valid_to))),
    }))

    c = ctx.customers
    copy(Customer, pd.DataFrame({
        'id': c.id, 'first_name': c.first_name, 'last_name': c.last_name, 'email': c.email, 'phone': c.phone,
        'postal_code': c.postal_code, 'home_store_id': c.home_store_id, 'marketing_opt_in': c.opt_in,
        'created_at': seconds_to_strings(c.created_at), 'updated_at': seconds_to_strings(c.created_at),
    }), text_columns=['email', 'phone', 'postal_code'])


def _load_sales(ctx):
    sales = ctx.sales
    store_ids = ctx.stores.id.to_numpy()
    codes = coupon_codes(ctx, sales.campaign.to_numpy())
    for start in range(0, len(sales), build_sales.CHUNK_SALES):
        part = sales.iloc[start:start + build_sales.CHUNK_SALES]
        cancelled_at = seconds_to_strings(part.cancelled_at)
        cancelled_at[~part.cancelled.to_numpy()] = ''
        copy(Sale, pd.DataFrame({
            'id': part.id,
            'receipt_number': [f'R{i:010d}' for i in part.id],
            'store_id': store_ids[part.store],
            'customer_id': nullable_id(part.customer_id),
            'employee_id': nullable_id(part.employee_id),
            'channel': np.where(part.online, 'online', 'in_store'),
            'status': np.where(part.cancelled, 'cancelled', 'completed'),
            'sold_at': seconds_to_strings(part.sold_at),
            'cancelled_at': cancelled_at,
            'coupon_code': codes[start:start + len(part)],
            'updated_at': seconds_to_strings(np.where(part.cancelled, part.cancelled_at, part.sold_at)),
        }), text_columns=['coupon_code'])


def _load_animals(animals):
    if not len(animals):
        return
    copy(Animal, pd.DataFrame({
        'id': animals.id, 'product_id': animals.product_id, 'store_id': animals.store_id, 'name': animals['name'],
        'sex': animals.sex, 'born_on': days_to_strings(animals.born), 'received_on': days_to_strings(animals.received),
        'removed_on': days_to_strings(animals.removed, missing=NO_DAY), 'removal_reason': animals.removal_reason,
        # Animals change when they arrive and when they are removed; selling one changes the sale line instead.
        'updated_at': seconds_to_strings(day_start_seconds(np.where(animals.removed == NO_DAY, animals.received,
                                                                    animals.removed)) + 10 * 3600),
    }), text_columns=['name', 'removal_reason'])


def _load_returns(returns):
    if not len(returns):
        return
    copy(SaleReturn, pd.DataFrame({
        'id': returns.id, 'return_number': [f'RT{i:09d}' for i in returns.id], 'sale_id': returns.sale_id,
        'store_id': returns.store_id, 'employee_id': nullable_id(returns.employee_id), 'reason': returns.reason,
        'returned_at': seconds_to_strings(returns.returned_at),
    }))
    copy(SaleReturnLine, pd.DataFrame({
        'id': returns.id, 'sale_return_id': returns.id, 'sale_line_id': returns.sale_line_id,
        'quantity': returns.quantity, 'refund_amount': returns.refund_amount, 'restocked': returns.restocked,
    }))


def _write_true_lift(ctx, output_dir):
    """The real effect of each campaign, kept apart so the analysis can be checked against it."""
    c = ctx.campaigns
    pd.DataFrame({'campaign_id': c.id, 'code': c.code, 'true_lift': c.lift.round(3)}).to_csv(
        output_dir / 'campaign_true_lift.csv', index=False)


def default_output_dir(size_name):
    return Path(settings.BASE_DIR) / 'data' / 'generated' / size_name
