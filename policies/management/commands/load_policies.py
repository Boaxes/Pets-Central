from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from policies.models import Policy

SEED_DIR = Path(__file__).resolve().parents[2] / 'seed'


def parse(path):
    """A seed file is 'key: value' lines, a '---' line, then the markdown body."""
    header, body = path.read_text(encoding='utf-8').split('\n---\n', 1)
    fields = dict(line.split(': ', 1) for line in header.strip().splitlines())
    return fields, body.strip() + '\n'


class Command(BaseCommand):
    help = ('Load the starting set of corporate policies from policies/seed/. After this the database is the source '
            'of truth: corporate edits policies in the admin.')

    @transaction.atomic
    def handle(self, *args, **options):
        for path in sorted(SEED_DIR.glob('*.md')):
            fields, body = parse(path)
            # A newer published version of the same policy replaces the old one, which is kept as superseded.
            Policy.objects.filter(slug=path.stem, status=Policy.Status.PUBLISHED).exclude(
                version=fields['version']).update(status=Policy.Status.SUPERSEDED)
            policy, created = Policy.objects.update_or_create(
                slug=path.stem, version=fields['version'],
                defaults={
                    'title': fields['title'], 'category': fields['category'],
                    'effective_on': date.fromisoformat(fields['effective_on']), 'owner': fields['owner'],
                    'applies_to_states': fields.get('applies_to_states', ''), 'summary': fields['summary'],
                    'body': body, 'status': Policy.Status.PUBLISHED,
                },
            )
            self.stdout.write(f'{"Added" if created else "Updated"} {policy}')
