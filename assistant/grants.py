from django.conf import settings
from psycopg import sql


def grant_read_access(connection):
    """Lets the assistant's login read the store_data views, if the login exists. Returns whether it did."""
    role = settings.ASSISTANT_DB_USER
    with connection.cursor() as cursor:
        cursor.execute('SELECT EXISTS (SELECT FROM pg_roles WHERE rolname = %s)', [role])
        if not cursor.fetchone()[0]:
            return False
        ident = sql.Identifier(role)
        for statement in (
            'GRANT USAGE ON SCHEMA store_data TO {}',
            'GRANT SELECT ON ALL TABLES IN SCHEMA store_data TO {}',
            # Views added by later migrations are readable too.
            'ALTER DEFAULT PRIVILEGES IN SCHEMA store_data GRANT SELECT ON TABLES TO {}',
        ):
            cursor.execute(sql.SQL(statement).format(ident).as_string(cursor.connection))
    return True
