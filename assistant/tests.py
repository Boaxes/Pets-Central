from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock, skipUnless

import psycopg
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Department, Product
from policies.models import Policy
from sales.models import Sale, SaleLine
from stores.models import Employee, Region, Store

from . import agent, store_data
from .models import Question, Scope
from .policy_search import split_sections
from .rendering import render_answer
from .sql_guard import UnsafeSql, check_sql


class SqlGuardTests(SimpleTestCase):
    def test_allows_selects(self):
        self.assertEqual(check_sql('select 1;'), 'select 1')
        check_sql('WITH t AS (SELECT 1 AS x) SELECT x FROM t')
        check_sql("SELECT * FROM sales WHERE coupon_code LIKE '%SPRING%'")
        # Words inside strings and comments don't count, and neither do column names that contain them.
        check_sql("SELECT 'delete; drop table' AS note -- update\nFROM store")
        check_sql('SELECT updated_count, offset_days FROM t')

    def test_rejects_other_statements(self):
        for query in ['DELETE FROM sales', 'UPDATE sales SET status = 1', 'SET ROLE pets_app', 'COPY sales TO stdout',
                      'EXPLAIN ANALYZE SELECT 1', 'SELECT 1; SELECT 2', 'SELECT * INTO copy_of_sales FROM sales', '']:
            with self.subTest(query), self.assertRaises(UnsafeSql):
                check_sql(query)

    def test_rejects_server_functions(self):
        for query in ["SELECT set_config('role', 'pets_app', false)", 'SELECT "set_config"(1)', 'SELECT pg_sleep(60)',
                      "SELECT query_to_xml('select 1', true, true, '')", 'SELECT U&"\\0073et_config"(1)',
                      "SELECT 'unclosed"]:
            with self.subTest(query), self.assertRaises(UnsafeSql):
                check_sql(query)


class RenderingTests(SimpleTestCase):
    SECTION = {'key': 'returns-and-refunds#2-receipts', 'title': 'Returns and Refunds', 'version': '2.0',
               'heading': '2. Receipts', 'url': '/policies/returns-and-refunds/#2-receipts'}

    def test_escapes_html_and_drops_links_and_images(self):
        html, _ = render_answer('<script>x</script> [click](javascript:alert(1)) ![a](https://evil.example/?d=1)', {})
        self.assertNotIn('<script>', html)
        self.assertNotIn('href', html)
        self.assertNotIn('<img', html)

    def test_cites_only_retrieved_sections(self):
        html, cited = render_answer('Yes. [[returns-and-refunds#2-receipts]] Also [[made-up#1-x]].',
                                    {self.SECTION['key']: self.SECTION})
        self.assertIn('href="/policies/returns-and-refunds/#2-receipts"', html)
        self.assertNotIn('made-up', html)
        self.assertEqual(cited, [self.SECTION])

    def test_a_list_right_under_a_line_is_a_list(self):
        html, _ = render_answer('**Bring:**\n- The receipt\n- A vet note\n\nSteps:\n1. Check\n2. Refund', {})
        self.assertIn('<ul>', html)
        self.assertIn('<li>A vet note</li>', html)
        self.assertIn('<ol>', html)

    def test_markdown_tables(self):
        html, _ = render_answer('| SKU | Units |\n|---|---|\n| DOG-1 | 4 |', {})
        self.assertIn('<table>', html)


class PolicySectionTests(TestCase):
    def test_sections_use_the_page_heading_ids(self):
        policy = Policy.objects.create(title='Returns and Refunds', category='returns', version='2.0',
                                       effective_on=date(2026, 1, 1), status='published', owner='Store Operations',
                                       summary='How returns work.', body='Intro.\n\n## 1. Time limits\n\n30 days.\n\n'
                                                                         '## 2. Receipts\n\nNeeded.\n')
        sections = split_sections(policy)
        html, _ = policy.render()
        self.assertEqual([s.key for s in sections], ['returns-and-refunds#1-time-limits', 'returns-and-refunds#2-receipts'])
        for section in sections:
            self.assertIn(f'id="{section.anchor}"', html)
        self.assertEqual(sections[1].body, 'Needed.')


def _store(code, name, state='WA'):
    region, _ = Region.objects.get_or_create(code='PA', defaults={'name': 'Pacific'})
    return Store.objects.create(store_code=code, name=name, region=region, address_line='1 Main St', city=name,
                                state=state, postal_code='00000', time_zone='America/Los_Angeles',
                                opened_on=date(2020, 1, 1))


def _sale(store, receipt, amount):
    product = Product.objects.first() or Product.objects.create(
        sku='DOG-1', name='Kibble', introduced_on=date(2020, 1, 1),
        category=Category.objects.create(name='Dry Food', department=Department.objects.create(code='DOG', name='Dogs')))
    sale = Sale.objects.create(receipt_number=receipt, store=store, sold_at=datetime(2026, 9, 30, 20, tzinfo=timezone.utc))
    SaleLine.objects.create(sale=sale, line_number=1, product=product, quantity=1, unit_price=Decimal(amount),
                            unit_cost=Decimal('1.00'))
    return sale


def _assistant_login_works():
    if not settings.ASSISTANT_DB_PASSWORD:
        return False
    db = connection.settings_dict
    try:
        psycopg.connect(host=db['HOST'] or 'localhost', port=db['PORT'] or '5432', dbname='postgres',
                        user=settings.ASSISTANT_DB_USER, password=settings.ASSISTANT_DB_PASSWORD,
                        connect_timeout=3).close()
    except psycopg.Error:
        return False
    return True


@skipUnless(_assistant_login_works(), "The assistant's database login isn't set up (scripts/setup_local_db.ps1).")
class StoreDataIsolationTests(TransactionTestCase):
    """Runs real SQL as the assistant's login, which must see one store's data and nothing else."""

    def setUp(self):
        self.seattle = _store('PC-0001', 'Seattle')
        self.fresno = _store('PC-0002', 'Fresno', 'CA')
        _sale(self.seattle, 'R-1', '10.00')
        _sale(self.fresno, 'R-2', '99.00')

    def query(self, store, sql):
        with store_data.store_session(store) as conn:
            return store_data.run_query(conn, sql)

    def test_sees_only_its_store(self):
        result = self.query(self.seattle, 'SELECT receipt_number, net_total FROM sales')
        self.assertEqual(result.rows, [['R-1', 10]])
        self.assertEqual(self.query(self.fresno, 'SELECT store_code FROM store').rows, [['PC-0002']])

    def test_times_are_on_the_store_clock(self):
        # 8 pm UTC on the 30th is 1 pm in Seattle.
        self.assertEqual(self.query(self.seattle, 'SELECT sold_at FROM sales').rows, [['2026-09-30 13:00']])

    def test_scope_is_removed_when_the_session_ends(self):
        self.query(self.seattle, 'SELECT 1')
        self.assertFalse(Scope.objects.exists())

    def test_cannot_read_tables_or_change_anything(self):
        with store_data.store_session(self.seattle) as conn:
            for sql in ['SELECT * FROM public.auth_user', 'SELECT * FROM public.sales_sale',
                        'SELECT * FROM public.assistant_scope']:
                with self.subTest(sql), self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    store_data.run_query(conn, sql)
            # Past the SQL check, the database itself still refuses.
            for statement in ['SET ROLE pets_app', "SELECT set_config('role', 'pets_app', false)"]:
                with self.subTest(statement), self.assertRaises(psycopg.Error), conn.transaction():
                    conn.execute(statement.replace('pets_app', connection.settings_dict['USER']))
            with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction), conn.transaction():
                conn.execute('CREATE TEMP TABLE scratch (n int)')
            with self.assertRaises(psycopg.Error), conn.transaction():
                conn.execute("UPDATE store_data.employees SET hourly_rate = 1")

    def test_slow_queries_stop(self):
        with store_data.store_session(self.seattle) as conn:
            with self.assertRaises(psycopg.errors.QueryCanceled), conn.transaction():
                conn.execute('SELECT pg_sleep(10)')

    def test_row_limit(self):
        result = self.query(self.seattle, 'SELECT generate_series(1, 500) AS n')
        self.assertEqual(len(result.rows), store_data.ROW_LIMIT)
        self.assertTrue(result.truncated)


def _message(stop_reason, content):
    usage = SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0)
    return SimpleNamespace(stop_reason=stop_reason, content=content, usage=usage)


class FakeClient:
    """Plays back Claude's side of a conversation and records each request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **request):
        self.requests.append({**request, 'messages': list(request['messages'])})
        return self.responses.pop(0)


@override_settings(ANTHROPIC_API_KEY='test', ASSISTANT_DB_PASSWORD='test')
class AgentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store = _store('PC-0001', 'Seattle')
        cls.user = User.objects.create_user('morgan', first_name='Morgan', last_name='Lee')

    def setUp(self):
        # No real assistant login here; StoreDataIsolationTests covers the database side.
        patcher = mock.patch.object(store_data, 'store_session')
        self.session = patcher.start()
        self.addCleanup(patcher.stop)

    def test_runs_sql_then_answers(self):
        tool_use = SimpleNamespace(type='tool_use', id='t1', name='run_sql',
                                   input={'sql': 'SELECT count(*) FROM sales', 'purpose': 'count sales'})
        client = FakeClient(_message('tool_use', [tool_use]),
                            _message('end_turn', [SimpleNamespace(type='text', text='You made **3** sales.')]))
        result = store_data.QueryResult(columns=['count'], rows=[[3]], truncated=False)
        with mock.patch.object(store_data, 'run_query', return_value=result) as run:
            question = agent.ask(self.store, self.user, 'How many sales?', client=client)
        self.session.assert_called_once_with(self.store)
        run.assert_called_once()
        self.assertEqual(question.outcome, Question.Outcome.ANSWERED)
        self.assertEqual(question.answer, 'You made **3** sales.')
        self.assertEqual(question.input_tokens, 200)
        call = question.tool_calls.get()
        self.assertTrue(call.ok)
        self.assertEqual(call.row_count, 1)
        # The second request carries the tool result back to Claude.
        tool_result = client.requests[1]['messages'][-1]['content'][0]
        self.assertEqual(tool_result['tool_use_id'], 't1')
        self.assertIn('"rows": [[3]]', tool_result['content'])
        self.assertFalse(tool_result['is_error'])

    def test_sql_errors_go_back_to_claude(self):
        tool_use = SimpleNamespace(type='tool_use', id='t1', name='run_sql',
                                   input={'sql': 'DELETE FROM sales', 'purpose': 'oops'})
        client = FakeClient(_message('tool_use', [tool_use]),
                            _message('end_turn', [SimpleNamespace(type='text', text='I can only read data.')]))
        question = agent.ask(self.store, self.user, 'Delete everything', client=client)
        call = question.tool_calls.get()
        self.assertFalse(call.ok)
        self.assertIn('Only SELECT', call.error)
        self.assertTrue(client.requests[1]['messages'][-1]['content'][0]['is_error'])

    def test_policy_search_is_offered_only_when_available(self):
        client = FakeClient(_message('end_turn', [SimpleNamespace(type='text', text='Hi.')]))
        agent.ask(self.store, self.user, 'Hello', client=client)
        request = client.requests[0]
        self.assertEqual([tool['name'] for tool in request['tools']], ['run_sql'])
        self.assertIn('Policy search is not available', request['system'])

        client = FakeClient(_message('end_turn', [SimpleNamespace(type='text', text='Hi.')]))
        with mock.patch('assistant.policy_search.is_available', return_value=True):
            agent.ask(self.store, self.user, 'Hello', client=client)
        self.assertEqual([tool['name'] for tool in client.requests[0]['tools']], ['run_sql', 'search_policies'])

    def test_refusal(self):
        client = FakeClient(_message('refusal', []))
        question = agent.ask(self.store, self.user, 'Something off-limits', client=client)
        self.assertEqual(question.outcome, Question.Outcome.DECLINED)

    @override_settings(ASSISTANT_DAILY_LIMIT=5, ASSISTANT_SITE_DAILY_LIMIT=3)
    def test_daily_limits(self):
        other = User.objects.create_user('sam')
        Question.objects.create(store=self.store, user=self.user, text='q', model='m', policy_search=False)
        self.assertEqual(agent.questions_left_today(self.user), 2)  # the site's limit is the tighter one
        for _ in range(2):
            Question.objects.create(store=self.store, user=other, text='q', model='m', policy_search=False)
        self.assertEqual(agent.questions_left_today(self.user), 0)
        with override_settings(ASSISTANT_SITE_DAILY_LIMIT=0):
            self.assertEqual(agent.questions_left_today(self.user), 4)


@override_settings(ANTHROPIC_API_KEY='', ASSISTANT_DB_PASSWORD='')
class AssistantPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seattle = _store('PC-0001', 'Seattle')
        cls.fresno = _store('PC-0002', 'Fresno', 'CA')
        cls.user = User.objects.create_user('morgan')
        cls.user.groups.add(Group.objects.create(name='Store Managers'))
        Employee.objects.create(store=cls.seattle, user=cls.user, employee_number='E1', first_name='Morgan',
                                last_name='Lee', role='store_manager', hourly_rate=Decimal('30.00'),
                                hired_on=date(2021, 1, 1))
        cls.fresno_question = Question.objects.create(store=cls.fresno, text='Fresno only', model='m',
                                                      policy_search=False)

    def setUp(self):
        self.client.force_login(self.user)

    def test_page_says_what_is_missing(self):
        response = self.client.get(reverse('assistant'))
        self.assertContains(response, 'ANTHROPIC_API_KEY is missing')
        self.assertContains(response, "Policy search isn't available")
        self.assertNotContains(response, 'Fresno only')

    def test_other_stores_questions_are_hidden(self):
        response = self.client.get(reverse('assistant_question', args=[self.fresno_question.pk]))
        self.assertEqual(response.status_code, 404)

    @override_settings(ANTHROPIC_API_KEY='test', ASSISTANT_DB_PASSWORD='test')
    def test_asking_shows_the_answer(self):
        def fake_ask(store, user, text):
            return Question.objects.create(store=store, user=user, text=text, answer='**42** sales.', model='m',
                                           policy_search=False, outcome=Question.Outcome.ANSWERED)

        with mock.patch.object(agent, 'ask', side_effect=fake_ask):
            response = self.client.post(reverse('assistant'), {'question': 'How many?'}, HTTP_HX_REQUEST='true')
        self.assertContains(response, '<strong>42</strong> sales.')
        self.assertIn('/assistant/', response['HX-Push-Url'])
