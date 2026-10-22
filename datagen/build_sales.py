"""Sales, sale lines, the animals sold, returns, current stock and animals still in stores.

Sales come from two places: customers, who shop on their own schedule until they stop coming, and guests, who
check out without a customer record. Campaigns bring opted-in customers in for extra trips and coupon use, so a
campaign's real effect shows up in the sales.
"""

import numpy as np
import pandas as pd

from .build_catalog import price_on
from .build_org import NO_DAY, active_staff_by_store_month
from .reference import CATEGORY_SEASONALITY, DEPARTMENTS, QUANTITY_DISTRIBUTIONS
from .timeline import (
    DAY_FACTORS, DAY_MONTH_INDEX, DAY_MONTHS, N_DAYS, day_start_seconds, local_to_utc_seconds, seconds_to_strings,
)

MEAN_LINES_PER_SALE = 2.5
GUEST_SHARE = 0.28
AWAY_FROM_HOME_SHARE = 0.08
LINE_DEPARTMENT_WEIGHTS = np.array([.40, .32, .10, .05, .06, .07])  # Same order as DEPARTMENTS.
IN_STORE_HOURS = np.arange(9, 21)
IN_STORE_HOUR_WEIGHTS = np.array([3, 5, 7, 8, 8, 7, 7, 8, 9, 9, 7, 4], dtype=float)
ONLINE_HOUR_WEIGHTS = np.array([1, .5, .3, .3, .3, .5, 1, 2, 3, 4, 4, 5, 5, 5, 4, 4, 4, 5, 6, 7, 7, 6, 4, 2])
SELLING_ROLES = ['associate', 'assistant_manager', 'store_manager']
RETURN_REASONS = (['damaged', 'wrong_item', 'pet_refused', 'changed_mind', 'other'], [.25, .15, .30, .25, .05])
PET_NAMES = ['Mango', 'Pickles', 'Noodle', 'Biscuit', 'Peanut', 'Ziggy', 'Pepper', 'Kiwi', 'Mochi', 'Rex', 'Sunny',
             'Olive', 'Nugget', 'Spike', 'Luna', 'Gizmo', 'Basil', 'Tango', 'Clover', 'Echo']
CHUNK_SALES = 250_000


def build_sales(ctx):
    rng, people, stores = ctx.rng, ctx.people, ctx.stores
    target_sales = ctx.size.sale_lines / MEAN_LINES_PER_SALE

    # --- Customer trips ---------------------------------------------------------------------------------------
    span = np.maximum(0, people.active_to.to_numpy() - people.active_from.to_numpy() + 1)
    rate = people.rate.to_numpy()
    first = people.first_purchase.to_numpy()
    exposure = (rate * span / 365).sum()
    scale = max(0.0, ((1 - GUEST_SHARE) * target_sales - first.sum()) / exposure)
    peak = DAY_FACTORS.max()

    counts = rng.poisson(rate * scale * peak * span / 365)
    person = np.repeat(np.arange(len(people)), counts)
    day = people.active_from.to_numpy()[person] + (rng.random(len(person)) * span[person]).astype(int)
    keep = rng.random(len(person)) < DAY_FACTORS[day] / peak
    person, day = person[keep], day[keep]
    campaign = np.full(len(person), -1)
    first_trip = np.zeros(len(person), dtype=bool)

    first_people = np.flatnonzero(first)
    extra_person, extra_day, extra_campaign = _campaign_trips(ctx, scale)

    person = np.concatenate([person, first_people, extra_person])
    day = np.concatenate([day, people.created.to_numpy()[first_people], extra_day])
    campaign = np.concatenate([campaign, np.full(len(first_people), -1), extra_campaign])
    first_trip = np.concatenate([first_trip, np.ones(len(first_people), dtype=bool),
                                 np.zeros(len(extra_person), dtype=bool)])

    # Duplicate records: their first trip is the day they were created; after that, trips split between records.
    record = people.record_id.to_numpy()[person]
    dup_id, dup_created = people.dup_record_id.to_numpy(), people.dup_created.to_numpy()
    use_dup = (dup_id[person] > 0) & (day > dup_created[person]) & (rng.random(len(person)) < 0.5)
    record = np.where(use_dup, dup_id[person], record)
    dup_people = np.flatnonzero(dup_id > 0)
    person = np.concatenate([person, dup_people])
    day = np.concatenate([day, dup_created[dup_people]])
    record = np.concatenate([record, dup_id[dup_people]])
    campaign = np.concatenate([campaign, np.full(len(dup_people), -1)])
    first_trip = np.concatenate([first_trip, np.ones(len(dup_people), dtype=bool)])

    store = people.home.to_numpy()[person]
    store = _sometimes_shop_elsewhere(rng, stores, store, day, first_trip)
    online = (~first_trip) & (rng.random(len(person)) < 0.08 + 0.08 * day / N_DAYS)

    # Coupons: an opted-in customer whose pet matches a running campaign sometimes uses its code.
    primary, secondary = people.primary.to_numpy()[person], people.secondary.to_numpy()[person]
    active = ctx.active_campaign
    matching = np.where(active[primary, day] >= 0, active[primary, day],
                        np.where(secondary >= 0, active[np.maximum(secondary, 0), day], -1))
    regular_coupon = people.opt_in.to_numpy()[person] & (matching >= 0) & (rng.random(len(person)) < 0.30)
    campaign = np.where(campaign >= 0,
                        np.where(rng.random(len(person)) < 0.85, campaign, -1),
                        np.where(regular_coupon, matching, -1))

    # --- Guest checkouts --------------------------------------------------------------------------------------
    guest_store, guest_day = _guest_trips(ctx, GUEST_SHARE * target_sales)
    n_guests = len(guest_store)
    guest_campaign = np.full(n_guests, -1)
    guest_dept = rng.choice(len(DEPARTMENTS), n_guests, p=LINE_DEPARTMENT_WEIGHTS)
    coupon_roll = rng.random(n_guests) < 0.04
    guest_campaign[coupon_roll] = active[guest_dept[coupon_roll], guest_day[coupon_roll]]

    sales = pd.DataFrame({
        'store': np.concatenate([store, guest_store]),
        'day': np.concatenate([day, guest_day]),
        'customer_id': np.concatenate([record, np.zeros(n_guests, dtype=np.int64)]),
        'primary': np.concatenate([primary, np.full(n_guests, -1)]),
        'secondary': np.concatenate([secondary, np.full(n_guests, -1)]),
        'online': np.concatenate([online, np.zeros(n_guests, dtype=bool)]),
        'campaign': np.concatenate([campaign, guest_campaign]),
        'first_trip': np.concatenate([first_trip, np.zeros(n_guests, dtype=bool)]),
    })
    sales['sold_at'] = _sale_seconds(ctx, sales)
    sales = sales.sort_values('sold_at', ignore_index=True)
    sales['id'] = np.arange(1, len(sales) + 1)
    # Prices change at midnight UTC, so a sale's price depends on its UTC date, not the store's local date.
    sales['utc_day'] = (sales.sold_at - day_start_seconds(np.array([0]))[0]) // 86_400
    n = len(sales)

    cancel_rate = np.where(sales.online, 0.03, 0.003)
    sales['cancelled'] = rng.random(n) < cancel_rate
    sales['cancelled_at'] = np.where(sales.cancelled, sales.sold_at + rng.integers(600, 36 * 3600, n), 0)

    staff = active_staff_by_store_month(ctx.employees, SELLING_ROLES)
    store_ids = stores.id.to_numpy()
    sales['employee_id'] = _pick_staff(rng, staff, store_ids[sales.store], DAY_MONTH_INDEX[sales.day])
    sales.loc[sales.online & (rng.random(n) < 0.7), 'employee_id'] = 0

    ctx.sales = sales
    ctx.selling_staff = staff
    ctx.log(f'  {n:,} sales ({sales.customer_id.eq(0).sum():,} guest, {sales.online.sum():,} online, '
            f'{(sales.campaign >= 0).sum():,} with a coupon)')


def _campaign_trips(ctx, scale):
    rng, people = ctx.rng, ctx.people
    persons, days, campaigns = [], [], []
    rate = people.rate.to_numpy()
    opt_in = people.opt_in.to_numpy()
    primary, secondary = people.primary.to_numpy(), people.secondary.to_numpy()
    active_from, active_to = people.active_from.to_numpy(), people.active_to.to_numpy()
    for index, c in enumerate(ctx.campaigns.itertuples()):
        eligible = np.flatnonzero(opt_in & (rate > 0) & ((primary == c.dept_index) | (secondary == c.dept_index))
                                  & (active_from <= c.start) & (active_to >= c.end))
        length = c.end - c.start + 1
        trips = rng.poisson(rate[eligible] * scale * length / 365 * c.lift)
        who = np.repeat(eligible, trips)
        when = c.start + rng.integers(0, length, len(who))
        open_day = DAY_FACTORS[when] > 0
        persons.append(who[open_day])
        days.append(when[open_day])
        campaigns.append(np.full(open_day.sum(), index))
    return np.concatenate(persons), np.concatenate(days), np.concatenate(campaigns)


def _sometimes_shop_elsewhere(rng, stores, store, day, first_trip):
    """A few trips happen at another store in the same region, if it was open that day."""
    away = np.flatnonzero(~first_trip & (rng.random(len(store)) < AWAY_FROM_HOME_SHARE))
    region = stores.region_id.to_numpy()
    starts, ends = stores.window_start.to_numpy(), stores.window_end.to_numpy()
    store = store.copy()
    for region_id in np.unique(region):
        candidates = np.flatnonzero(region == region_id)
        trips = away[region[store[away]] == region_id]
        other = rng.choice(candidates, len(trips))
        open_then = (starts[other] <= day[trips]) & (ends[other] >= day[trips])
        store[trips[open_then]] = other[open_then]
    return store


def _guest_trips(ctx, target):
    rng, stores = ctx.rng, ctx.stores
    total = sum(s.volume * DAY_FACTORS[s.window_start:s.window_end + 1].sum() for s in stores.itertuples())
    per_unit = target / total
    store_out, day_out = [], []
    for i, s in enumerate(stores.itertuples()):
        days = np.arange(s.window_start, s.window_end + 1)
        counts = rng.poisson(per_unit * s.volume * DAY_FACTORS[days])
        store_out.append(np.full(counts.sum(), i))
        day_out.append(np.repeat(days, counts))
    return np.concatenate(store_out), np.concatenate(day_out)


def _sale_seconds(ctx, sales):
    rng = ctx.rng
    n = len(sales)
    online = sales.online.to_numpy()
    hour = np.where(online,
                    rng.choice(24, n, p=ONLINE_HOUR_WEIGHTS / ONLINE_HOUR_WEIGHTS.sum()),
                    rng.choice(IN_STORE_HOURS, n, p=IN_STORE_HOUR_WEIGHTS / IN_STORE_HOUR_WEIGHTS.sum()))
    minute = hour * 60 + rng.integers(0, 60, n)
    zones = ctx.stores.time_zone.to_numpy()[sales.store]
    seconds = local_to_utc_seconds(sales.day.to_numpy(), minute, zones) + rng.integers(0, 60, n)

    # A customer's first trip happens a few minutes after their record was created at the register.
    created_at = dict(zip(ctx.customers.id, ctx.customers.created_at))
    first = sales.first_trip.to_numpy()
    first_created = np.array([created_at[c] for c in sales.customer_id.to_numpy()[first]], dtype=np.int64)
    seconds[first] = first_created + rng.integers(60, 600, first.sum())
    return seconds


def _pick_staff(rng, lookup, store_ids, months):
    out = np.zeros(len(store_ids), dtype=np.int64)
    frame = pd.DataFrame({'store': store_ids, 'month': months})
    for (store_id, month), index in frame.groupby(['store', 'month']).indices.items():
        staff = lookup.get((store_id, month))
        if staff is not None and len(staff):
            out[index] = rng.choice(staff, len(index))
    return out


# --- Lines -------------------------------------------------------------------------------------------------------

class LineMaker:
    """Turns sales into sale lines, the animals they sold and returns, one chunk of sales at a time."""

    def __init__(self, ctx):
        self.ctx = ctx
        products, categories = ctx.products, ctx.categories
        self.product_live = products.live.to_numpy()
        self.product_intro = products.introduced.to_numpy()
        self.product_end = np.where(products.discontinued == NO_DAY, N_DAYS + 1, products.discontinued)
        self.product_dept = products.dept_code.map({d.code: i for i, d in enumerate(DEPARTMENTS)}).to_numpy()
        # Products are numbered from 1; index 0 is unused padding.
        for name in ['product_live', 'product_intro', 'product_end', 'product_dept']:
            values = getattr(self, name)
            setattr(self, name, np.concatenate([np.zeros(1, dtype=values.dtype), values]))

        self.category_ids, self.category_probs, self.category_quantity = [], [], []
        self.category_needs_live, self.category_fallback = [], []
        for d in DEPARTMENTS:
            rows = categories[categories.dept_code == d.code]
            specs = list(rows.spec)
            weights = np.array([[s.sales_share * CATEGORY_SEASONALITY.get(s.name, {}).get(m, 1.0) for s in specs]
                                for m in range(1, 13)])
            self.category_ids.append(rows.id.to_numpy())
            self.category_probs.append(weights / weights.sum(axis=1, keepdims=True))
            self.category_quantity.append([s.quantity for s in specs])
            self.category_needs_live.append(np.array([s.name.startswith('Live') for s in specs]))
            self.category_fallback.append(next(i for i, s in enumerate(specs) if not s.name.startswith('Live')))

        self.store_ids = ctx.stores.id.to_numpy()
        self.store_live = ctx.stores.carries_live.to_numpy()
        self.store_express = (ctx.stores.format == 'express').to_numpy()
        self.store_region = ctx.stores.region_id.to_numpy()
        self.store_start = ctx.stores.window_start.to_numpy()
        self.store_end = ctx.stores.window_end.to_numpy()
        self.next_line_id = 1
        self.next_animal_id = 1
        self.returns = []
        self.return_staff = active_staff_by_store_month(ctx.employees, SELLING_ROLES)

    def chunks(self):
        sales = self.ctx.sales
        for start in range(0, len(sales), CHUNK_SALES):
            yield self.make(sales.iloc[start:start + CHUNK_SALES])

    def make(self, sales):
        rng, ctx = self.ctx.rng, self.ctx
        n_sales = len(sales)
        n_lines = np.minimum(1 + rng.poisson(MEAN_LINES_PER_SALE - 1, n_sales), 10)
        sale_pos = np.repeat(np.arange(n_sales), n_lines)
        line_number = np.arange(len(sale_pos)) - np.repeat(np.cumsum(n_lines) - n_lines, n_lines) + 1
        n = len(sale_pos)

        day = sales.day.to_numpy()[sale_pos]
        store = sales.store.to_numpy()[sale_pos]
        online = sales.online.to_numpy()[sale_pos]
        cancelled = sales.cancelled.to_numpy()[sale_pos]
        primary = sales.primary.to_numpy()[sale_pos]
        secondary = sales.secondary.to_numpy()[sale_pos]
        campaign = sales.campaign.to_numpy()[sale_pos]
        campaigns = ctx.campaigns
        coupon_dept = np.where(campaign >= 0, campaigns.dept_index.to_numpy()[np.maximum(campaign, 0)], -1)

        # Which kind of pet each line is for.
        roll = rng.random(n)
        anyone = rng.choice(len(DEPARTMENTS), n, p=LINE_DEPARTMENT_WEIGHTS)
        dept = np.where(primary < 0, anyone,
                        np.where(roll < 0.72, primary,
                                 np.where((roll < 0.86) & (secondary >= 0), secondary, anyone)))
        on_coupon = (coupon_dept >= 0) & ((line_number == 1) | (rng.random(n) < 0.5))
        dept = np.where(on_coupon, coupon_dept, dept)

        # Category, by department and month, then product by popularity.
        month = DAY_MONTHS[day] - 1
        category_pos = np.zeros(n, dtype=np.int64)
        for d in range(len(DEPARTMENTS)):
            for m in range(12):
                mask = np.flatnonzero((dept == d) & (month == m))
                if len(mask):
                    probs = self.category_probs[d][m]
                    category_pos[mask] = rng.choice(len(probs), len(mask), p=probs)
        no_live = online | ~self.store_live[store]
        for d in range(len(DEPARTMENTS)):
            rows = np.flatnonzero((dept == d) & no_live)
            swap = rows[self.category_needs_live[d][category_pos[rows]]]
            category_pos[swap] = self.category_fallback[d]

        product = np.zeros(n, dtype=np.int64)
        quantity = np.ones(n, dtype=np.int64)
        express = self.store_express[store]
        for d in range(len(DEPARTMENTS)):
            for c, category_id in enumerate(self.category_ids[d]):
                mask = np.flatnonzero((dept == d) & (category_pos == c))
                if not len(mask):
                    continue
                sampler = ctx.samplers[category_id]
                chosen = sampler.sample(rng, len(mask), express[mask])
                for _ in range(6):
                    stale = np.flatnonzero((self.product_intro[chosen] > day[mask]) | (self.product_end[chosen] < day[mask]))
                    if not len(stale):
                        break
                    chosen[stale] = sampler.sample(rng, len(stale), express[mask][stale])
                stale = (self.product_intro[chosen] > day[mask]) | (self.product_end[chosen] < day[mask])
                chosen[stale] = sampler.product_ids[0]
                product[mask] = chosen
                values, weights = QUANTITY_DISTRIBUTIONS[self.category_quantity[d][c]]
                quantity[mask] = rng.choice(values, len(mask), p=weights)

        live = self.product_live[product]
        quantity[live] = 1
        price, cost = price_on(ctx, product, sales.utc_day.to_numpy()[sale_pos])
        percent = np.where(campaign >= 0, campaigns.discount_percent.to_numpy()[np.maximum(campaign, 0)], 0)
        discount = np.where(on_coupon, np.round(quantity * price * percent / 100), 0).astype(np.int64)

        line_ids = np.arange(self.next_line_id, self.next_line_id + n)
        self.next_line_id += n

        # Each live animal sold in a completed sale is a specific animal, received at that store shortly before.
        sold_animal = live & ~cancelled
        animal_id = np.zeros(n, dtype=np.int64)
        n_animals = int(sold_animal.sum())
        animal_id[sold_animal] = np.arange(self.next_animal_id, self.next_animal_id + n_animals)
        self.next_animal_id += n_animals
        received = np.maximum(day[sold_animal] - rng.integers(2, 76, n_animals), self.store_start[store[sold_animal]])
        animals = self._animal_rows(animal_id[sold_animal], product[sold_animal], store[sold_animal], received)

        lines = pd.DataFrame({
            'id': line_ids,
            'sale_id': sales.id.to_numpy()[sale_pos],
            'line_number': line_number,
            'product_id': product,
            'animal_id': animal_id,
            'quantity': quantity,
            'unit_price': price / 100,
            'unit_cost': cost / 100,
            'discount_amount': discount / 100,
            # Cancelling a sale changes its lines too (any animal goes back on sale).
            'updated_at': seconds_to_strings(np.where(cancelled, sales.cancelled_at.to_numpy()[sale_pos],
                                                      sales.sold_at.to_numpy()[sale_pos])),
        })
        self._collect_returns(sales, sale_pos, lines, price, discount, live)
        return animals, lines

    def _animal_rows(self, ids, product, store, received):
        rng = self.ctx.rng
        n = len(ids)
        young = self.product_dept[product] == 4  # Small animals are sold young.
        age = np.where(young, rng.integers(20, 120, n), rng.integers(30, 400, n))
        named = rng.random(n) < 0.15
        return pd.DataFrame({
            'id': ids,
            'product_id': product,
            'store_id': self.store_ids[store],
            'name': np.where(named, rng.choice(PET_NAMES, n), ''),
            'sex': rng.choice(['male', 'female', 'unknown'], n, p=[.4, .4, .2]),
            'born': received - age,
            'received': received,
            'removed': NO_DAY,
            'removal_reason': '',
        })

    def _collect_returns(self, sales, sale_pos, lines, price, discount, live):
        rng = self.ctx.rng
        completed = np.flatnonzero(~sales.cancelled.to_numpy())
        returned = completed[rng.random(len(completed)) < 0.025]
        if not len(returned):
            return
        # One line of each returned sale comes back.
        first_line = np.searchsorted(sale_pos, returned)
        line_count = np.searchsorted(sale_pos, returned, side='right') - first_line
        line = first_line + (rng.random(len(returned)) * line_count).astype(int)

        quantity = lines.quantity.to_numpy()[line]
        back = 1 + (rng.random(len(line)) * quantity).astype(int)
        line_total = quantity * price[line] - discount[line]
        refund = np.round(line_total * back / quantity).astype(np.int64)

        sold_at = sales.sold_at.to_numpy()[returned]
        delay = np.minimum(rng.exponential(6 * 86_400, len(line)), 60 * 86_400).astype(np.int64) + 3600
        returned_at = sold_at + delay
        last_second = day_start_seconds(np.array([N_DAYS])) - 1
        keep = returned_at <= last_second
        sale_store = sales.store.to_numpy()[returned]
        return_day = (returned_at - day_start_seconds(np.array([0]))) // 86_400
        store = sale_store.copy()
        elsewhere = rng.random(len(store)) < 0.15
        for region_id in np.unique(self.store_region):
            candidates = np.flatnonzero(self.store_region == region_id)
            pick = np.flatnonzero(elsewhere & (self.store_region[store] == region_id))
            other = rng.choice(candidates, len(pick))
            open_then = (self.store_start[other] <= return_day[pick]) & (self.store_end[other] >= return_day[pick])
            store[pick[open_then]] = other[open_then]
        keep &= (self.store_start[store] <= return_day) & (self.store_end[store] >= return_day)

        reasons, weights = RETURN_REASONS
        self.returns.append(pd.DataFrame({
            'sale_id': sales.id.to_numpy()[returned],
            'store': store,
            'returned_at': returned_at,
            'month': DAY_MONTH_INDEX[np.minimum(return_day, N_DAYS - 1)],
            'reason': rng.choice(reasons, len(line), p=weights),
            'sale_line_id': lines.id.to_numpy()[line],
            'quantity': back,
            'refund_amount': refund / 100,
            'restocked': ~live[line] & (rng.random(len(line)) < 0.6),
        })[keep])

    def finish_returns(self):
        rng = self.ctx.rng
        if not self.returns:
            return pd.DataFrame()
        returns = pd.concat(self.returns, ignore_index=True).sort_values('returned_at', ignore_index=True)
        returns['id'] = np.arange(1, len(returns) + 1)
        returns['store_id'] = self.store_ids[returns.store]
        returns['employee_id'] = _pick_staff(rng, self.return_staff, returns.store_id.to_numpy(),
                                             returns.month.to_numpy())
        return returns

    def extra_animals(self):
        """Animals still waiting in stores at the end of the history, and ones that died or went back."""
        ctx, rng = self.ctx, self.ctx.rng
        live_products = ctx.products[ctx.products.live]
        rows = []
        stocked = np.flatnonzero(self.store_live & (self.store_end == N_DAYS - 1))
        for store in stocked:
            counts = rng.poisson(1.0, len(live_products))
            product = np.repeat(live_products.id.to_numpy(), counts)
            received = np.maximum(N_DAYS - 1 - rng.integers(0, 60, len(product)), self.store_start[store])
            rows.append((product, np.full(len(product), store), received, np.full(len(product), NO_DAY)))

        n_removed = max(1, (self.next_animal_id - 1) // 25)
        live_stores = np.flatnonzero(self.store_live)
        store = rng.choice(live_stores, n_removed)
        received = rng.integers(self.store_start[store], self.store_end[store] - 1)
        removed = np.minimum(received + rng.integers(1, 46, n_removed), self.store_end[store])
        rows.append((rng.choice(live_products.id.to_numpy(), n_removed), store, received, removed))

        product = np.concatenate([r[0] for r in rows])
        store = np.concatenate([r[1] for r in rows])
        received = np.concatenate([r[2] for r in rows])
        removed = np.concatenate([r[3] for r in rows])
        ids = np.arange(self.next_animal_id, self.next_animal_id + len(product))
        self.next_animal_id += len(product)
        animals = self._animal_rows(ids, product, store, received)
        animals['removed'] = removed
        is_removed = removed != NO_DAY
        animals.loc[is_removed, 'removal_reason'] = rng.choice(
            ['deceased', 'returned_to_breeder', 'transferred_out'], is_removed.sum(), p=[.7, .25, .05])
        return animals

    def caretakers(self, animal_store_ids, animal_ids, received):
        rng = self.ctx.rng
        staff = active_staff_by_store_month(self.ctx.employees, ['animal_care'])
        months = DAY_MONTH_INDEX[np.clip(received, 0, N_DAYS - 1)]
        first = _pick_staff(rng, staff, animal_store_ids, months)
        second = _pick_staff(rng, staff, animal_store_ids, months)
        pairs = pd.DataFrame({'animal_id': np.concatenate([animal_ids, animal_ids]),
                              'employee_id': np.concatenate([first, np.where(rng.random(len(second)) < 0.3,
                                                                             second, 0)])})
        pairs = pairs[pairs.employee_id > 0].drop_duplicates()
        pairs['id'] = np.arange(1, len(pairs) + 1)
        return pairs


# Shares of a store's products that are out of stock, or low and waiting for a delivery, at any moment.
OUT_OF_STOCK_SHARE = 0.01
AWAITING_DELIVERY_SHARE = 0.03


def build_stock_levels(ctx):
    """What every open store has on the shelf at the end of the history.

    Each product has a shelf target that grows with how well it sells, a reorder point at about a third of that, and
    is reordered up to the target. Most products sit somewhere in that cycle above the reorder point; about 3% are at
    or below it waiting for a delivery, and about 1% are out of stock. Stock has its own random stream, so changing
    how it is drawn never changes the sales.
    """
    rng = np.random.default_rng([ctx.seed, 7])
    stores, products = ctx.stores, ctx.products
    end_day = N_DAYS - 1
    carried = products[~products.live & (products.introduced <= end_day) & (products.discontinued == NO_DAY)]
    needs_live = carried.category_id.isin(
        ctx.categories.id[ctx.categories.name.str.startswith('Live')])
    express_ok = np.zeros(len(carried), dtype=bool)
    for category_id, sampler in ctx.samplers.items():
        top = set(sampler.product_ids[:sampler.express_count])
        in_category = (carried.category_id == category_id).to_numpy()
        express_ok[in_category] = carried.id[in_category].isin(top).to_numpy()
    category_max = carried.groupby('category_id').weight.transform('max')
    popularity = (carried.weight / category_max).to_numpy()

    frames = []
    for s in stores[stores.window_end == end_day].itertuples():
        mask = np.ones(len(carried), dtype=bool) if s.format != 'express' else express_ok & ~needs_live.to_numpy()
        target = 6 + 40 * popularity[mask] * s.volume
        reorder_point = np.maximum(2, np.round(target * 0.35)).astype(int)
        order_up_to = reorder_point + np.maximum(3, np.round(target * 0.8)).astype(int)
        quantity = rng.integers(reorder_point + 1, order_up_to + 1)
        state = rng.random(len(quantity))
        low = state < AWAITING_DELIVERY_SHARE + OUT_OF_STOCK_SHARE
        quantity[low] = rng.integers(1, reorder_point[low] + 1)
        quantity[state < OUT_OF_STOCK_SHARE] = 0
        frames.append(pd.DataFrame({'store_id': s.id, 'product_id': carried.id.to_numpy()[mask],
                                    'quantity_on_hand': quantity, 'reorder_point': reorder_point}))
    stock = pd.concat(frames, ignore_index=True)
    stock['id'] = np.arange(1, len(stock) + 1)
    return stock
