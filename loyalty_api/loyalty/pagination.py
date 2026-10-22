"""Keyset pagination for v2: rows in (time, id) order, with an opaque cursor naming the last row returned."""

import base64
import json
import sqlite3
from datetime import datetime, timezone

from fastapi import HTTPException


def encode_cursor(time_value, row_id):
    return base64.urlsafe_b64encode(json.dumps([time_value, row_id]).encode()).decode().rstrip('=')


def decode_cursor(cursor):
    try:
        time_value, row_id = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
        return str(time_value), int(row_id)
    except (ValueError, TypeError):
        raise HTTPException(400, detail={'error': 'invalid_cursor', 'message': 'The cursor is not valid.'})


def utc_text(moment: datetime):
    """The database's UTC text format, for comparing against stored times."""
    if moment.tzinfo is None:
        raise HTTPException(400, detail={'error': 'invalid_timestamp',
                                         'message': 'updated_since needs a time zone, such as 2026-01-01T00:00:00Z.'})
    return moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def fetch_page(db: sqlite3.Connection, table, time_column, *, updated_since=None, cursor=None, limit=500,
               filters=None):
    """One page of rows changed at or after updated_since, after the cursor. Returns (rows, next_cursor)."""
    where, params = [], []
    if updated_since is not None:
        where.append(f'{time_column} >= ?')
        params.append(utc_text(updated_since))
    if cursor:
        after_time, after_id = decode_cursor(cursor)
        where.append(f'({time_column} > ? OR ({time_column} = ? AND id > ?))')
        params += [after_time, after_time, after_id]
    for column, value in (filters or {}).items():
        where.append(f'{column} = ?')
        params.append(value)
    sql = f'SELECT * FROM {table}'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += f' ORDER BY {time_column}, id LIMIT ?'
    rows = db.execute(sql, params + [limit + 1]).fetchall()
    if len(rows) > limit:
        rows = rows[:limit]
        return rows, encode_cursor(rows[-1][time_column], rows[-1]['id'])
    return rows, None
