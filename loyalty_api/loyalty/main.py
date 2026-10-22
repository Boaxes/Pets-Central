"""Pawprint Loyalty's API, for the Pets Central Rewards program it runs.

In the project's story Pawprint Loyalty is another company, so this behaves like a real vendor API: an API key,
rate limits, occasional 503s, paging, two versions with renamed fields, local times mixed with UTC, and events
that arrive days late. Loyalty members share no ID with Pets Central's store customers.
"""

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Response, Security
from fastapi.security import APIKeyHeader

from .limits import RateLimiter, authenticate, maybe_fail
from .pagination import fetch_page
from .schemas import (
    Campaign, CouponRedemption, EmailEvent, MembersV1Page, MemberV1, MemberV2, Page, PointsTransaction,
)
from .settings import Settings

UPDATED_SINCE = Query(None, description='Only rows changed or received at or after this time. Include a time zone.')
CURSOR = Query(None, description='The next_cursor from the previous page.')
LIMIT = Query(500, ge=1, le=1000)
API_KEY = Security(APIKeyHeader(name='X-API-Key', scheme_name='ApiKey', auto_error=False))


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(
        title='Pawprint Loyalty API',
        version='2.3.0',
        description=(
            'Pawprint Loyalty runs the Pets Central Rewards program. This API serves its loyalty members, points, '
            'campaigns, campaign emails and coupon redemptions. '
            'Send your key in the `X-API-Key` header. Limits: '
            f'{settings.requests_per_second:g} requests per second, bursts of {settings.burst}. '
            'v2 pages with cursors; v1 is deprecated.'
            + (f' The public demo key, filled in on this page, is limited to {settings.demo_per_second:g} requests '
               f'per second, bursts of {settings.demo_burst}.' if settings.demo_key else '')
        ),
    )
    limiter = RateLimiter(settings.requests_per_second, settings.burst)
    demo_limiter = RateLimiter(settings.demo_per_second, settings.demo_burst)

    def guard(x_api_key: str | None = API_KEY):
        authenticate(x_api_key, settings)
        (demo_limiter if x_api_key == settings.demo_key else limiter).check(x_api_key)
        maybe_fail(settings)

    def database():
        db = sqlite3.connect(f'file:{settings.db_path.as_posix()}?mode=ro', uri=True, check_same_thread=False)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @app.get('/health', tags=['status'])
    def health():
        return {'status': 'ok'}

    v2 = APIRouter(prefix='/v2', dependencies=[Depends(guard)])

    @v2.get('/members', response_model=Page[MemberV2], tags=['members'])
    def list_members(updated_since: datetime | None = UPDATED_SINCE, cursor: str | None = CURSOR,
                     limit: int = LIMIT, db=Depends(database)):
        rows, next_cursor = fetch_page(db, 'members', 'updated_at', updated_since=updated_since, cursor=cursor,
                                       limit=limit)
        return Page(data=[_member_v2(r) for r in rows], next_cursor=next_cursor, has_more=next_cursor is not None)

    @v2.get('/members/{member_id}', response_model=MemberV2, tags=['members'])
    def get_member(member_id: str, db=Depends(database)):
        row = db.execute('SELECT * FROM members WHERE member_id = ?', [member_id]).fetchone()
        if row is None:
            raise HTTPException(404, detail={'error': 'not_found', 'message': f'No member {member_id}.'})
        return _member_v2(row)

    @v2.get('/campaigns', response_model=Page[Campaign], tags=['campaigns'])
    def list_campaigns(updated_since: datetime | None = UPDATED_SINCE, cursor: str | None = CURSOR,
                       limit: int = LIMIT, db=Depends(database)):
        rows, next_cursor = fetch_page(db, 'campaigns', 'updated_at', updated_since=updated_since, cursor=cursor,
                                       limit=limit)
        data = [Campaign(campaign_id=r['id'], code=r['code'], name=r['name'], department=r['department_code'],
                         discount_percent=r['discount_percent'], starts_on=r['starts_on'], ends_on=r['ends_on'],
                         channel=r['channel'], updated_at=r['updated_at']) for r in rows]
        return Page(data=data, next_cursor=next_cursor, has_more=next_cursor is not None)

    @v2.get('/points-transactions', response_model=Page[PointsTransaction], tags=['points'])
    def list_points(updated_since: datetime | None = UPDATED_SINCE, cursor: str | None = CURSOR,
                    limit: int = LIMIT, db=Depends(database)):
        rows, next_cursor = fetch_page(db, 'points_transactions', 'recorded_at', updated_since=updated_since,
                                       cursor=cursor, limit=limit)
        data = [PointsTransaction(transaction_id=r['id'], member_id=r['member_id'], type=r['type'],
                                  points=r['points'], purchase_amount=r['purchase_amount'],
                                  store_code=r['store_code'], occurred_at=r['occurred_local'],
                                  recorded_at=r['recorded_at']) for r in rows]
        return Page(data=data, next_cursor=next_cursor, has_more=next_cursor is not None)

    @v2.get('/email-events', response_model=Page[EmailEvent], tags=['campaigns'])
    def list_email_events(campaign_id: int | None = None, updated_since: datetime | None = UPDATED_SINCE,
                          cursor: str | None = CURSOR, limit: int = LIMIT, db=Depends(database)):
        filters = {'campaign_id': campaign_id} if campaign_id is not None else None
        rows, next_cursor = fetch_page(db, 'email_events', 'recorded_at', updated_since=updated_since,
                                       cursor=cursor, limit=limit, filters=filters)
        data = [EmailEvent(event_id=r['id'], campaign_id=r['campaign_id'], member_id=r['member_id'],
                           sent_at=r['sent_at'], opened_at=r['opened_at'], clicked_at=r['clicked_at'],
                           unsubscribed=bool(r['unsubscribed']), recorded_at=r['recorded_at']) for r in rows]
        return Page(data=data, next_cursor=next_cursor, has_more=next_cursor is not None)

    @v2.get('/coupon-redemptions', response_model=Page[CouponRedemption], tags=['campaigns'])
    def list_redemptions(updated_since: datetime | None = UPDATED_SINCE, cursor: str | None = CURSOR,
                         limit: int = LIMIT, db=Depends(database)):
        rows, next_cursor = fetch_page(db, 'coupon_redemptions', 'recorded_at', updated_since=updated_since,
                                       cursor=cursor, limit=limit)
        data = [CouponRedemption(redemption_id=r['redemption_id'], campaign_id=r['campaign_id'],
                                 coupon_code=r['coupon_code'], member_id=r['member_id'], store_code=r['store_code'],
                                 redeemed_at=r['redeemed_at'], order_total=r['order_total'],
                                 discount_amount=r['discount_amount'], status=r['status'],
                                 voided_at=r['voided_at'], recorded_at=r['recorded_at']) for r in rows]
        return Page(data=data, next_cursor=next_cursor, has_more=next_cursor is not None)

    v1 = APIRouter(prefix='/v1', dependencies=[Depends(guard)], deprecated=True)

    @v1.get('/members', response_model=MembersV1Page, tags=['members (v1, deprecated)'])
    def list_members_v1(response: Response, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                        db=Depends(database)):
        response.headers['Deprecation'] = 'true'
        response.headers['Sunset'] = 'Thu, 31 Dec 2026 23:59:59 GMT'
        response.headers['Link'] = '</v2/members>; rel="successor-version"'
        total = db.execute('SELECT COUNT(*) FROM members').fetchone()[0]
        rows = db.execute('SELECT * FROM members ORDER BY id LIMIT ? OFFSET ?',
                          [page_size, (page - 1) * page_size]).fetchall()
        return MembersV1Page(members=[_member_v1(r) for r in rows], page=page, page_size=page_size, total=total)

    app.include_router(v2)
    app.include_router(v1)
    return app


def _member_v2(row):
    return MemberV2(
        member_id=row['member_id'], first_name=row['first_name'], last_name=row['last_name'], email=row['email'],
        phone_e164=row['phone_e164'], postal_code=row['postal_code'], home_store=row['home_store_code'],
        pet_types=row['pet_types'].split(','), email_opt_in=bool(row['email_opt_in']), tier=row['tier'],
        status=row['status'], enrolled_at=row['enrolled_at'], closed_at=row['closed_at'],
        points_balance=row['points_balance'], updated_at=row['updated_at'],
    )


def _member_v1(row):
    enrolled = datetime.fromisoformat(row['enrolled_at'].replace('Z', '+00:00'))
    local = enrolled.astimezone(ZoneInfo(row['home_store_time_zone']))
    return MemberV1(
        id=row['member_id'], name=f"{row['last_name']}, {row['first_name']}", email_address=row['email'],
        phone=row['phone_typed'], signup_date=local.strftime('%m/%d/%Y %H:%M'), tier=row['tier'],
        points=row['points_balance'],
    )
