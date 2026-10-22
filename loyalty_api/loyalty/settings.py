"""Configuration from environment variables. Locally they come from .env; on Azure they are Application settings."""

import json
import os
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')


@dataclass(frozen=True)
class Settings:
    db_path: Path
    api_keys: frozenset
    requests_per_second: float = 20.0
    burst: int = 40
    # Share of requests that fail with 503, as real vendor APIs sometimes do. Clients must retry.
    failure_rate: float = 0.0
    # A public key for the docs page's "Try It Out", with a low limit of its own. Unset, there is none.
    demo_key: str = ''
    demo_per_second: float = 2.0
    demo_burst: int = 5

    @classmethod
    def from_env(cls):
        return cls(
            db_path=_database_path(),
            api_keys=frozenset(k.strip() for k in os.environ['LOYALTY_API_KEYS'].split(',') if k.strip()),
            requests_per_second=float(os.environ.get('LOYALTY_RATE_LIMIT', '20')),
            burst=int(os.environ.get('LOYALTY_RATE_BURST', '40')),
            failure_rate=float(os.environ.get('LOYALTY_FAILURE_RATE', '0.02')),
            demo_key=os.environ.get('LOYALTY_DEMO_KEY', '').strip(),
        )


def _database_path():
    """LOYALTY_DB_PATH locally. On Azure, LOYALTY_DB_URL (a private blob) is downloaded once per instance."""
    if path := os.environ.get('LOYALTY_DB_PATH'):
        return (ROOT / path).resolve()  # A relative path is relative to the loyalty_api folder.
    target = Path(tempfile.gettempdir()) / 'loyalty.sqlite3'
    if not target.exists():
        request = urllib.request.Request(os.environ['LOYALTY_DB_URL'], headers={
            'Authorization': f'Bearer {_storage_token()}', 'x-ms-version': '2023-11-03'})
        partial = target.with_suffix('.partial')
        with urllib.request.urlopen(request) as response, open(partial, 'wb') as out:
            out.write(response.read())
        partial.replace(target)
    return target


def _storage_token():
    """A token for Blob Storage from the Function App's own managed identity, so the blob stays private and no key
    or signed link exists. Azure Functions provides IDENTITY_ENDPOINT and IDENTITY_HEADER."""
    request = urllib.request.Request(
        f"{os.environ['IDENTITY_ENDPOINT']}?resource=https://storage.azure.com/&api-version=2019-08-01",
        headers={'X-IDENTITY-HEADER': os.environ['IDENTITY_HEADER']})
    with urllib.request.urlopen(request) as response:
        return json.load(response)['access_token']
