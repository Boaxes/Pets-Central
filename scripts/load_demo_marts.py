"""Loads the saved marts (data/marts/*.parquet, from scripts/export_marts.py) into the demo's `marts` database on the
Neon seed branch, and creates the read-only login the demo's analytics app uses. Run once, with the seed branch's
settings in data/neon.env (git-ignored; POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER and POSTGRES_PASSWORD):

    uv run --with pyarrow python scripts/load_demo_marts.py

Each table is replaced. The login `marts_reader` can read the marts and evaluation schemas and nothing else, in
read-only sessions with a statement timeout; its connection string is added to data/neon.env as MARTS_READER_URL.
Nothing secret is printed.
"""

import datetime
import decimal
import io
import secrets
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
MARTS = ROOT / 'data' / 'marts'
ENV = ROOT / 'data' / 'neon.env'
READER = 'marts_reader'
CHUNK = 5_000
ATTEMPTS = 4


def settings():
    pairs = (line.split('=', 1) for line in ENV.read_text().splitlines() if '=' in line and not line.startswith('#'))
    return {key.strip(): value.strip() for key, value in pairs}


def column_type(series):
    if pd.api.types.is_bool_dtype(series):
        return 'boolean'
    if pd.api.types.is_integer_dtype(series):
        return 'bigint'
    if pd.api.types.is_float_dtype(series):
        return 'double precision'
    if pd.api.types.is_datetime64_any_dtype(series):
        return 'timestamp'
    sample = series.dropna()
    value = sample.iloc[0] if len(sample) else None
    if isinstance(value, datetime.datetime):
        return 'timestamp'
    if isinstance(value, datetime.date):
        return 'date'
    if isinstance(value, decimal.Decimal):
        return 'numeric'
    if isinstance(value, (bool,)):
        return 'boolean'
    return 'text'


def whole_ids(frame):
    """Id columns with gaps come out of Snowflake as floats; store them as integers."""
    for name in frame.columns:
        if name.endswith('_id') and pd.api.types.is_float_dtype(frame[name]):
            values = frame[name].dropna()
            if (values == values.round()).all():
                frame[name] = frame[name].astype('Int64')
    return frame


def load_table(params, schema, table, frame):
    columns = [(name, column_type(frame[name])) for name in frame.columns]
    target = sql.Identifier(schema, table)
    with psycopg.connect(**params) as connection:
        connection.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(schema)))
        connection.execute(sql.SQL('DROP TABLE IF EXISTS {}').format(target))
        connection.execute(sql.SQL('CREATE TABLE {} ({})').format(target, sql.SQL(', ').join(
            sql.SQL('{} {}').format(sql.Identifier(name), sql.SQL(kind)) for name, kind in columns)))
    # CSV in pieces of a few thousand rows, each on its own connection and retried: uploads from this machine to
    # Neon now and then broke with TLS errors ("bad record mac"). A broken piece's COPY never commits.
    statement = sql.SQL('COPY {} ({}) FROM STDIN WITH (FORMAT csv)').format(
        target, sql.SQL(', ').join(sql.Identifier(name) for name, _ in columns))
    for start in range(0, len(frame), CHUNK):
        buffer = io.StringIO()
        frame.iloc[start:start + CHUNK].to_csv(buffer, header=False, index=False)
        for attempt in range(1, ATTEMPTS + 1):
            try:
                with psycopg.connect(**params) as connection, connection.cursor() as cursor:
                    with cursor.copy(statement) as copy:
                        copy.write(buffer.getvalue())
                break
            except psycopg.OperationalError as error:
                if attempt == ATTEMPTS:
                    raise
                print(f'  {schema}.{table} rows {start:,}+: {error}; trying again')


def main():
    env = settings()
    params = dict(host=env['POSTGRES_HOST'], port=env['POSTGRES_PORT'], user=env['POSTGRES_USER'],
                  password=env['POSTGRES_PASSWORD'], dbname='marts', sslmode='require')
    for path in sorted(MARTS.glob('*.parquet')):
        schema, table = path.stem.split('.', 1)
        frame = whole_ids(pd.read_parquet(path))
        load_table(params, schema, table, frame)
        print(f'{schema}.{table}: {len(frame):,} rows')

    with psycopg.connect(**params) as connection, connection.cursor() as cursor:
        password = env.get('MARTS_READER_PASSWORD') or secrets.token_urlsafe(24)
        cursor.execute('SELECT EXISTS (SELECT FROM pg_roles WHERE rolname = %s)', [READER])
        ident = sql.Identifier(READER)
        if not cursor.fetchone()[0]:
            cursor.execute(sql.SQL('CREATE ROLE {} LOGIN').format(ident))
        for statement, values in (
            ('ALTER ROLE {} WITH LOGIN NOINHERIT CONNECTION LIMIT 20 PASSWORD {}', [password]),
            ('ALTER ROLE {} SET default_transaction_read_only = on', []),
            ('ALTER ROLE {} SET statement_timeout = {}', ['15s']),
            ('ALTER ROLE {} SET idle_in_transaction_session_timeout = {}', ['30s']),
        ):
            cursor.execute(sql.SQL(statement).format(ident, *(sql.Literal(v) for v in values)))
        cursor.execute(sql.SQL('REVOKE ALL ON SCHEMA public FROM {}').format(ident))
        cursor.execute(sql.SQL('GRANT CONNECT ON DATABASE marts TO {}').format(ident))
        for schema in ('marts', 'evaluation'):
            cursor.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(schema), ident))
            cursor.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}').format(sql.Identifier(schema), ident))
        print(f'{READER} can read the marts.')

    url = f"postgresql://{READER}:{quote(password, safe='')}@{env['POSTGRES_HOST']}/marts?sslmode=require"
    lines = [line for line in ENV.read_text().splitlines() if not line.startswith(('MARTS_READER_URL=', 'MARTS_READER_PASSWORD='))]
    ENV.write_text('\n'.join(lines + [f'MARTS_READER_PASSWORD={password}', f'MARTS_READER_URL={url}']) + '\n')
    print('data/neon.env now has MARTS_READER_URL.')


if __name__ == '__main__':
    main()
