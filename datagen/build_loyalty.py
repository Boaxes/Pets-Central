"""The loyalty platform's data: members, points, campaign emails and coupon redemptions, written to SQLite.

Members are the same people as the store's customers, but the platform recorded them its own way and shares no ID
with the store: emails lowercased by the platform (or a different address), phones normalized (or a different
number), different store codes. A separate truth file says which member is which customer, for scoring the
matching later. Points come from members' real purchases and redemptions from the real coupon sales.

This uses its own random stream, so adding or changing loyalty data never changes the store data.
"""

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from .build_customers import EMAIL_DOMAINS, _formatted_phones
from .context import Names
from .reference import CITIES, DEPARTMENTS
from .timeline import N_DAYS, day_start_seconds, days_to_strings

SCHEMA = Path(__file__).resolve().parent.parent / 'loyalty_api' / 'loyalty' / 'schema.sql'
MEMBER_RATE_OPTED_IN, MEMBER_RATE_OTHERS = 0.70, 0.15
ONLINE_ONLY_SHARE = 0.06
EARN_RECORDED_RATE = 0.90  # Members sometimes forget to give their phone number at the register.
CAMPAIGN_BONUS = 100
REDEEM_THRESHOLD, REDEEM_POINTS = 600, 500
EMAIL_SEGMENT_SHARE = 0.60
DAY = 86_400


def vendor_store_code(code):
    """The platform's store codes: PC-0042 becomes PC0042 and CC/WA/017 becomes CC-WA-017."""
    return code.replace('PC-', 'PC').replace('/', '-')


def utc_strings(seconds):
    return np.datetime_as_string(np.asarray(seconds).astype('datetime64[s]'), unit='s').astype(object) + 'Z'


def local_strings(seconds, zones):
    """Wall-clock time in each store's time zone, with no offset."""
    out = np.empty(len(seconds), dtype=object)
    zones = np.asarray(zones)
    for tz in np.unique(zones):
        mask = zones == tz
        local = pd.to_datetime(np.asarray(seconds)[mask], unit='s', utc=True).tz_convert(tz)
        out[mask] = local.strftime('%Y-%m-%d %H:%M:%S').to_numpy()
    return out


def recording_lag(rng, n):
    """Most rows reach the platform within hours; some arrive a day or several days late."""
    roll = rng.random(n)
    return np.where(roll < 0.85, rng.integers(300, 3 * 3600, n),
                    np.where(roll < 0.97, rng.integers(DAY, 2 * DAY, n), rng.integers(2 * DAY, 7 * DAY, n)))


def build_loyalty(ctx, sale_net_cents, sale_discount_cents, path, truth_path):
    rng = np.random.default_rng(ctx.seed + 1)
    end = int(day_start_seconds(np.array([N_DAYS]))[0])
    members, person_member = _members(ctx, rng, end)
    points = _points(ctx, rng, members, person_member, sale_net_cents, end)
    _finish_members(members, points)
    campaigns = _campaigns(ctx)
    emails = _emails(ctx, rng, members, person_member, end)
    redemptions = _redemptions(ctx, rng, person_member, members, sale_net_cents, sale_discount_cents)
    _write_sqlite(path, members, campaigns, points, emails, redemptions)
    _write_truth(ctx, members, truth_path)
    return {'members': len(members), 'points_transactions': len(points), 'email_events': len(emails),
            'coupon_redemptions': len(redemptions)}


def _members(ctx, rng, end):
    people, customers, stores = ctx.people, ctx.customers, ctx.stores
    originals = customers[~customers.duplicate].set_index('person')
    created_at = originals.created_at.reindex(range(len(people))).to_numpy()

    rate = np.where(people.opt_in, MEMBER_RATE_OPTED_IN, MEMBER_RATE_OTHERS)
    enrolled = created_at + rng.integers(0, 180 * DAY, len(people))
    joined = np.flatnonzero((rng.random(len(people)) < rate) & (enrolled < end - DAY))
    m = len(joined)
    p = people.iloc[joined]

    store_email = p.email.str.strip().str.lower().str.replace('.exmaple', '.example', regex=False).to_numpy()
    first_l = p.first_name.str.replace(r'[^A-Za-z]', '', regex=True).str.lower()
    last_l = p.last_name.str.replace(r'[^A-Za-z]', '', regex=True).str.lower()
    other_email = (first_l + '.' + last_l + pd.Series(rng.integers(1, 999, m), index=p.index).astype(str)
                   + '@work.example').to_numpy()
    roll = rng.random(m)
    has_store_email = store_email != ''
    email = np.where(has_store_email & (roll < 0.82), store_email,
                     np.where(roll < 0.95, other_email, None))

    store_digits = p.phone.str.replace(r'\D', '', regex=True)
    store_digits = store_digits.where(store_digits.str.len() == 10, store_digits.str[-10:]).to_numpy()
    home = p.home.to_numpy()
    new_digits = _random_digits(rng, stores.city_id.to_numpy()[home])
    roll = rng.random(m)
    has_store_phone = p.phone.to_numpy() != ''
    digits = np.where(has_store_phone, np.where(roll < 0.85, store_digits, np.where(roll < 0.93, new_digits, None)),
                      np.where(roll < 0.70, new_digits, None))

    store_postal = originals.postal_code.reindex(p.index).to_numpy()
    city_zip3 = np.array([CITIES[i].zip3 for i in stores.city_id])[home]
    moved = rng.random(m) < 0.10
    postal = np.where(moved, city_zip3 + pd.Series(rng.integers(0, 100, m)).map('{:02d}'.format).to_numpy(),
                      store_postal)

    codes = np.array([d.code for d in DEPARTMENTS])
    secondary = p.secondary.to_numpy()
    pet_types = np.where(secondary >= 0, codes[p.primary.to_numpy()] + ',' + codes[np.maximum(secondary, 0)],
                         codes[p.primary.to_numpy()])

    members = pd.DataFrame({
        'person': joined, 'first_name': p.first_name.to_numpy(), 'last_name': p.last_name.to_numpy(),
        'email': email, 'digits': digits, 'postal_code': postal, 'home': home, 'pet_types': pet_types,
        'email_opt_in': p.opt_in.to_numpy() ^ (rng.random(m) < 0.10), 'enrolled': enrolled[joined],
    })
    members = pd.concat([members, _online_only_members(ctx, rng, round(m * ONLINE_ONLY_SHARE), end)],
                        ignore_index=True)

    n = len(members)
    closed = rng.random(n) < 0.04
    members['closed'] = np.where(closed, members.enrolled + (rng.random(n) * (end - members.enrolled)).astype(np.int64),
                                 0)
    members['member_id'] = _unique_ids(rng, n)
    has_phone = members.digits.notna().to_numpy()
    typed = np.full(n, None, dtype=object)
    typed[has_phone] = _formatted_phones(rng, members.digits[has_phone].to_numpy())
    members['phone_typed'] = typed
    members['phone_e164'] = np.where(has_phone, '+1' + members.digits.fillna(''), None)
    members['home_store_code'] = [vendor_store_code(c) for c in stores.store_code.to_numpy()[members.home]]
    members['home_store_time_zone'] = stores.time_zone.to_numpy()[members.home]

    person_member = np.full(len(people), -1)
    from_store = members.person.to_numpy() >= 0
    person_member[members.person.to_numpy()[from_store]] = np.flatnonzero(from_store)
    return members, person_member


def _online_only_members(ctx, rng, n, end):
    """People who joined online and never shopped under a customer record."""
    names = Names(rng)
    female = rng.random(n) < 0.53
    first = np.where(female, names.first_female(n), names.first_male(n))
    last = names.last(n)
    domains, weights = EMAIL_DOMAINS
    email = (pd.Series(first).str.lower().str.replace(r'[^a-z]', '', regex=True) + '.'
             + pd.Series(last).str.lower().str.replace(r'[^a-z]', '', regex=True)
             + pd.Series(rng.integers(100, 9999, n)).astype(str) + '@' + rng.choice(domains, n, p=weights))
    home = rng.integers(0, len(ctx.stores), n)
    codes = np.array([d.code for d in DEPARTMENTS])
    owner_share = np.array([d.owner_share for d in DEPARTMENTS])
    start = int(day_start_seconds(np.array([0]))[0])
    return pd.DataFrame({
        'person': -1, 'first_name': first, 'last_name': last, 'email': email.to_numpy(),
        'digits': _random_digits(rng, ctx.stores.city_id.to_numpy()[home]),
        'postal_code': np.array([CITIES[i].zip3 for i in ctx.stores.city_id])[home]
        + pd.Series(rng.integers(0, 100, n)).map('{:02d}'.format).to_numpy(),
        'home': home, 'pet_types': codes[rng.choice(len(codes), n, p=owner_share)],
        'email_opt_in': rng.random(n) < 0.6, 'enrolled': rng.integers(start, end - DAY, n),
    })


def _random_digits(rng, city_ids):
    area = np.array([CITIES[i].area_codes[0] for i in city_ids], dtype=object)
    return (area + pd.Series(rng.integers(200, 1000, len(area))).astype(str).to_numpy()
            + pd.Series(rng.integers(0, 10_000, len(area))).map('{:04d}'.format).to_numpy())


def _unique_ids(rng, n):
    ids = np.unique(rng.integers(0, 16 ** 10, n + n // 100 + 10))
    ids = rng.permutation(ids)[:n]
    assert len(ids) == n
    return [f'LM{x:010X}' for x in ids]


def _record_to_person(people, customers):
    lookup = np.full(int(customers.id.max()) + 1, -1)
    lookup[people.record_id.to_numpy()] = np.arange(len(people))
    duplicates = people.dup_record_id.to_numpy() > 0
    lookup[people.dup_record_id.to_numpy()[duplicates]] = np.flatnonzero(duplicates)
    return lookup


def _sale_members(ctx, person_member):
    sales = ctx.sales
    lookup = _record_to_person(ctx.people, ctx.customers)
    person = lookup[sales.customer_id.to_numpy()]
    return np.where(person >= 0, person_member[np.maximum(person, 0)], -1)


def _points(ctx, rng, members, person_member, sale_net_cents, end):
    sales = ctx.sales
    member = _sale_members(ctx, person_member)
    enrolled = members.enrolled.to_numpy()
    closed = np.where(members.closed > 0, members.closed, end + DAY)
    sold_at = sales.sold_at.to_numpy()
    m = np.maximum(member, 0)
    earned = ((member >= 0) & (sold_at >= enrolled[m]) & (sold_at < closed[m])
              & (rng.random(len(sales)) < EARN_RECORDED_RATE))
    net = sale_net_cents[sales.id.to_numpy()]
    cancelled = sales.cancelled.to_numpy()
    coupon = sales.campaign.to_numpy() >= 0
    store = sales.store.to_numpy()

    parts = [
        ('earn', earned, net // 100, net / 100, sold_at),
        ('reversal', earned & cancelled, -(net // 100), -net / 100, sales.cancelled_at.to_numpy()),
        ('campaign_bonus', earned & coupon & ~cancelled, np.full(len(sales), CAMPAIGN_BONUS), np.nan, sold_at + 60),
    ]
    frames = [pd.DataFrame({'member': member[mask], 'type': kind, 'points': np.asarray(pts)[mask],
                            'purchase_amount': (np.full(len(sales), np.nan) if np.isscalar(amount) else amount)[mask],
                            'store': store[mask], 'at': np.asarray(at)[mask]})
              for kind, mask, pts, amount, at in parts]
    events = pd.concat(frames, ignore_index=True).sort_values(['member', 'at'], kind='stable', ignore_index=True)

    # A member redeems 500 points each time their running total passes another 600, most of the time.
    running = events.groupby('member').points.cumsum().to_numpy()
    before = running - events.points.to_numpy()
    crossings = np.maximum(0, np.floor_divide(running, REDEEM_THRESHOLD) - np.floor_divide(before, REDEEM_THRESHOLD))
    trigger = np.repeat(np.arange(len(events)), crossings)
    trigger = trigger[rng.random(len(trigger)) < 0.7]
    redeem_at = events['at'].to_numpy()[trigger] + rng.integers(DAY, 30 * DAY, len(trigger))
    keep = redeem_at < np.minimum(end, closed[events.member.to_numpy()[trigger]])
    redeems = pd.DataFrame({'member': events.member.to_numpy()[trigger][keep], 'type': 'redeem',
                            'points': -REDEEM_POINTS, 'purchase_amount': np.nan,
                            'store': events.store.to_numpy()[trigger][keep], 'at': redeem_at[keep]})
    events = pd.concat([events, redeems], ignore_index=True)
    events['recorded'] = events['at'] + recording_lag(rng, len(events))
    events = events.sort_values(['recorded', 'member'], ignore_index=True)
    events['id'] = np.arange(1, len(events) + 1)
    store_codes = np.array([vendor_store_code(c) for c in ctx.stores.store_code], dtype=object)
    events['store_code'] = store_codes[events.store]
    events['occurred_local'] = local_strings(events['at'].to_numpy(), ctx.stores.time_zone.to_numpy()[events.store])
    return events


def _finish_members(members, points):
    totals = points.groupby('member').points.sum()
    lifetime = points[points.points > 0].groupby('member').points.sum()
    last_recorded = points.groupby('member').recorded.max()
    n = len(members)
    members['points_balance'] = totals.reindex(range(n), fill_value=0).to_numpy().astype(int)
    earned = lifetime.reindex(range(n), fill_value=0).to_numpy()
    members['tier'] = np.where(earned >= 6000, 'gold', np.where(earned >= 1500, 'silver', 'bronze'))
    members['status'] = np.where(members.closed > 0, 'closed', 'active')
    members['updated'] = np.maximum.reduce([members.enrolled.to_numpy(), members.closed.to_numpy(),
                                            last_recorded.reindex(range(n), fill_value=0).to_numpy()])


def _campaigns(ctx):
    c = ctx.campaigns
    created = day_start_seconds(c.start.to_numpy()) - 7 * DAY
    start_dates = days_to_strings(c.start.to_numpy())
    end_dates = days_to_strings(c.end.to_numpy())
    return pd.DataFrame({'id': c.id, 'code': c.code, 'name': c['name'], 'department_code': c.department_code,
                         'discount_percent': c.discount_percent, 'starts_on': start_dates, 'ends_on': end_dates,
                         'channel': 'email', 'created_at': utc_strings(created), 'updated_at': utc_strings(created)})


def _emails(ctx, rng, members, person_member, end):
    sales = ctx.sales
    member_of_sale = _sale_members(ctx, person_member)
    enrolled = members.enrolled.to_numpy()
    closed = np.where(members.closed > 0, members.closed, end + DAY)
    can_email = members.email.notna().to_numpy() & members.email_opt_in.to_numpy()
    pets = members.pet_types.to_numpy().astype(str)
    frames = []
    for index, c in enumerate(ctx.campaigns.itertuples()):
        sent_base = int(day_start_seconds(np.array([c.start]))[0]) + 15 * 3600
        audience = np.flatnonzero(can_email & (enrolled < sent_base) & (closed > sent_base)
                                  & (np.char.find(pets, c.department_code) >= 0))
        audience = audience[rng.random(len(audience)) < EMAIL_SEGMENT_SHARE]
        responders = member_of_sale[(sales.campaign.to_numpy() == index) & (member_of_sale >= 0)]
        responded = np.isin(audience, responders)
        n = len(audience)
        sent = sent_base + rng.integers(0, 3 * 3600, n)
        opened = rng.random(n) < np.where(responded, 0.85, 0.20)
        opened_at = sent + np.minimum(rng.exponential(6 * 3600, n), 5 * DAY).astype(np.int64)
        clicked = opened & (rng.random(n) < np.where(responded, 0.70, 0.12))
        clicked_at = opened_at + rng.integers(10, 2 * 3600, n)
        last = np.where(clicked, clicked_at, np.where(opened, opened_at, sent))
        frames.append(pd.DataFrame({
            'campaign_id': c.id, 'member': audience, 'sent': sent,
            'opened': np.where(opened, opened_at, 0), 'clicked': np.where(clicked, clicked_at, 0),
            'unsubscribed': rng.random(n) < 0.002, 'recorded': last + recording_lag(rng, n),
        }))
    emails = pd.concat(frames, ignore_index=True).sort_values(['recorded', 'member'], ignore_index=True)
    emails['id'] = np.arange(1, len(emails) + 1)
    return emails


def _redemptions(ctx, rng, person_member, members, sale_net_cents, sale_discount_cents):
    sales = ctx.sales[ctx.sales.campaign >= 0]
    member = _sale_members(ctx, person_member)[ctx.sales.campaign.to_numpy() >= 0]
    cancelled = sales.cancelled.to_numpy()
    redeemed = sales.sold_at.to_numpy()
    voided = sales.cancelled_at.to_numpy()
    last = np.where(cancelled, voided, redeemed)
    out = pd.DataFrame({
        'campaign_id': ctx.campaigns.id.to_numpy()[sales.campaign.to_numpy()],
        'coupon_code': ctx.campaigns.code.to_numpy()[sales.campaign.to_numpy()],
        'member_id': np.where(member >= 0, np.asarray(members.member_id, dtype=object)[np.maximum(member, 0)], None),
        'store_code': [vendor_store_code(c) for c in ctx.stores.store_code.to_numpy()[sales.store.to_numpy()]],
        'redeemed': redeemed,
        'order_total': sale_net_cents[sales.id.to_numpy()] / 100,
        'discount_amount': sale_discount_cents[sales.id.to_numpy()] / 100,
        'status': np.where(cancelled, 'voided', 'redeemed'),
        'voided': np.where(cancelled, voided, 0),
        'recorded': last + recording_lag(rng, len(sales)),
    }).sort_values(['recorded', 'redeemed'], ignore_index=True)
    out['id'] = np.arange(1, len(out) + 1)
    out['redemption_id'] = [f'RD{i:08d}' for i in out.id]
    return out


def _nullable_utc(seconds):
    text = utc_strings(seconds)
    text[np.asarray(seconds) == 0] = None
    return text


def _write_sqlite(path, members, campaigns, points, emails, redemptions):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    db.executescript('PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF;' + SCHEMA.read_text())

    def insert(table, frame):
        columns = ', '.join(frame.columns)
        marks = ', '.join('?' for _ in frame.columns)
        rows = frame.astype(object).where(frame.notna(), None).itertuples(index=False, name=None)
        db.executemany(f'INSERT INTO {table} ({columns}) VALUES ({marks})', rows)

    insert('members', pd.DataFrame({
        'id': np.arange(1, len(members) + 1), 'member_id': members.member_id, 'first_name': members.first_name,
        'last_name': members.last_name, 'email': members.email, 'phone_typed': members.phone_typed,
        'phone_e164': members.phone_e164, 'postal_code': members.postal_code,
        'home_store_code': members.home_store_code, 'home_store_time_zone': members.home_store_time_zone,
        'pet_types': members.pet_types, 'email_opt_in': members.email_opt_in.astype(int), 'tier': members.tier,
        'status': members.status, 'enrolled_at': utc_strings(members.enrolled),
        'closed_at': _nullable_utc(members.closed), 'points_balance': members.points_balance,
        'updated_at': utc_strings(members.updated),
    }))
    insert('campaigns', campaigns)
    member_ids = np.asarray(members.member_id, dtype=object)
    insert('points_transactions', pd.DataFrame({
        'id': points.id, 'member_id': member_ids[points.member], 'type': points.type, 'points': points.points,
        'purchase_amount': points.purchase_amount, 'store_code': points.store_code,
        'occurred_local': points.occurred_local, 'recorded_at': utc_strings(points.recorded),
    }))
    insert('email_events', pd.DataFrame({
        'id': emails.id, 'campaign_id': emails.campaign_id, 'member_id': member_ids[emails.member],
        'sent_at': utc_strings(emails.sent), 'opened_at': _nullable_utc(emails.opened),
        'clicked_at': _nullable_utc(emails.clicked), 'unsubscribed': emails.unsubscribed.astype(int),
        'recorded_at': utc_strings(emails.recorded),
    }))
    insert('coupon_redemptions', pd.DataFrame({
        'id': redemptions.id, 'redemption_id': redemptions.redemption_id, 'campaign_id': redemptions.campaign_id,
        'coupon_code': redemptions.coupon_code, 'member_id': redemptions.member_id,
        'store_code': redemptions.store_code, 'redeemed_at': utc_strings(redemptions.redeemed),
        'order_total': redemptions.order_total, 'discount_amount': redemptions.discount_amount,
        'status': redemptions.status, 'voided_at': _nullable_utc(redemptions.voided),
        'recorded_at': utc_strings(redemptions.recorded),
    }))
    db.commit()
    db.execute('ANALYZE')
    db.close()


def _write_truth(ctx, members, path):
    """Which member is which customer record. Kept out of the API; used only to score the matching."""
    people = ctx.people
    from_store = members[members.person >= 0]
    person = from_store.person.to_numpy()
    rows = [pd.DataFrame({'member_id': from_store.member_id.to_numpy(),
                          'customer_id': people.record_id.to_numpy()[person]})]
    dup = people.dup_record_id.to_numpy()[person]
    has_dup = dup > 0
    rows.append(pd.DataFrame({'member_id': from_store.member_id.to_numpy()[has_dup], 'customer_id': dup[has_dup]}))
    truth = pd.concat(rows, ignore_index=True).sort_values(['member_id', 'customer_id'])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    truth.to_csv(path, index=False)
