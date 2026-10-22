"""Copy new and changed loyalty platform data from its API into Snowflake's RAW schema.

Each v2 endpoint lands in its own table, LOYALTY__<NAME>, as raw JSON (a VARIANT column) next to the record's id,
the time it changed and the run's batch id. Landing the JSON untouched means a renamed or added field never breaks
the load; dbt does the parsing.

A run asks each endpoint for rows that changed since the newest change already in RAW, less an hour of overlap.
The API filters on when the platform received a row, so events that happened days earlier but arrived late are
still picked up; the overlap only covers rows written out of order. Rows read twice are harmless: dbt keeps the
latest version of each id.

The client honors 429 Retry-After and retries 503s and network errors with backoff. The five endpoints download
in parallel; then each loads through a table stage into a loading table, its row count is checked against what was
downloaded, and only then is it appended to RAW.

    uv run python -m pipeline.load_loyalty
    uv run python -m pipeline.load_loyalty --endpoints members campaigns
"""

import argparse
import gzip
import json
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta

import httpx

from .connections import connect_snowflake
from .snowflake_io import EXPORT_DIR, log, publish, table_exists, upload

TARGET_PREFIX = 'LOYALTY__'
FILE_FORMAT = 'JSON_GZ'
OVERLAP = timedelta(hours=1)
PAGE_SIZE = 1000
RECORDS_PER_FILE = 200_000
MAX_ATTEMPTS = 8
RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class Endpoint:
    name: str
    path: str
    id_field: str
    changed_field: str  # What the API's updated_since filters on.

    @property
    def target(self):
        return TARGET_PREFIX + self.name.upper()


ENDPOINTS = [
    Endpoint('members', '/v2/members', 'member_id', 'updated_at'),
    Endpoint('campaigns', '/v2/campaigns', 'campaign_id', 'updated_at'),
    Endpoint('points_transactions', '/v2/points-transactions', 'transaction_id', 'recorded_at'),
    Endpoint('email_events', '/v2/email-events', 'event_id', 'recorded_at'),
    Endpoint('coupon_redemptions', '/v2/coupon-redemptions', 'redemption_id', 'recorded_at'),
]


class LoyaltyClient:
    """A small client for the loyalty API that pages with cursors and retries what is worth retrying."""

    def __init__(self, base_url, api_key, transport=None, sleep=time.sleep):
        self.http = httpx.Client(base_url=base_url, headers={'X-API-Key': api_key}, timeout=60,
                                 transport=transport)
        self.sleep = sleep
        self.retries = 0
        self._lock = threading.Lock()

    def get(self, path, params=None):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self.http.get(path, params=params)
            except httpx.TransportError:
                if attempt == MAX_ATTEMPTS:
                    raise
                self._wait(attempt, None)
                continue
            if response.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                self._wait(attempt, response.headers.get('Retry-After'))
                continue
            response.raise_for_status()
            return response.json()

    def pages(self, path, updated_since=None):
        params = {'limit': PAGE_SIZE}
        if updated_since is not None:
            params['updated_since'] = updated_since.isoformat()
        while True:
            body = self.get(path, params)
            yield body['data']
            if not body['next_cursor']:
                return
            params['cursor'] = body['next_cursor']

    def _wait(self, attempt, retry_after):
        with self._lock:
            self.retries += 1
        self.sleep(float(retry_after) if retry_after else min(30.0, 0.5 * 2 ** (attempt - 1)))


def ensure_file_format(sf):
    sf.cursor().execute(f"""
        CREATE FILE FORMAT IF NOT EXISTS {FILE_FORMAT} TYPE = JSON COMPRESSION = GZIP
        COMMENT = 'Newline-delimited JSON, one API record per line'""")


def changed_since(sf, endpoint):
    """Where this run starts for an endpoint: the newest change in RAW less the overlap, or None on the first run."""
    if not table_exists(sf, endpoint.target):
        return None
    newest = sf.cursor().execute(f'SELECT MAX(CHANGED_AT) FROM {endpoint.target}').fetchone()[0]
    return newest - OVERLAP if newest else None


def download(client, endpoint, updated_since):
    """Write every changed record to gzipped newline-delimited JSON files. Returns (files, record count)."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    files, count, out = [], 0, None
    for page in client.pages(endpoint.path, updated_since):
        for record in page:
            if out is None or count % RECORDS_PER_FILE == 0 and count:
                if out is not None:
                    out.close()
                files.append(EXPORT_DIR / f'loyalty_{endpoint.name}_{len(files) + 1:04d}.json.gz')
                out = gzip.open(files[-1], 'wt', encoding='utf-8', compresslevel=5)
            out.write(json.dumps(record, separators=(',', ':')) + '\n')
            count += 1
    if out is not None:
        out.close()
    return files, count


def load(sf, endpoint, files, expected, batch_id):
    loading = endpoint.target + '__LOADING'
    cursor = sf.cursor()
    cursor.execute(f"""CREATE OR REPLACE TABLE {loading} (
        RECORD VARIANT, RECORD_ID VARCHAR, CHANGED_AT TIMESTAMP_TZ, _BATCH_ID VARCHAR,
        _LOADED_AT TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP())""")
    for path in files:
        upload(cursor, path, loading)
    cursor.execute(f"""
        COPY INTO {loading} (RECORD, RECORD_ID, CHANGED_AT, _BATCH_ID)
        FROM (SELECT $1, $1:{endpoint.id_field}::VARCHAR, $1:{endpoint.changed_field}::TIMESTAMP_TZ, '{batch_id}'
              FROM @%{loading})
        FILE_FORMAT = (FORMAT_NAME = {FILE_FORMAT}) PURGE = TRUE ON_ERROR = ABORT_STATEMENT""")
    publish(sf, loading, endpoint.target, expected, endpoint.name)


def summary(sf, endpoints, fetched):
    print(f'{"endpoint":22} {"this run":>10} {"rows in RAW":>12} {"distinct ids":>13}')
    for endpoint in endpoints:
        rows, ids = sf.cursor().execute(
            f'SELECT COUNT(*), COUNT(DISTINCT RECORD_ID) FROM {endpoint.target}').fetchone()
        print(f'{endpoint.name:22} {fetched.get(endpoint.name, 0):>10,} {rows:>12,} {ids:>13,}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--endpoints', nargs='+', choices=[e.name for e in ENDPOINTS],
                        help='Load only these endpoints.')
    args = parser.parse_args(argv)
    endpoints = [e for e in ENDPOINTS if not args.endpoints or e.name in args.endpoints]

    try:
        run(endpoints)
    except httpx.TransportError:
        sys.exit(f"Can't reach the loyalty API at {os.environ['LOYALTY_API_URL']}. Start it first: "
                 'in loyalty_api/, run uv run uvicorn asgi:app --port 8001')
    return 0


def run(endpoints=ENDPOINTS):
    """Loads each endpoint's changes into RAW and returns the number of records loaded per endpoint name."""
    client = LoyaltyClient(os.environ['LOYALTY_API_URL'], os.environ['LOYALTY_API_KEY'])
    client.get('/health')
    batch_id = uuid.uuid4().hex
    with connect_snowflake() as sf:
        ensure_file_format(sf)
        starts = {e.name: changed_since(sf, e) for e in endpoints}
        for e in endpoints:
            log(f'{e.name}: changes since {starts[e.name] or "the beginning"}')

        with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
            downloads = {e.name: pool.submit(download, client, e, starts[e.name]) for e in endpoints}
            results = {}
            for e in endpoints:
                results[e.name] = downloads[e.name].result()
                log(f'{e.name}: downloaded {results[e.name][1]:,} records')

        for e in endpoints:
            files, count = results[e.name]
            if count:
                load(sf, e, files, count, batch_id)
                log(f'{e.name}: {count:,} records -> {e.target}')
            else:
                log(f'{e.name}: nothing new')
        log(f'Batch {batch_id} done; {client.retries} requests were retried.')
        counts = {name: count for name, (_, count) in results.items()}
        summary(sf, endpoints, counts)
    return counts


if __name__ == '__main__':
    sys.exit(main())
