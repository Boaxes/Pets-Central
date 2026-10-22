from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg import sql

from assistant.grants import grant_read_access


class Command(BaseCommand):
    help = ("Creates or updates the Store Assistant's read-only database login from ASSISTANT_DB_USER and "
            "ASSISTANT_DB_PASSWORD. Locally scripts/setup_local_db.ps1 does this; in Azure, where the database "
            "is private, the manage job runs it before migrate.")

    def handle(self, *args, **options):
        role, password = settings.ASSISTANT_DB_USER, settings.ASSISTANT_DB_PASSWORD
        if not password:
            raise CommandError('ASSISTANT_DB_PASSWORD is not set.')
        ident = sql.Identifier(role)
        with connection.cursor() as cursor:
            cursor.execute('SELECT EXISTS (SELECT FROM pg_roles WHERE rolname = %s)', [role])
            if not cursor.fetchone()[0]:
                cursor.execute(sql.SQL('CREATE ROLE {} LOGIN').format(ident).as_string(cursor.connection))
            # The same settings as scripts/setup_local_db.sql: read-only sessions that stop runaway queries. A new
            # role is already not a superuser and can't create databases or roles; only a superuser could say so.
            for statement, values in (
                ('ALTER ROLE {} WITH LOGIN NOINHERIT CONNECTION LIMIT 20 PASSWORD {}', [password]),
                ('ALTER ROLE {} SET default_transaction_read_only = on', []),
                ('ALTER ROLE {} SET statement_timeout = {}', ['5s']),
                ('ALTER ROLE {} SET idle_in_transaction_session_timeout = {}', ['30s']),
                ('ALTER ROLE {} SET search_path = store_data', []),
            ):
                query = sql.SQL(statement).format(ident, *(sql.Literal(v) for v in values))
                cursor.execute(query.as_string(cursor.connection))
            cursor.execute("SELECT EXISTS (SELECT FROM pg_namespace WHERE nspname = 'store_data')")
            views_exist = cursor.fetchone()[0]
        if views_exist:  # Otherwise migrate grants access when it creates the views.
            grant_read_access(connection)
        self.stdout.write(self.style.SUCCESS(f'{role} is ready.'))
