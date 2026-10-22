"""A first check on the SQL the assistant writes, before it reaches the database.

This is not what keeps the data safe. The database login does that: it can only read the store_data views, every
session is read-only, and queries time out. This check turns the obvious mistakes into clear messages the model can
act on, and blocks a few functions that have no business in a report.
"""

import re


class UnsafeSql(ValueError):
    pass


# Statements and clauses that change data or session state, and functions that act on the server.
FORBIDDEN = {
    'insert', 'update', 'delete', 'merge', 'create', 'alter', 'drop', 'truncate', 'grant', 'revoke', 'copy', 'call',
    'do', 'execute', 'prepare', 'deallocate', 'listen', 'notify', 'unlisten', 'lock', 'vacuum', 'analyze', 'refresh',
    'set', 'reset', 'begin', 'commit', 'rollback', 'savepoint', 'discard', 'into',
    'set_config', 'pg_sleep', 'pg_sleep_for', 'pg_sleep_until', 'pg_terminate_backend', 'pg_cancel_backend',
    'pg_reload_conf', 'pg_read_file', 'pg_read_binary_file', 'pg_ls_dir', 'pg_stat_file', 'lo_import', 'lo_export',
    'dblink', 'query_to_xml', 'query_to_xml_and_xmlschema', 'cursor_to_xml', 'table_to_xml', 'schema_to_xml',
    'database_to_xml',
}

_TOKEN = re.compile(r"""
    (?P<line_comment>--[^\n]*)
  | (?P<block_comment>/\*.*?\*/)
  | (?P<dollar>\$(?P<tag>[A-Za-z_]*)\$.*?\$(?P=tag)\$)
  | (?P<escape_string>[Ee]'(?:[^'\\]|\\.|'')*')
  | (?P<string>'(?:[^']|'')*')
""", re.VERBOSE | re.DOTALL)


def _code_only(text):
    """The query with comments and string literals blanked out, so words inside them don't count."""
    return _TOKEN.sub(' ', text)


def check_sql(text):
    """Returns the query ready to run, or raises UnsafeSql with a message for the model."""
    query = (text or '').strip()
    while query.endswith(';'):
        query = query[:-1].rstrip()
    if not query:
        raise UnsafeSql('The query is empty.')
    code = _code_only(query)
    if "'" in code or '/*' in code:
        raise UnsafeSql('The query has an unclosed string or comment.')
    if ';' in code:
        raise UnsafeSql('Send one statement at a time, without semicolons.')
    if re.search(r'\bu&', code, re.IGNORECASE):
        raise UnsafeSql('Unicode-escaped names (U&"...") are not allowed.')
    words = re.findall(r'[a-z_][a-z0-9_$]*', code.lower())
    if not words or words[0] not in ('select', 'with'):
        raise UnsafeSql('Only SELECT queries can run. WITH ... SELECT is fine.')
    used = sorted(set(words) & FORBIDDEN)
    if used:
        raise UnsafeSql(f'The query uses {", ".join(used).upper()}, which is not allowed here. Only read data.')
    return query
