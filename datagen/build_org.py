"""Regions, stores and employees."""

import numpy as np
import pandas as pd

from .reference import ACQUIRED_CHAIN_STATES, CITIES, REGIONS, STORE_NAME_SUFFIXES
from .timeline import ACQUISITION_DATE, END, N_DAYS, START, day_index

NO_DAY = -999_999

FORMAT_VOLUME = {'flagship': 2.0, 'standard': 1.0, 'express': 0.55}
HIGH_WAGE_STATES = {'CA', 'WA', 'NY', 'MA', 'NJ', 'CT', 'OR'}

# Staffing per store format: role -> headcount at any one time.
STAFFING = {
    'flagship': {'store_manager': 1, 'assistant_manager': 2, 'animal_care': 5, 'groomer': 4, 'associate': 20},
    'standard': {'store_manager': 1, 'assistant_manager': 1, 'animal_care': 3, 'groomer': 2, 'associate': 11},
    'express': {'store_manager': 1, 'assistant_manager': 1, 'animal_care': 0, 'groomer': 0, 'associate': 7},
}
MEAN_TENURE_YEARS = {'store_manager': 5.0, 'assistant_manager': 3.5, 'animal_care': 2.0, 'groomer': 2.5,
                     'associate': 1.1}
BASE_WAGE = {'store_manager': 29.0, 'assistant_manager': 21.0, 'animal_care': 17.0, 'groomer': 19.0,
             'associate': 15.5}


def build_regions():
    return pd.DataFrame({'id': range(1, len(REGIONS) + 1),
                         'code': [code for code, _ in REGIONS],
                         'name': [name for _, name in REGIONS]})


def _allocate(weights, total):
    """Split `total` stores across cities in proportion to weight (largest remainder)."""
    shares = np.asarray(weights) / np.sum(weights) * total
    counts = np.floor(shares).astype(int)
    for i in np.argsort(-(shares - counts))[: total - counts.sum()]:
        counts[i] += 1
    return counts


def build_stores(ctx):
    rng, fake = ctx.rng, ctx.fake
    region_ids = {code: i + 1 for i, (code, _) in enumerate(REGIONS)}
    n_acquired = max(1, round(ctx.size.stores * 0.12))
    acquired_cities = [i for i, c in enumerate(CITIES) if c.state in ACQUIRED_CHAIN_STATES]

    rows = []
    for chain, city_ids, count in [
        ('pets_central', list(range(len(CITIES))), ctx.size.stores - n_acquired),
        ('critter_corner', acquired_cities, n_acquired),
    ]:
        counts = _allocate([CITIES[i].weight for i in city_ids], count)
        for city_id, n in zip(city_ids, counts):
            for _ in range(n):
                rows.append({'chain': chain, 'city_id': city_id})

    start_day, end_day = day_index(START), day_index(END)
    acquisition_day = day_index(ACQUISITION_DATE)
    for row in rows:
        city = CITIES[row['city_id']]
        if row['chain'] == 'critter_corner':
            row['opened'] = int(rng.integers(day_index(START.replace(year=2006)), day_index(START.replace(year=2022))))
            row['acquired'] = acquisition_day
            row['closed'] = NO_DAY
            row['format'] = 'express' if rng.random() < 0.3 else 'standard'
        else:
            roll = rng.random()
            if roll < 0.09:
                row['opened'] = int(rng.integers(start_day + 30, end_day - 120))
            else:
                row['opened'] = int(rng.integers(day_index(START.replace(year=2004)), start_day - 30))
            row['acquired'] = NO_DAY
            closes = row['opened'] < start_day and rng.random() < 0.03
            row['closed'] = int(rng.integers(start_day + 180, end_day - 30)) if closes else NO_DAY
            row['format'] = ('flagship' if city.weight >= 1.4 and rng.random() < 0.35
                             else 'express' if rng.random() < 0.22 else 'standard')
        row['region_id'] = region_ids[city.region]

    stores = pd.DataFrame(rows)
    stores = stores.sort_values(['chain', 'opened'], ignore_index=True)
    stores['id'] = np.arange(1, len(stores) + 1)

    acquired_numbers = rng.choice(np.arange(1, 160), size=n_acquired, replace=False)
    codes, names, acquired_i = [], [], 0
    pc_number = 0
    city_seen = {}
    for row in stores.itertuples():
        city = CITIES[row.city_id]
        if row.chain == 'critter_corner':
            codes.append(f'CC/{city.state}/{acquired_numbers[acquired_i]:03d}')
            acquired_i += 1
        else:
            pc_number += 1
            codes.append(f'PC-{pc_number:04d}')
        seen = city_seen.get(row.city_id, 0)
        city_seen[row.city_id] = seen + 1
        names.append(city.name if seen == 0 else f'{city.name} {STORE_NAME_SUFFIXES[(seen - 1) % len(STORE_NAME_SUFFIXES)]}')

    stores['store_code'] = codes
    stores['name'] = names
    stores['city'] = [CITIES[i].name for i in stores.city_id]
    stores['state'] = [CITIES[i].state for i in stores.city_id]
    stores['time_zone'] = [CITIES[i].time_zone for i in stores.city_id]
    stores['region_code'] = [CITIES[i].region for i in stores.city_id]
    stores['postal_code'] = [CITIES[i].zip3 + f'{rng.integers(0, 100):02d}' for i in stores.city_id]
    stores['address_line'] = [fake.street_address() for _ in range(len(stores))]
    # The days this store's sales appear in this system.
    stores['window_start'] = np.maximum.reduce([np.full(len(stores), start_day), stores.opened, stores.acquired])
    stores['window_end'] = np.where(stores.closed == NO_DAY, end_day, stores.closed)
    stores['volume'] = stores.format.map(FORMAT_VOLUME)
    stores['carries_live'] = stores.format != 'express'
    assert (stores.window_end > stores.window_start).all()
    assert stores.window_end.max() < N_DAYS
    return stores


def build_employees(ctx):
    rng = ctx.rng
    stores = ctx.stores
    end_day = day_index(END)
    rows = []
    for store in stores.itertuples():
        # Staff are only recorded from when the store joined this system, but keep their real hire dates.
        system_start = store.window_start
        for role, headcount in STAFFING[store.format].items():
            for _ in range(headcount):
                hired = max(store.opened, system_start - int(rng.integers(0, 6 * 365)))
                while hired <= min(store.window_end, end_day):
                    tenure = max(30, int(rng.exponential(MEAN_TENURE_YEARS[role] * 365)))
                    left = hired + tenure
                    if store.closed != NO_DAY:
                        left = min(left, store.closed)
                    terminated = left if left <= end_day else NO_DAY
                    if terminated == NO_DAY or terminated >= system_start:
                        rows.append((store.id, store.chain, store.state, role, hired, terminated))
                    if terminated == NO_DAY or terminated >= store.window_end:
                        break
                    hired = terminated + int(rng.integers(3, 30))

    employees = pd.DataFrame(rows, columns=['store_id', 'chain', 'state', 'role', 'hired', 'terminated'])
    employees = employees.sort_values('hired', ignore_index=True)
    employees['id'] = np.arange(1, len(employees) + 1)
    n = len(employees)

    acquired_chain = (employees.chain == 'critter_corner') & (employees.hired < day_index(ACQUISITION_DATE))
    numbers = np.array([f'E{i:06d}' for i in range(100_001, 100_001 + n)], dtype=object)
    legacy = rng.choice(np.arange(10_000, 99_999), size=int(acquired_chain.sum()), replace=False)
    numbers[acquired_chain.to_numpy()] = [f'CC-{x:05d}' for x in legacy]
    employees['employee_number'] = numbers

    female = rng.random(n) < 0.55
    employees['first_name'] = np.where(female, ctx.names.first_female(n), ctx.names.first_male(n))
    employees['last_name'] = ctx.names.last(n)
    employees['email'] = (employees.first_name.str.lower().str.replace(r'[^a-z]', '', regex=True) + '.'
                          + employees.last_name.str.lower().str.replace(r'[^a-z]', '', regex=True)
                          + employees.employee_number.str[-4:] + '@petscentral.example')
    years_since_2023 = np.clip((employees.hired - day_index(START)) / 365.25, -6, 3)
    wage = (employees.role.map(BASE_WAGE) * np.where(employees.state.isin(HIGH_WAGE_STATES), 1.2, 1.0)
            * (1.03 ** years_since_2023) * rng.uniform(0.95, 1.1, n))
    employees['hourly_rate'] = np.round(wage, 2)
    return employees


def active_staff_by_store_month(employees, roles):
    """{(store_id, month): array of employee ids} for staff in `roles` working the whole month.

    Falls back to staff who worked any part of the month when nobody worked all of it.
    """
    from .timeline import MONTH_FIRST_DAY, MONTH_LAST_DAY, N_MONTHS

    staff = employees[employees.role.isin(roles)]
    staff = staff.assign(left=np.where(staff.terminated == NO_DAY, N_DAYS + 1, staff.terminated))
    lookup = {}
    for store_id, group in staff.groupby('store_id'):
        hired, left, ids = group.hired.to_numpy(), group.left.to_numpy(), group.id.to_numpy()
        for month in range(N_MONTHS):
            first, last = MONTH_FIRST_DAY[month], MONTH_LAST_DAY[month]
            whole = ids[(hired <= first) & (left >= last)]
            lookup[(store_id, month)] = whole if len(whole) else ids[(hired <= last) & (left >= first)]
    return lookup
