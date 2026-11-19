"""Where the app's data comes from. In Streamlit in Snowflake, the app's own session, running as the role that owns
the app (PETS_REPORTER, which can read the marts and nothing else). Anywhere else, the `marts` connection in
.streamlit/secrets.toml: the stand-in's Postgres copy of the marts, or Snowflake for local development.

The SQL in the pages is written to run unchanged on both Snowflake and Postgres: tables are named `marts.<table>`,
sums are cast with ::float, and there are no dialect-only functions.
"""

import streamlit as st

try:
    from snowflake.snowpark.context import get_active_session

    SESSION = get_active_session()
except Exception:  # Not running in Snowflake.
    SESSION = None

IN_SNOWFLAKE = SESSION is not None


def dialect():
    if IN_SNOWFLAKE:
        return 'snowflake'
    return 'snowflake' if st.secrets['connections']['marts'].get('type') == 'snowflake' else 'postgres'


@st.cache_data(ttl=3600, show_spinner='Querying the warehouse...')
def query(sql):
    if IN_SNOWFLAKE:
        frame = SESSION.sql(sql).to_pandas()
    else:
        frame = _query_marts(sql)
    frame.columns = [column.lower() for column in frame.columns]  # Snowflake returns them upper case
    return frame


def _query_marts(sql):
    """Runs a query on the `marts` connection, reconnecting once if the connection has gone stale.

    The demo's Postgres (Neon) closes connections that sit idle, and the pool can hand back a dead one, so the
    first query after a quiet spell fails ("Can't reconnect until invalid transaction is rolled back"). A fresh
    connection then works, so on a connection error the connection is reset and the query tried once more. Any
    other error, such as bad SQL, is raised as it is.
    """
    try:
        return st.connection('marts').query(sql, ttl=0)
    except Exception as error:
        if not _is_connection_error(error):
            raise
        st.connection('marts').reset()
        return st.connection('marts').query(sql, ttl=0)


def _is_connection_error(error):
    """True if SQLAlchemy lost the connection. pandas wraps the error ("Execution failed on sql ..."), so this
    looks through the whole chain of causes."""
    from sqlalchemy import exc  # Only needed outside Snowflake, where sqlalchemy is installed.

    while error is not None:
        if isinstance(error, (exc.OperationalError, exc.InterfaceError, exc.PendingRollbackError)):
            return True
        error = error.__cause__ or error.__context__
    return False


def quoted(value):
    """A string literal for SQL. Only used for values the app itself offers in a select box."""
    return "'" + str(value).replace("'", "''") + "'"


def titled(frame):
    """Column names as headings, for charts and tables: department_name becomes Department Name."""
    return frame.rename(columns=lambda column: column.replace('_', ' ').title())
