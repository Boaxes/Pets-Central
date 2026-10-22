"""Copy new and changed store operations rows from Postgres into Snowflake's RAW schema.

Each table has a strategy (see STRATEGIES):

- incremental: rows whose updated_at is at or after the newest one already in RAW, minus a short overlap. New
  versions are appended, so RAW keeps every version of a row; dbt keeps the latest per id.
- append: rows with an id above the highest in RAW. For tables whose rows never change.
- full: the whole table, swapped in at once. For small tables and snapshots such as stock levels.

Rows are exported with Postgres COPY as gzipped CSV, uploaded to a Snowflake table stage and loaded with COPY INTO a
loading table. The row count is checked against Postgres before anything reaches the RAW table, so a failed run
never leaves a half-loaded table. The first run of an empty RAW schema loads everything.

    uv run python -m pipeline.load_store_ops
    uv run python -m pipeline.load_store_ops --tables sales_sale sales_saleline
    uv run python -m pipeline.load_store_ops --verify-only
"""

import argparse
import gzip
import sys
from datetime import timedelta

import psycopg

from .connections import connect_postgres, connect_snowflake
from .snowflake_io import EXPORT_DIR, log, publish, snowflake_count, table_exists, upload

SOURCE_PREFIXES = ('stores_', 'catalog_', 'customers_', 'inventory_', 'sales_')
TARGET_PREFIX = 'STORE_OPS__'
FILE_FORMAT = 'PG_CSV'
MAX_FILE_BYTES = 256 * 1024 * 1024  # Uncompressed; Snowflake loads 100-250 MB compressed files best.
# Re-read a little before the watermark, so a row committed late with an earlier updated_at isn't missed.
OVERLAP = timedelta(minutes=15)

INCREMENTAL, APPEND, FULL = 'incremental', 'append', 'full'
STRATEGIES = {
    'customers_customer': INCREMENTAL,
    'catalog_productprice': INCREMENTAL,
    'inventory_animal': INCREMENTAL,
    'sales_sale': INCREMENTAL,
    'sales_saleline': INCREMENTAL,
    'sales_salereturn': APPEND,
    'sales_salereturnline': APPEND,
}

PG_TO_SNOWFLAKE = {
    'bigint': 'NUMBER(38,0)', 'integer': 'NUMBER(38,0)', 'smallint': 'NUMBER(38,0)',
    'character varying': 'VARCHAR', 'text': 'VARCHAR', 'boolean': 'BOOLEAN', 'date': 'DATE',
    'timestamp with time zone': 'TIMESTAMP_TZ',
}


def source_tables(pg):
    """Store operations tables only. Django's own tables (users, password hashes, sessions) never leave Postgres."""
    rows = pg.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name""").fetchall()
    return [name for (name,) in rows if name.startswith(SOURCE_PREFIXES)]


def source_columns(pg, table):
    return pg.execute("""
        SELECT column_name, data_type, numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position""", [table]).fetchall()


def snowflake_type(data_type, precision, scale):
    if data_type == 'numeric':
        return f'NUMBER({precision},{scale})'
    return PG_TO_SNOWFLAKE[data_type]


def export_expression(name, data_type):
    if data_type == 'timestamp with time zone':
        # ISO 8601 in UTC with the offset spelled out, which Snowflake reads without a custom format.
        return f"""to_char("{name}" AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"')"""
    return f'"{name}"'


def ensure_file_format(sf):
    sf.cursor().execute(f"""
        CREATE FILE FORMAT IF NOT EXISTS {FILE_FORMAT}
            TYPE = CSV COMPRESSION = GZIP FIELD_OPTIONALLY_ENCLOSED_BY = '"' ESCAPE_UNENCLOSED_FIELD = NONE
            EMPTY_FIELD_AS_NULL = TRUE NULL_IF = ()
        COMMENT = 'Postgres COPY ... WITH (FORMAT csv): unquoted empty is NULL, quoted empty is an empty string'""")


def changed_rows_filter(sf, table, target):
    """The WHERE clause and parameters that select what this run loads, from what RAW already has."""
    strategy = STRATEGIES.get(table, FULL)
    if strategy == FULL or not table_exists(sf, target):
        return strategy, '', []
    if strategy == INCREMENTAL:
        newest = sf.cursor().execute(f'SELECT MAX(UPDATED_AT) FROM {target}').fetchone()[0]
        return (strategy, 'WHERE "updated_at" >= %s', [newest - OVERLAP]) if newest else (strategy, '', [])
    highest = sf.cursor().execute(f'SELECT MAX(ID) FROM {target}').fetchone()[0]
    return (strategy, 'WHERE "id" > %s', [int(highest)]) if highest is not None else (strategy, '', [])


def load_table(pg, sf, table, allow_empty=False):
    """Loads one table's new or changed rows into RAW and returns how many rows it loaded."""
    target = TARGET_PREFIX + table.upper()
    loading = target + '__LOADING'
    columns = source_columns(pg, table)
    strategy, where_sql, params = changed_rows_filter(sf, table, target)

    cursor = sf.cursor()
    # One snapshot for the count and the export, so rows changing mid-run can't make them disagree.
    with pg.transaction():
        expected = pg.execute(f'SELECT COUNT(*) FROM "{table}" {where_sql}', params).fetchone()[0]
        if strategy == FULL and expected == 0 and not allow_empty and table_exists(sf, target) \
                and snowflake_count(sf, target) > 0:
            log(f'{table}: SKIPPED. Postgres is empty but {target} has rows; pass --allow-empty to replace them.')
            return 0
        if strategy != FULL and expected == 0 and table_exists(sf, target):
            log(f'{table}: no new or changed rows')
            return 0

        definition = ', '.join(f'"{name.upper()}" {snowflake_type(t, p, s)}' for name, t, p, s in columns)
        cursor.execute(f'CREATE OR REPLACE TABLE {loading} ({definition}, '
                       f'_LOADED_AT TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP())')
        select = ', '.join(export_expression(name, t) for name, t, _, _ in columns)
        query = f'COPY (SELECT {select} FROM "{table}" {where_sql}) TO STDOUT WITH (FORMAT csv)'
        files = _export_and_upload(pg, cursor, table, loading, query, params)

    column_list = ', '.join(f'"{name.upper()}"' for name, *_ in columns)
    if files:
        cursor.execute(f'COPY INTO {loading} ({column_list}) FROM @%{loading} '
                       f'FILE_FORMAT = (FORMAT_NAME = {FILE_FORMAT}) PURGE = TRUE ON_ERROR = ABORT_STATEMENT')
    loaded = publish(sf, loading, target, expected, table, replace=strategy == FULL)
    log(f'{table} ({strategy}): {loaded:,} rows -> {target}')
    return loaded


def _export_and_upload(pg, cursor, table, loading, query, params):
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    files = 0
    out = path = None
    written = 0
    with pg.cursor().copy(query, params) as copy:
        for block in copy:
            if out is None:
                files += 1
                path = EXPORT_DIR / f'{table}_{files:04d}.csv.gz'
                out, written = gzip.open(path, 'wb', compresslevel=5), 0
            out.write(block)
            written += len(block)
            if written >= MAX_FILE_BYTES:
                out.close()
                upload(cursor, path, loading)
                out = None
    if out is not None:
        out.close()
        upload(cursor, path, loading)
    return files


def verify(pg, sf, tables):
    """Compare Postgres with RAW: row counts and id sums. RAW may hold several versions of a row, so it counts ids."""
    all_match = True
    print(f'{"table":32} {"postgres":>12} {"snowflake":>12}  match')
    for table in tables:
        target = TARGET_PREFIX + table.upper()
        source = pg.execute(f'SELECT COUNT(*), COALESCE(SUM(id), 0) FROM "{table}"').fetchone()
        copied = (sf.cursor().execute(f'SELECT COUNT(DISTINCT ID), COALESCE(SUM(DISTINCT ID), 0) FROM {target}')
                  .fetchone() if table_exists(sf, target) else (None, None))
        match = tuple(source) == tuple(copied)
        all_match &= match
        print(f'{table:32} {source[0]:>12,} {f'{copied[0]:,}' if copied[0] is not None else 'missing':>12}  '
              f'{"yes" if match else "NO"}')
    return all_match


def run(tables=None, allow_empty=False):
    """Loads the given Postgres tables (all of them by default) and returns the rows loaded per table."""
    with connect_postgres() as pg, connect_snowflake() as sf:
        pg.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        tables = tables or source_tables(pg)
        ensure_file_format(sf)
        log(f'Loading {len(tables)} tables into {sf.database}.{sf.schema}')
        return {table: load_table(pg, sf, table, allow_empty=allow_empty) for table in tables}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--tables', nargs='+', help='Load only these Postgres tables.')
    parser.add_argument('--allow-empty', action='store_true',
                        help='Replace a fully refreshed Snowflake table even when the Postgres table is empty.')
    parser.add_argument('--verify-only', action='store_true', help='Only compare Postgres and Snowflake.')
    args = parser.parse_args(argv)

    if not args.verify_only:
        run(args.tables, allow_empty=args.allow_empty)
    with connect_postgres() as pg, connect_snowflake() as sf:
        matched = verify(pg, sf, args.tables or source_tables(pg))
    print('All tables match.' if matched else 'Some tables do not match.')
    return 0 if matched else 1


if __name__ == '__main__':
    sys.exit(main())
