import os

import httpx
from django.core.management.base import BaseCommand, CommandError

from config import managed_identity
from datagen import load
from datagen.timeline import SIZES


class Command(BaseCommand):
    help = ("Uploads the loyalty platform's data file made by generate_data to the vendor's private blob "
            "(LOYALTY_DATA_BLOB_URL), signed in with this container's managed identity (AZURE_CLIENT_ID). "
            "In Azure the manage job runs it right after generate_data.")

    def add_arguments(self, parser):
        parser.add_argument('--size', choices=SIZES, default='small', help='The size generate_data was run with.')

    def handle(self, *args, size, **options):
        if not os.environ.get('LOYALTY_DATA_BLOB_URL'):
            raise CommandError('LOYALTY_DATA_BLOB_URL is not set; this command runs in the Azure manage job.')
        path = load.default_output_dir(size) / 'loyalty.sqlite3'
        if not path.exists():
            raise CommandError(f'{path} does not exist. Run generate_data --size {size} first.')
        with open(path, 'rb') as data:
            response = httpx.put(os.environ['LOYALTY_DATA_BLOB_URL'], content=data, timeout=600, headers={
                'Authorization': f"Bearer {managed_identity.token('https://storage.azure.com/')}", 'x-ms-version': '2023-11-03',
                'x-ms-blob-type': 'BlockBlob'})
        if response.status_code != 201:
            raise CommandError(f'Upload failed: {response.status_code} {response.text[:300]}')
        self.stdout.write(self.style.SUCCESS(f'Uploaded {path.stat().st_size:,} bytes.'))

