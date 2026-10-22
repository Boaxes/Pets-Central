"""Saves the dev warehouse's marts (built from the `small` dataset) and its evaluation tables as Parquet files in
data/marts/, before Snowflake is destroyed. The demo's Postgres copy of the marts is loaded from these files.

    uv run --with pyarrow python scripts/export_marts.py

Signs in as dbt's service user, with the key in ~/.snowflake/keys/pets_dbt.p8.
"""

from pathlib import Path

import snowflake.connector

OUT = Path(__file__).resolve().parent.parent / 'data' / 'marts'
SCHEMAS = ['MARTS', 'EVALUATION']


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    connection = snowflake.connector.connect(
        account='ZDNLOQP-ZB02546', user='PETS_DBT_SVC', authenticator='SNOWFLAKE_JWT',
        private_key_file=str(Path.home() / '.snowflake' / 'keys' / 'pets_dbt.p8'),
        role='PETS_TRANSFORMER', warehouse='PETS_WH', database='PETS_CENTRAL_DEV')
    cursor = connection.cursor()
    for schema in SCHEMAS:
        tables = cursor.execute(f"select table_name from information_schema.tables "
                                f"where table_schema = '{schema}' order by 1").fetchall()
        for (table,) in tables:
            frame = cursor.execute(f'select * from {schema}.{table}').fetch_pandas_all()
            frame.columns = [column.lower() for column in frame.columns]
            path = OUT / f'{schema.lower()}.{table.lower()}.parquet'
            frame.to_parquet(path, index=False)
            print(f'{path.name}: {len(frame):,} rows')
    connection.close()


if __name__ == '__main__':
    main()
