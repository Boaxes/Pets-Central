from django.core.management.base import BaseCommand, CommandError

from datagen import load
from datagen.context import Context
from datagen.timeline import END, SIZES, START


class Command(BaseCommand):
    help = (f'Generate {START:%B %Y} to {END:%B %Y} of store history and bulk-load it into the database. '
            'The loyalty platform database and the truth files are written to data/generated/<size>/.')

    def add_arguments(self, parser):
        parser.add_argument('--size', choices=SIZES, default='small',
                            help='How much data: tiny, small, medium or full (about 10 million sale lines).')
        parser.add_argument('--seed', type=int, default=42, help='The same seed and size always give the same data.')
        parser.add_argument('--reset', action='store_true',
                            help='Delete all store data first. Admin logins are kept.')

    def handle(self, *args, size, seed, reset, **options):
        if load.has_data():
            if not reset:
                raise CommandError('The database already has store data. Run again with --reset to replace it.')
            self.stdout.write('Deleting existing store data')
            load.truncate()
        ctx = Context(SIZES[size], seed)
        ctx.log = self.stdout.write
        load.generate(ctx, output_dir=load.default_output_dir(size))
