"""Customers, with the mess real ones have, and the loyalty platform's marketing campaigns.

A "person" is a real shopper. Most people have one customer record; about 3% were entered twice, with their email
capitalized differently or missing and their phone typed in another format.
"""

import numpy as np
import pandas as pd

from .reference import CAMPAIGN_THEMES, CITIES, DEPARTMENTS
from .timeline import (
    ACQUISITION_DATE, DAY_FACTORS, N_DAYS, START, day_index, day_start_seconds, local_to_utc_seconds,
)

DUPLICATE_SHARE = 0.03
ONE_TIME_SHARE = 0.35
# Share of a long-open store's customers who were already customers when the history starts.
PREEXISTING_SHARE = 0.45
MEAN_LIFETIME_YEARS = 2.6
EMAIL_DOMAINS = (['mailbox.example', 'inbox.example', 'postal.example', 'webmail.example', 'netmail.example',
                  'homemail.example', 'campus.example', 'work.example'],
                 [.32, .22, .14, .10, .08, .06, .04, .04])
PHONE_FORMATS = (['({a}) {e}-{n}', '{a}-{e}-{n}', '{a}.{e}.{n}', '{a}{e}{n}', '+1 {a} {e} {n}', '1-{a}-{e}-{n}',
                  '{a} {e} {n}'],
                 [.35, .25, .08, .15, .07, .05, .05])


def build_customers(ctx):
    rng, stores = ctx.rng, ctx.stores
    n_records = ctx.size.customers
    n_people = round(n_records * (1 - DUPLICATE_SHARE))
    n_dupes = n_records - n_people

    store_weight = stores.volume * (stores.window_end - stores.window_start)
    home = rng.choice(len(stores), size=n_people, p=store_weight / store_weight.sum())
    ws = stores.window_start.to_numpy()[home]
    we = stores.window_end.to_numpy()[home]
    opened = stores.opened.to_numpy()[home]
    acquired_store = (stores.chain == 'critter_corner').to_numpy()[home]

    created = _days_weighted_by_traffic(rng, ws, we)
    imported = acquired_store & (rng.random(n_people) < 0.55)
    created[imported] = day_index(ACQUISITION_DATE)
    preexisting = ~acquired_store & (opened < 0) & (ws == 0) & (rng.random(n_people) < PREEXISTING_SHARE)
    earliest = np.maximum(opened, -5 * 365)
    created[preexisting] = rng.integers(earliest[preexisting], 0)
    # People created at the register made their first purchase that day.
    first_purchase = ~imported & ~preexisting

    rate = np.where(rng.random(n_people) < ONE_TIME_SHARE, 0.0, rng.gamma(1.3, 1.0, n_people))
    lifetime = (rng.exponential(MEAN_LIFETIME_YEARS, n_people) * 365).astype(int)
    active_from = np.maximum(created, ws) + first_purchase  # Repeat purchases start the day after the first.
    active_to = np.minimum(np.maximum(created, ws) + lifetime, we)

    owner_share = np.array([d.owner_share for d in DEPARTMENTS])
    primary = rng.choice(len(DEPARTMENTS), size=n_people, p=owner_share)
    secondary = rng.choice(len(DEPARTMENTS), size=n_people, p=owner_share)
    secondary = np.where((rng.random(n_people) < 0.30) & (secondary != primary), secondary, -1)

    female = rng.random(n_people) < 0.53
    first = np.where(female, ctx.names.first_female(n_people), ctx.names.first_male(n_people))
    last = ctx.names.last(n_people)
    has_email = rng.random(n_people) < 0.88
    has_phone = rng.random(n_people) < 0.90
    email_base = _unique_emails(rng, first, last)
    phone_digits = _unique_phones(rng, stores.city_id.to_numpy()[home])

    people = pd.DataFrame({
        'home': home, 'created': created, 'imported': imported, 'first_purchase': first_purchase,
        'rate': rate, 'active_from': active_from, 'active_to': active_to,
        'opt_in': rng.random(n_people) < 0.42, 'primary': primary, 'secondary': secondary,
        'first_name': first, 'last_name': last,
        'email': np.where(has_email, _styled_emails(rng, email_base), ''),
        'phone': np.where(has_phone, _formatted_phones(rng, phone_digits), ''),
    })

    # Duplicates: the same person entered again later, at the same or a nearby store.
    can_duplicate = np.flatnonzero((np.maximum(created, ws) + 30 < we) & (has_email | has_phone))
    source = rng.choice(can_duplicate, size=min(n_dupes, len(can_duplicate)), replace=False)
    dup_created = rng.integers(np.maximum(created[source], ws[source]) + 30, we[source] + 1)
    dupes = pd.DataFrame({
        'person': source, 'home': home[source], 'created': dup_created,
        'opt_in': rng.random(len(source)) < 0.42,
        'first_name': first[source], 'last_name': last[source],
        'email': np.where(has_email[source] & (rng.random(len(source)) < 0.8),
                          _styled_emails(rng, email_base[source], avoid_lower=True), ''),
        'phone': np.where(has_phone[source] & (rng.random(len(source)) < 0.8),
                          _formatted_phones(rng, phone_digits[source]), ''),
    })

    records = pd.concat([
        people[['home', 'created', 'opt_in', 'first_name', 'last_name', 'email', 'phone']].assign(
            person=np.arange(n_people), duplicate=False, imported=imported, at_register=first_purchase),
        dupes.assign(duplicate=True, imported=False, at_register=True),
    ], ignore_index=True)

    records['created_at'] = _creation_seconds(rng, records, stores)
    records = records.sort_values('created_at', ignore_index=True)
    records['id'] = np.arange(1, len(records) + 1)
    records['home_store_id'] = stores.id.to_numpy()[records.home]
    city_zip3 = np.array([CITIES[i].zip3 for i in stores.city_id])[records.home]
    records['postal_code'] = np.where(rng.random(len(records)) < 0.95,
                                      city_zip3 + pd.Series(rng.integers(0, 100, len(records))).map('{:02d}'.format),
                                      '')

    people['record_id'] = 0
    originals = records[~records.duplicate]
    people.loc[originals.person, 'record_id'] = originals.id.to_numpy()
    people['dup_record_id'] = 0
    people['dup_created'] = N_DAYS + 1
    copies = records[records.duplicate]
    people.loc[copies.person, 'dup_record_id'] = copies.id.to_numpy()
    people.loc[copies.person, 'dup_created'] = copies.created.to_numpy()

    ctx.people, ctx.customers = people, records


def _days_weighted_by_traffic(rng, low, high):
    """A day in [low, high] for each row, more likely on busy days and never on closed ones."""
    cumulative = np.concatenate([[0.0], np.cumsum(DAY_FACTORS)])
    lo, hi = cumulative[low], cumulative[high + 1]
    return np.searchsorted(cumulative, lo + rng.random(len(low)) * (hi - lo), side='right') - 1


def _clean(names):
    return pd.Series(names).str.replace(r'[^A-Za-z]', '', regex=True)


def _unique_emails(rng, first, last):
    """Properly capitalized email addresses, unique ignoring case."""
    f, l = _clean(first), _clean(last)
    n = len(f)
    digits = pd.Series(rng.integers(1, 99, n)).astype(str)
    patterns = [f + '.' + l, f + l, f.str[0] + l, f + l + digits, f + '_' + l, l + f.str[0] + digits]
    local = pd.Series(np.choose(rng.choice(len(patterns), n, p=[.3, .2, .15, .15, .1, .1]),
                                [p.to_numpy() for p in patterns]))
    domains, weights = EMAIL_DOMAINS
    email = local + '@' + pd.Series(rng.choice(domains, n, p=weights))
    while True:
        clash = email.str.lower().duplicated()
        if not clash.any():
            return email.to_numpy()
        extra = pd.Series(rng.integers(100, 9999, clash.sum())).astype(str).to_numpy()
        parts = email[clash].str.split('@', n=1, expand=True)
        email[clash] = parts[0] + extra + '@' + parts[1]


def _styled_emails(rng, emails, avoid_lower=False):
    """How each address was typed: mostly lowercase, sometimes capitalized, rarely shouting or with a typo."""
    emails = pd.Series(emails)
    style = rng.choice(4, len(emails), p=[0, .55, .30, .15] if avoid_lower else [.85, .09, .04, .02])
    out = emails.str.lower()
    out = out.where(style != 1, emails)                                       # Sam.Rivera@mailbox.example
    out = out.where(style != 2, emails.str.split('@').str[0] + '@' + emails.str.split('@').str[1].str.title())
    out = out.where(style != 3, emails.str.upper())                           # SAM.RIVERA@MAILBOX.EXAMPLE
    roll = rng.random(len(emails))
    out = out.where(roll >= 0.005, out.str.replace('.example', '.exmaple', regex=False))
    out = out.where((roll < 0.005) | (roll >= 0.012), out + ' ')
    return out.to_numpy()


def _unique_phones(rng, city_ids):
    area = np.empty(len(city_ids), dtype=object)
    for city_id in np.unique(city_ids):
        mask = city_ids == city_id
        area[mask] = rng.choice(CITIES[city_id].area_codes, mask.sum())
    area = pd.Series(area)

    def draw(count):
        return (pd.Series(rng.integers(200, 1000, count)).astype(str)
                + pd.Series(rng.integers(0, 10_000, count)).map('{:04d}'.format)).to_numpy()

    digits = area + draw(len(area))
    while (clash := digits.duplicated()).any():
        digits[clash] = area[clash] + draw(clash.sum())
    return digits.to_numpy()


def _formatted_phones(rng, digits):
    digits = pd.Series(digits)
    a, e, n = digits.str[:3], digits.str[3:6], digits.str[6:]
    formats, weights = PHONE_FORMATS
    choice = rng.choice(len(formats), len(digits), p=weights)
    out = pd.Series('', index=digits.index, dtype=object)
    for i, fmt in enumerate(formats):
        mask = choice == i
        out[mask] = [fmt.format(a=x, e=y, n=z) for x, y, z in zip(a[mask], e[mask], n[mask])]
    return out.to_numpy()


def _creation_seconds(rng, records, stores):
    n = len(records)
    seconds = np.empty(n, dtype=np.int64)
    at_register = records.at_register.to_numpy()
    minutes = rng.integers(9 * 60, 21 * 60, n)
    days = records.created.to_numpy()
    zones = stores.time_zone.to_numpy()[records.home]
    seconds[at_register] = local_to_utc_seconds(days[at_register], minutes[at_register], zones[at_register])
    other = ~at_register
    seconds[other] = day_start_seconds(days[other]) + rng.integers(0, 86_400, other.sum())
    # Customers brought over from Critter Corner were all imported in one batch at 06:00 UTC.
    imported = records.imported.to_numpy()
    seconds[imported] = day_start_seconds(np.full(imported.sum(), day_index(ACQUISITION_DATE))) + 6 * 3600
    return seconds


def build_campaigns(ctx):
    """Department-specific coupon campaigns. `lift` is how much each one really raised sales; it stays hidden."""
    rng = ctx.rng
    rows = []
    for dept_index, d in enumerate(DEPARTMENTS):
        big = d.code in ('DOG', 'CAT')
        gap_low, gap_high = (21, 36) if big else (42, 71)
        day = int(rng.integers(0, gap_high))
        while day < N_DAYS - 7:
            length = int(rng.integers(7, 15))
            end = min(day + length - 1, N_DAYS - 1)
            percent = int(rng.choice([10, 15, 20, 25], p=[.30, .35, .25, .10]))
            start_date = START + pd.Timedelta(days=day)
            lift = 0.05 if rng.random() < 0.12 else float(rng.lognormal(np.log(0.8), 0.6))
            rows.append({'dept_index': dept_index, 'department_code': d.code,
                         'code': f'{d.code}{percent}-{start_date:%y%m%d}',
                         'name': f'{rng.choice(CAMPAIGN_THEMES[d.code])}: {percent}% off',
                         'discount_percent': percent, 'start': day, 'end': end, 'lift': lift})
            day = end + int(rng.integers(gap_low, gap_high))
    campaigns = pd.DataFrame(rows).sort_values('start', ignore_index=True)
    campaigns['id'] = np.arange(1, len(campaigns) + 1)

    active = np.full((len(DEPARTMENTS), N_DAYS), -1)
    for i, c in enumerate(campaigns.itertuples()):
        active[c.dept_index, c.start:c.end + 1] = i
    ctx.campaigns, ctx.active_campaign = campaigns, active
