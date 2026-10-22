import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from loyalty.main import create_app
from loyalty.settings import Settings

SCHEMA = Path(__file__).resolve().parent.parent / 'loyalty' / 'schema.sql'
KEY = {'X-API-Key': 'test-key'}


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / 'loyalty.sqlite3'
    db = sqlite3.connect(path)
    db.executescript(SCHEMA.read_text())
    for i in range(1, 8):
        db.execute(
            'INSERT INTO members VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [i, f'LM{i:010X}', f'First{i}', f'Last{i}', f'person{i}@inbox.example', '(206) 555-01%02d' % i,
             '+120655501%02d' % i, '98101', 'PC0001', 'America/Los_Angeles', 'DOG,CAT', 1, 'bronze', 'active',
             '2024-01-01T08:30:00Z', None, 10 * i,
             # Rows 3 and 4 share an updated_at, to check the cursor handles ties.
             f'2024-02-0{min(i, 3) if i != 4 else 3}T00:00:00Z'])
    db.execute("INSERT INTO points_transactions VALUES (1, 'LM0000000001', 'earn', 43, 43.99, 'PC0001', "
               "'2024-01-05 18:30:00', '2024-01-06T02:45:00Z')")
    db.execute("INSERT INTO points_transactions VALUES (2, 'LM0000000001', 'earn', 12, 12.50, 'PC0001', "
               "'2024-01-02 10:00:00', '2024-01-09T12:00:00Z')")  # Arrived a week late.
    db.commit()
    db.close()
    return path


def client(db_path, **overrides):
    settings = Settings(db_path=db_path, api_keys=frozenset({'test-key'}), **overrides)
    return TestClient(create_app(settings))


def test_health_needs_no_key(db_path):
    assert client(db_path).get('/health').json() == {'status': 'ok'}


def test_requests_need_a_valid_key(db_path):
    api = client(db_path)
    assert api.get('/v2/members').status_code == 401
    assert api.get('/v2/members', headers={'X-API-Key': 'wrong'}).status_code == 401


def test_v2_cursor_pages_return_every_member_once_even_with_ties(db_path):
    api = client(db_path)
    seen, cursor = [], None
    while True:
        params = {'limit': 2} | ({'cursor': cursor} if cursor else {})
        body = api.get('/v2/members', params=params, headers=KEY).json()
        seen += [m['member_id'] for m in body['data']]
        cursor = body['next_cursor']
        assert body['has_more'] == (cursor is not None)
        if not cursor:
            break
    assert sorted(seen) == [f'LM{i:010X}' for i in range(1, 8)]


def test_updated_since_filters_and_needs_a_time_zone(db_path):
    api = client(db_path)
    body = api.get('/v2/members', params={'updated_since': '2024-02-03T00:00:00Z'}, headers=KEY).json()
    assert len(body['data']) == 5
    assert api.get('/v2/members', params={'updated_since': '2024-02-03T00:00:00'}, headers=KEY).status_code == 400


def test_late_points_are_found_by_when_they_were_recorded(db_path):
    api = client(db_path)
    body = api.get('/v2/points-transactions', params={'updated_since': '2024-01-08T00:00:00Z'}, headers=KEY).json()
    assert [t['transaction_id'] for t in body['data']] == [2]
    assert body['data'][0]['occurred_at'] == '2024-01-02 10:00:00'  # Local store time, no offset.


def test_v1_uses_old_field_names_local_times_and_page_numbers(db_path):
    response = client(db_path).get('/v1/members', params={'page': 2, 'page_size': 3}, headers=KEY)
    body = response.json()
    assert response.headers['Deprecation'] == 'true'
    assert (body['page'], body['page_size'], body['total']) == (2, 3, 7)
    member = body['members'][0]
    assert member['name'] == 'Last4, First4'
    assert member['email_address'] == 'person4@inbox.example'
    assert member['phone'] == '(206) 555-0104'
    assert member['signup_date'] == '01/01/2024 00:30'  # 08:30 UTC is 00:30 in Seattle in January.


def test_v2_member_by_id(db_path):
    api = client(db_path)
    member = api.get('/v2/members/LM0000000002', headers=KEY).json()
    assert member['pet_types'] == ['DOG', 'CAT'] and member['email_opt_in'] is True
    assert api.get('/v2/members/nobody', headers=KEY).status_code == 404


def test_rate_limit_answers_429_with_retry_after(db_path):
    api = client(db_path, requests_per_second=0.001, burst=2)
    statuses = [api.get('/v2/campaigns', headers=KEY).status_code for _ in range(3)]
    assert statuses == [200, 200, 429]
    assert int(api.get('/v2/campaigns', headers=KEY).headers['Retry-After']) >= 1


def test_failures_answer_503(db_path):
    response = client(db_path, failure_rate=1.0).get('/v2/campaigns', headers=KEY)
    assert response.status_code == 503 and response.headers['Retry-After'] == '1'


def test_bad_cursor_is_a_400(db_path):
    assert client(db_path).get('/v2/members', params={'cursor': 'nonsense'}, headers=KEY).status_code == 400


def test_demo_key_has_its_own_lower_limit(db_path):
    api = client(db_path, demo_key='demo', demo_per_second=0.001, demo_burst=2)
    demo = [api.get('/v2/campaigns', headers={'X-API-Key': 'demo'}).status_code for _ in range(3)]
    assert demo == [200, 200, 429]
    assert api.get('/v2/campaigns', headers=KEY).status_code == 200  # The issued key is unaffected.
