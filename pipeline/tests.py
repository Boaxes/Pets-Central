"""Tests for the loader's decisions. They use a fake Snowflake connection, so they need no credentials or credits."""

from datetime import datetime, timezone
from unittest import TestCase

import httpx

from . import load_loyalty
from . import load_store_ops as loader


class FakeCursor:
    def __init__(self, tables):
        self.tables = tables
        self.result = None

    def execute(self, sql, params=None):
        if 'INFORMATION_SCHEMA.TABLES' in sql:
            self.result = [(1,)] if params[0] in self.tables else []
        elif 'MAX(UPDATED_AT)' in sql:
            self.result = [(self.tables[sql.split('FROM ')[1]]['updated_at'],)]
        elif 'MAX(ID)' in sql:
            self.result = [(self.tables[sql.split('FROM ')[1]]['id'],)]
        return self

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result[0]


class FakeSnowflake:
    def __init__(self, tables=None):
        self.tables = tables or {}

    def cursor(self):
        return FakeCursor(self.tables)


class ChangedRowsFilterTests(TestCase):
    def test_first_run_loads_everything(self):
        for table in ['sales_sale', 'sales_salereturn', 'stores_store']:
            strategy, where, params = loader.changed_rows_filter(FakeSnowflake(), table, 'X')
            self.assertEqual((where, params), ('', []), table)

    def test_incremental_reads_from_the_newest_change_less_the_overlap(self):
        newest = datetime(2026, 9, 30, 23, 0, tzinfo=timezone.utc)
        sf = FakeSnowflake({'T': {'updated_at': newest}})
        strategy, where, params = loader.changed_rows_filter(sf, 'sales_sale', 'T')
        self.assertEqual(strategy, loader.INCREMENTAL)
        self.assertEqual(where, 'WHERE "updated_at" >= %s')
        self.assertEqual(params, [newest - loader.OVERLAP])

    def test_append_reads_ids_above_the_highest(self):
        sf = FakeSnowflake({'T': {'id': 146}})
        self.assertEqual(loader.changed_rows_filter(sf, 'sales_salereturn', 'T'),
                         (loader.APPEND, 'WHERE "id" > %s', [146]))

    def test_unlisted_tables_are_fully_refreshed(self):
        sf = FakeSnowflake({'T': {}})
        self.assertEqual(loader.changed_rows_filter(sf, 'inventory_stocklevel', 'T'), (loader.FULL, '', []))


class TypeMappingTests(TestCase):
    def test_types(self):
        self.assertEqual(loader.snowflake_type('numeric', 10, 2), 'NUMBER(10,2)')
        self.assertEqual(loader.snowflake_type('timestamp with time zone', None, None), 'TIMESTAMP_TZ')
        self.assertEqual(loader.snowflake_type('character varying', None, None), 'VARCHAR')

    def test_timestamps_are_exported_in_utc_with_an_offset(self):
        expression = loader.export_expression('sold_at', 'timestamp with time zone')
        self.assertIn("AT TIME ZONE 'UTC'", expression)
        self.assertIn('"+00:00"', expression)
        self.assertEqual(loader.export_expression('name', 'character varying'), '"name"')


class LoyaltyClientTests(TestCase):
    """The loyalty client against a fake API: retries, Retry-After and cursor paging."""

    def client(self, handler):
        self.slept = []
        return load_loyalty.LoyaltyClient('http://api.test', 'key', transport=httpx.MockTransport(handler),
                             sleep=self.slept.append)

    def test_retries_503_and_honors_429_retry_after(self):
        answers = iter([httpx.Response(503, headers={'Retry-After': '1'}),
                        httpx.Response(429, headers={'Retry-After': '3'}),
                        httpx.Response(200, json={'status': 'ok'})])
        client = self.client(lambda request: next(answers))
        self.assertEqual(client.get('/health'), {'status': 'ok'})
        self.assertEqual(self.slept, [1.0, 3.0])
        self.assertEqual(client.retries, 2)

    def test_backs_off_without_retry_after_and_gives_up_eventually(self):
        client = self.client(lambda request: httpx.Response(502))
        with self.assertRaises(httpx.HTTPStatusError):
            client.get('/v2/members')
        self.assertEqual(len(self.slept), load_loyalty.MAX_ATTEMPTS - 1)
        self.assertEqual(self.slept[:3], [0.5, 1.0, 2.0])

    def test_does_not_retry_client_errors(self):
        client = self.client(lambda request: httpx.Response(401))
        with self.assertRaises(httpx.HTTPStatusError):
            client.get('/v2/members')
        self.assertEqual(self.slept, [])

    def test_pages_follow_the_cursor_and_keep_the_filter(self):
        seen = []

        def handler(request):
            seen.append(dict(request.url.params))
            if 'cursor' not in request.url.params:
                return httpx.Response(200, json={'data': [{'id': 1}, {'id': 2}], 'next_cursor': 'c1',
                                                 'has_more': True})
            return httpx.Response(200, json={'data': [{'id': 3}], 'next_cursor': None, 'has_more': False})

        since = datetime(2026, 9, 1, tzinfo=timezone.utc)
        pages = list(self.client(handler).pages('/v2/members', since))
        self.assertEqual([len(p) for p in pages], [2, 1])
        self.assertEqual(seen[1]['cursor'], 'c1')
        self.assertTrue(all(p['updated_since'] == since.isoformat() for p in seen))


class LoyaltyWatermarkTests(TestCase):
    def test_first_run_starts_at_the_beginning_then_from_the_newest_change_less_an_hour(self):
        members = load_loyalty.ENDPOINTS[0]
        self.assertIsNone(load_loyalty.changed_since(FakeSnowflake(), members))

        newest = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

        class Cursor(FakeCursor):
            def execute(self, sql, params=None):
                self.result = [(newest,)] if 'MAX(CHANGED_AT)' in sql else [(1,)]
                return self

        class Snowflake:
            def cursor(self):
                return Cursor({})

        self.assertEqual(load_loyalty.changed_since(Snowflake(), members), newest - load_loyalty.OVERLAP)
