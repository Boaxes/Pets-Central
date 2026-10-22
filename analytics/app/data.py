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
        frame = st.connection('marts').query(sql, ttl=0)
    frame.columns = [column.lower() for column in frame.columns]  # Snowflake returns them upper case
    return frame


def quoted(value):
    """A string literal for SQL. Only used for values the app itself offers in a select box."""
    return "'" + str(value).replace("'", "''") + "'"


def titled(frame):
    """Column names as headings, for charts and tables: department_name becomes Department Name."""
    return frame.rename(columns=lambda column: column.replace('_', ' ').title())
