"""Runs the assistant's SQL as its own database login, which sees only one store's data.

The login (ASSISTANT_DB_USER) can read the store_data views and nothing else. Each session is read-only, has a
5-second statement timeout, and is bound to one store through assistant_scope before any query runs.

The binding is keyed by the session's server process id, so the assistant needs a direct database connection, not
one through a transaction-mode pooler.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import psycopg
from django.conf import settings
from django.db import connection

from .models import Scope
from .sql_guard import UnsafeSql, check_sql

ROW_LIMIT = 200
TIMEOUT_MS = 5000

# What the model is told about the views. Keep it in step with migrations/0002_store_data_views.py.
SCHEMA = """\
store (one row): store_code, name, region, original_chain ('pets_central' or 'critter_corner', for stores bought \
from Critter Corner), store_format ('standard', 'flagship', 'express'), address_line, city, state, postal_code, \
time_zone, opened_on, acquired_on (the day an acquired store joined Pets Central), closed_on
employees: employee_id, employee_number, first_name, last_name, role ('store_manager', 'assistant_manager', \
'associate', 'animal_care', 'groomer'), hourly_rate, hired_on, terminated_on, is_active
customers (customers whose home store is this store): customer_id, first_name, last_name, email, phone, \
postal_code, marketing_opt_in, created_at. Entered by hand, so one person can appear twice.
products (the whole chain's catalog, with this store's stock): product_id, sku, name, department, category, brand, \
is_house_brand, species, is_live_animal, introduced_on, discontinued_on, list_price (current), unit_cost (current), \
quantity_on_hand, reorder_point. Stock is null for live animals, which are counted one by one in animals.
animals (live animals this store has received): animal_id, product_id, species, name, sex ('male', 'female', \
'unknown'), born_on, received_on, status ('available', 'sold', 'removed'), sale_id, sold_at, removed_on, \
removal_reason ('deceased', 'returned_to_breeder', 'transferred_out')
animal_caretakers: animal_id, employee_id
sales: sale_id, receipt_number, sold_at, channel ('in_store', 'online'), status ('completed', 'cancelled'), \
cancelled_at, customer_id (null for guests), employee_id, coupon_code, net_total, item_count
sale_lines: sale_line_id, sale_id, line_number, sold_at, sale_status, product_id, sku, product_name, department, \
category, animal_id, quantity, unit_price, unit_cost, discount_amount, net_amount (quantity * unit_price - discount)
returns (returns processed at this store): return_id, return_number, sale_id, returned_at, reason ('damaged', \
'wrong_item', 'pet_refused', 'changed_mind', 'other'), employee_id, sold_here, refund_total, item_count
return_lines: return_id, sale_line_id, product_id, sku, product_name, quantity, refund_amount, restocked"""


@dataclass
class QueryResult:
    columns: list
    rows: list
    truncated: bool

@contextmanager
def store_session(store):
    """A database session as the assistant's login that can see one store's data, until it closes."""
    db = connection.settings_dict
    conn = psycopg.connect(
        host=db['HOST'] or 'localhost', port=db['PORT'] or '5432', dbname=db['NAME'],
        user=settings.ASSISTANT_DB_USER, password=settings.ASSISTANT_DB_PASSWORD,
        sslmode=db['OPTIONS'].get('sslmode', 'prefer'), connect_timeout=5,
        # The login has these defaults too. Times come back on the store's clock, so ::date is the local date.
        options=f'-c default_transaction_read_only=on -c statement_timeout={TIMEOUT_MS} '
                f'-c search_path=store_data -c TimeZone={store.time_zone}',
    )
    try:
        pid = conn.info.backend_pid
        # Written on the app's own connection and committed, so the assistant's session can see it.
        Scope.objects.update_or_create(backend_pid=pid, defaults={'store': store})
        try:
            yield conn
        finally:
            Scope.objects.filter(backend_pid=pid).delete()
    finally:
        conn.close()


def run_query(conn, text):
    """Runs one SELECT and returns up to ROW_LIMIT rows. Raises UnsafeSql or psycopg.Error with the reason."""
    query = check_sql(text)
    with conn.transaction():
        # A server-side cursor, so a query that matches a million rows only sends back the first ones.
        with conn.cursor(name='assistant_query') as cursor:
            cursor.execute(query)
            rows = cursor.fetchmany(ROW_LIMIT + 1)
            columns = [column.name for column in cursor.description]
    truncated = len(rows) > ROW_LIMIT
    return QueryResult(columns=columns, rows=[[_plain(v) for v in row] for row in rows[:ROW_LIMIT]],
                       truncated=truncated)


def describe_error(error):
    """A short reason the model can fix its query from."""
    if isinstance(error, UnsafeSql):
        return str(error)
    if isinstance(error, psycopg.errors.QueryCanceled):
        return f'The query took longer than {TIMEOUT_MS // 1000} seconds and was stopped. Aggregate more or filter.'
    diag = getattr(error, 'diag', None)
    message = (diag.message_primary if diag and diag.message_primary else str(error)).strip()
    if diag and diag.message_hint:
        message += f' Hint: {diag.message_hint}'
    return message


def _plain(value):
    """Values as JSON-friendly text and numbers, with times on the store's clock as the session returned them."""
    if isinstance(value, Decimal):
        return float(value) if value != value.to_integral_value() else int(value)
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M')
    if isinstance(value, date):
        return value.isoformat()
    return value
