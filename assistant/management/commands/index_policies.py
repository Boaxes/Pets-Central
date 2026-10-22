from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from assistant import policy_search


class Command(BaseCommand):
    help = "Builds the Store Assistant's policy search index: every published policy section, embedded for pgvector."

    def handle(self, *args, **options):
        if not policy_search.extension_installable():
            raise CommandError('This database server has no pgvector extension, so policy search is not available '
                               'here. The assistant will answer from store data only.')
        if not settings.AZURE_OPENAI_ENDPOINT:
            raise CommandError('AZURE_OPENAI_ENDPOINT is not set, so policy sections cannot be embedded.')
        count = policy_search.build_index()
        self.stdout.write(self.style.SUCCESS(f'Indexed {count} policy sections.'))
