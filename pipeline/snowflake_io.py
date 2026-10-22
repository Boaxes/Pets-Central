"""Helpers both loaders use to stage files in Snowflake and check what landed."""

import time

from .connections import ROOT

EXPORT_DIR = ROOT / 'data' / 'export'
_started = time.monotonic()


def log(message):
    print(f'[{time.monotonic() - _started:7.1f}s] {message}', flush=True)


def table_exists(sf, name):
    return bool(sf.cursor().execute(
        'SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = CURRENT_SCHEMA() AND TABLE_NAME = %s',
        [name]).fetchall())


def snowflake_count(sf, name):
    return sf.cursor().execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]


def upload(cursor, path, table):
    """PUT a gzipped file into a table's stage, then delete the local copy."""
    cursor.execute(f"PUT 'file://{path.as_posix()}' @%{table} AUTO_COMPRESS = FALSE SOURCE_COMPRESSION = GZIP "
                   f'PARALLEL = 8')
    path.unlink()


def publish(sf, loading, target, expected, what, replace=False):
    """Move a loading table into RAW, only if it holds exactly the rows expected; otherwise RAW is left as it was.

    With replace the whole table is swapped in; otherwise its rows are appended. Returns the number of rows.
    """
    loaded = snowflake_count(sf, loading)
    if loaded != expected:
        raise RuntimeError(f'{what}: expected {expected:,} rows but {loading} has {loaded:,}; RAW was not changed.')
    cursor = sf.cursor()
    if not table_exists(sf, target):
        cursor.execute(f'ALTER TABLE {loading} RENAME TO {target}')
    elif replace:
        cursor.execute(f'ALTER TABLE {loading} SWAP WITH {target}')
        cursor.execute(f'DROP TABLE {loading}')
    else:
        cursor.execute(f'INSERT INTO {target} SELECT * FROM {loading}')
        cursor.execute(f'DROP TABLE {loading}')
    return loaded
