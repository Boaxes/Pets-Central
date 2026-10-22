import datetime

import streamlit as st

from ask import ask
from data import IN_SNOWFLAKE, query, titled

st.set_page_config(page_title='Ask', page_icon='🐾', layout='wide')
st.title('Ask')
engine = 'Cortex Analyst' if IN_SNOWFLAKE else 'Claude'
st.caption(f'{engine} turns a question into SQL over the marts, using the semantic model that describes them. '
           'The SQL runs read-only, and you see the query and its result.')

# A visitor to the demo gets a few questions per session, and all visitors together a few a day, since the API key
# has no spend limit. Inside Snowflake, every user is already signed in.
LIMIT = None if IN_SNOWFLAKE else 10
DAILY_LIMIT = None if IN_SNOWFLAKE else 100
asked = st.session_state.setdefault('questions_asked', 0)


@st.cache_resource
def asked_by_day():
    """Questions asked on each day, shared by every session in this app process."""
    return {}


today = datetime.date.today()
asked_today = asked_by_day().get(today, 0)

examples = ['Which region had the highest gross margin rate last year?',
            'How many repeat customers are loyalty members?',
            'What were the top 5 departments by revenue in 2025?']
question = st.text_input('Question', placeholder=examples[0])
st.caption('For example: ' + ' / '.join(examples))

if LIMIT is not None and asked >= LIMIT:
    st.warning(f'That is the limit of {LIMIT} questions for this visit. Reload the page later to ask more.')
elif DAILY_LIMIT is not None and asked_today >= DAILY_LIMIT:
    st.warning("Today's limit of questions has been reached. Ask will be back tomorrow.")
elif st.button('Ask', type='primary', disabled=not question):
    st.session_state.questions_asked = asked + 1
    asked_by_day()[today] = asked_today + 1
    with st.spinner(f'Asking {engine}...'):
        try:
            interpretation, sql = ask(question)
        except Exception as error:
            st.error(f'{engine} could not answer: {error}')
            st.stop()
    st.markdown(interpretation)
    if sql:
        if not sql.lstrip().lower().startswith(('select', 'with')):
            st.error('The generated statement was not a query, so it was not run.')
            st.stop()
        st.code(sql, language='sql')
        try:
            result = query(sql)
        except Exception as error:
            st.error(f'The query failed: {error}')
            st.stop()
        st.dataframe(titled(result.head(1000)), hide_index=True, use_container_width=True)
        if len(result) > 1000:
            st.caption(f'Showing 1,000 of {len(result):,} rows.')
