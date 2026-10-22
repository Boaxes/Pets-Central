"""Turns a question into SQL over the marts. In Snowflake, Cortex Analyst does it with semantic_model.yaml from the
app's files. Anywhere else, Claude does it with the same file. Either way the result is a short interpretation of
the question and one SELECT statement, which the Ask page runs with the app's own read-only connection."""

import json
from pathlib import Path

import streamlit as st

from data import IN_SNOWFLAKE, dialect

SEMANTIC_MODEL = Path(__file__).parent / 'semantic_model.yaml'
CLAUDE_MODEL = 'claude-opus-5-5'


def ask(question):
    """Returns (interpretation, sql); sql is None when the question can't be answered from the marts."""
    return _cortex(question) if IN_SNOWFLAKE else _claude(question)


def _cortex(question):
    # The model is sent inline: the app's files live in the app itself, not on a stage Cortex can be pointed at.
    body = {
        'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': question}]}],
        'semantic_model': SEMANTIC_MODEL.read_text(encoding='utf-8'),
    }
    status, content = _cortex_request(body)
    if status >= 400:
        raise RuntimeError(content.get('message', 'Cortex Analyst returned an error.'))
    parts = content['message']['content']
    text = '\n\n'.join(part['text'] for part in parts if part['type'] == 'text')
    sql = next((part['statement'] for part in parts if part['type'] == 'sql'), None)
    suggestions = [s for part in parts if part['type'] == 'suggestions' for s in part['suggestions']]
    if suggestions:
        text += '\n\nTry instead: ' + '; '.join(suggestions)
    return text, sql


def _cortex_request(body):
    """Calls Cortex Analyst's REST API as the app's own session. The warehouse runtime offers _snowflake for this;
    the container runtime doesn't, so there the call goes out with the session's token."""
    path = '/api/v2/cortex/analyst/message'
    try:
        import _snowflake
    except ImportError:
        import requests

        from data import SESSION

        rest = SESSION.connection.rest
        response = requests.post(f'https://{SESSION.connection.host}{path}', json=body, timeout=60,
                                 headers={'Authorization': f'Snowflake Token="{rest.token}"'})
        return response.status_code, response.json()
    response = _snowflake.send_snow_api_request('POST', path, {}, {}, body, None, 60000)
    return response['status'], json.loads(response['content'])


ANSWER_SCHEMA = {
    'type': 'object',
    'properties': {
        'interpretation': {'type': 'string', 'description': 'One or two sentences: what the query answers.'},
        'sql': {'type': ['string', 'null'], 'description': 'One SELECT statement, or null if unanswerable.'},
    },
    'required': ['interpretation', 'sql'],
    'additionalProperties': False,
}


def _claude(question):
    import anthropic

    client = anthropic.Anthropic(api_key=st.secrets['ANTHROPIC_API_KEY'], timeout=90, max_retries=2)
    system = (
        "You answer questions about a pet store chain's data warehouse by writing one read-only SQL query in the "
        f'{dialect()} dialect. The tables are described by this semantic model; in SQL, name each table by its '
        "base_table's schema and table in lower case, such as marts.fct_sales, without the database. Use only the "
        'columns listed. Leave cancelled sales out unless asked. If the data cannot answer the question, set sql '
        'to null and say why in the interpretation.\n\n' + SEMANTIC_MODEL.read_text(encoding='utf-8')
    )
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8000,
        system=system,
        messages=[{'role': 'user', 'content': question}],
        output_config={'effort': 'low', 'format': {'type': 'json_schema', 'schema': ANSWER_SCHEMA}},
    )
    if response.stop_reason == 'refusal':
        return "This question can't be answered here.", None
    answer = json.loads(next(block.text for block in response.content if block.type == 'text'))
    return answer['interpretation'], answer['sql']
