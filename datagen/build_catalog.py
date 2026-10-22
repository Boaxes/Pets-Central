"""Departments, categories, brands, species, products and price history."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .build_org import NO_DAY
from .reference import BRAND_FIRST, BRAND_SECOND, DEPARTMENTS, HOUSE_BRAND, SPECIES
from .timeline import END, START, day_index

PRODUCT_SHARE = {'DOG': .36, 'CAT': .30, 'FISH': .12, 'BIRD': .06, 'SMALL': .08, 'REP': .08}
NAME_EXTRAS = ['', 'Value Pack', 'Plus', 'Pro', 'Natural', 'Original', 'Lite', 'Select', 'Classic', 'Max']
ALWAYS_STOCKED_RANKS = 3  # The top sellers in every category exist for the whole history.
DAY_KEY = 2 ** 20
DAY_OFFSET = 100_000


@dataclass
class CategorySampler:
    """Product ids in a category, most popular first, with cumulative popularity for fast sampling."""

    product_ids: np.ndarray
    cumulative: np.ndarray
    express_count: int  # Express stores carry only this many of the top sellers.

    def sample(self, rng, n, express_mask):
        limit = np.where(express_mask, self.cumulative[self.express_count - 1], self.cumulative[-1])
        positions = np.searchsorted(self.cumulative, rng.random(n) * limit, side='right')
        return self.product_ids[np.minimum(positions, len(self.product_ids) - 1)]


def round_price(dollars):
    """Retail prices end in .99, or .x9 under $5. Returns cents."""
    dollars = np.asarray(dollars, dtype=float)
    return np.where(dollars >= 5, np.ceil(dollars) * 100 - 1, np.ceil(dollars * 10) * 10 - 1).astype(np.int64)


def build_catalog(ctx):
    rng = ctx.rng
    departments = pd.DataFrame({'id': range(1, len(DEPARTMENTS) + 1),
                                'code': [d.code for d in DEPARTMENTS],
                                'name': [d.name for d in DEPARTMENTS],
                                'owner_share': [d.owner_share for d in DEPARTMENTS]})
    dept_id = dict(zip(departments.code, departments.id))

    category_rows = []
    for d in DEPARTMENTS:
        for spec in d.categories:
            category_rows.append({'department_id': dept_id[d.code], 'dept_code': d.code, 'name': spec.name,
                                  'spec': spec})
    categories = pd.DataFrame(category_rows)
    categories['id'] = np.arange(1, len(categories) + 1)

    species = pd.DataFrame(SPECIES, columns=['common_name', 'scientific_name', 'dept_code', 'price', 'weight'])
    species['id'] = np.arange(1, len(species) + 1)
    species['department_id'] = species.dept_code.map(dept_id)

    brands, brands_by_dept = _build_brands(ctx)
    brand_names = dict(zip(brands.id, brands.name))

    start_day, end_day = day_index(START), day_index(END)
    nonlive_total = ctx.size.products - len(species)
    product_rows = []
    for d in DEPARTMENTS:
        nonlive = [c for c in d.categories if not c.live]
        n_dept = round(PRODUCT_SHARE[d.code] * nonlive_total)
        assortment = sum(c.assortment_share for c in nonlive)
        for spec in d.categories:
            category_id = int(categories.id[(categories.dept_code == d.code) & (categories.name == spec.name)].iloc[0])
            if spec.live:
                for s in species[species.dept_code == d.code].itertuples():
                    product_rows.append({'category_id': category_id, 'dept_code': d.code, 'name': s.common_name,
                                         'brand_id': None, 'species_id': s.id, 'house': False,
                                         'base_price': s.price, 'weight': s.weight, 'spec': spec})
                continue
            n_category = max(ALWAYS_STOCKED_RANKS + 2, round(spec.assortment_share / assortment * n_dept))
            product_rows.extend(_name_products(rng, spec, d.code, category_id, n_category, brands_by_dept[d.code],
                                               brand_names))

    products = pd.DataFrame(product_rows)
    n = len(products)
    products['live'] = products.species_id.notna()

    # Popularity: a random rank within each category, with sales falling off by rank.
    products['rank'] = 0
    for _, index in products.groupby('category_id').groups.items():
        products.loc[index, 'rank'] = rng.permutation(len(index))
    products['weight'] = np.where(products.live, products.weight, 1.0 / (products['rank'] + 1) ** 0.8)

    old = (products['rank'] < ALWAYS_STOCKED_RANKS) | products.live | (rng.random(n) < 0.8)
    products['introduced'] = np.where(
        old,
        rng.integers(day_index(START.replace(year=2012)), start_day - 30, n),
        rng.integers(start_day, end_day - 60, n),
    )
    discontinue = (products['rank'] >= ALWAYS_STOCKED_RANKS).to_numpy() & ~products.live.to_numpy() & (rng.random(n) < 0.08)
    earliest = np.maximum(products.introduced + 180, start_day)
    discontinue &= earliest < end_day
    products['discontinued'] = NO_DAY
    products.loc[discontinue, 'discontinued'] = rng.integers(earliest[discontinue], end_day)

    # SKUs: department prefix and a number; live animals have their own series.
    products = products.sort_values(['dept_code', 'live', 'introduced'], ignore_index=True)
    products['id'] = np.arange(1, n + 1)
    products['sku'] = ''
    for (dept, live), index in products.groupby(['dept_code', 'live']).groups.items():
        products.loc[index, 'sku'] = [f'{dept}-LIVE-{i:03d}' if live else f'{dept}-{i:05d}'
                                      for i in range(1, len(index) + 1)]

    prices = _build_prices(ctx, products)

    ctx.departments, ctx.categories, ctx.brands, ctx.species = departments, categories, brands, species
    ctx.products, ctx.prices = products, prices
    ctx.samplers = _build_samplers(products)
    _index_prices(ctx)


def _build_brands(ctx):
    rng = ctx.rng
    names, depts = [HOUSE_BRAND], [None]
    used = {HOUSE_BRAND}
    for d in DEPARTMENTS:
        wanted = int(np.clip(PRODUCT_SHARE[d.code] * ctx.size.products / 50, 4, 40))
        made = 0
        while made < wanted:
            name = f'{rng.choice(BRAND_FIRST)} {rng.choice(BRAND_SECOND[d.code])}'
            if name not in used:
                used.add(name)
                names.append(name)
                depts.append(d.code)
                made += 1
    brands = pd.DataFrame({'id': range(1, len(names) + 1), 'name': names, 'dept_code': depts})
    brands['is_house_brand'] = brands.name == HOUSE_BRAND
    by_dept = {d.code: list(brands.id[brands.dept_code == d.code]) for d in DEPARTMENTS}
    # Some brands sell in a second department, like a dog food maker with a cat line.
    codes = [d.code for d in DEPARTMENTS]
    for brand in brands[brands.dept_code.notna()].itertuples():
        if rng.random() < 0.15:
            other = rng.choice([c for c in codes if c != brand.dept_code])
            by_dept[other].append(brand.id)
    return brands, by_dept


def _name_products(rng, spec, dept_code, category_id, count, brand_ids, brand_names):
    branded = spec.name != 'Live Fish'
    brand_choices = brand_ids if branded else [None]
    nouns, sizes = list(spec.nouns), list(spec.sizes)
    extras = NAME_EXTRAS if branded else ['']
    combos = len(brand_choices) * len(nouns) * len(sizes) * len(extras)
    count = min(count, combos)
    rows = []
    for code in rng.choice(combos, size=count, replace=False):
        code, extra = divmod(int(code), len(extras))
        code, size = divmod(code, len(sizes))
        brand, noun = divmod(code, len(nouns))
        brand_id = brand_choices[brand]
        house = branded and rng.random() < 0.08
        if house:
            brand_id = 1
        parts = [brand_names.get(brand_id), nouns[noun], extras[extra]]
        name = ' '.join(p for p in parts if p)
        if sizes[size]:
            name = f'{name}, {sizes[size]}'
        low, high = spec.price_range
        price = np.exp(rng.uniform(np.log(low), np.log(high))) * (0.8 if house else 1.0)
        rows.append({'category_id': category_id, 'dept_code': dept_code, 'name': name, 'brand_id': brand_id,
                     'species_id': None, 'house': house, 'base_price': price, 'weight': 0.0, 'spec': spec})
    return rows


def _build_prices(ctx, products):
    rng = ctx.rng
    start_day, end_day = day_index(START), day_index(END)
    rows = []
    for p in products.itertuples():
        margin_low, margin_high = p.spec.margin_range
        margin = rng.uniform(margin_low, margin_high) + (0.10 if p.house else 0)
        price = int(round_price(p.base_price))
        cost = int(round(price * (1 - margin)))
        day = p.introduced
        changes = rng.poisson(0.5 if p.live else 1.6)
        first_change = max(p.introduced + 30, start_day - 365)
        change_days = np.unique(rng.integers(first_change, end_day, changes)) if first_change < end_day else []
        history = [(day, price, cost)]
        for change_day in change_days:
            if rng.random() < 0.85:
                price = int(round_price(price / 100 * rng.uniform(1.03, 1.10)))
                cost = int(round(cost * rng.uniform(1.03, 1.12)))
            else:
                price = int(round_price(price / 100 * rng.uniform(0.85, 0.95)))
            cost = min(cost, price)
            history.append((int(change_day), price, cost))
        for i, (valid_from, list_cents, cost_cents) in enumerate(history):
            valid_to = history[i + 1][0] if i + 1 < len(history) else NO_DAY
            rows.append((p.id, valid_from, valid_to, list_cents, cost_cents))
    prices = pd.DataFrame(rows, columns=['product_id', 'valid_from', 'valid_to', 'list_cents', 'cost_cents'])
    prices['id'] = np.arange(1, len(prices) + 1)
    return prices


def _build_samplers(products):
    samplers = {}
    for category_id, group in products.groupby('category_id'):
        group = group.sort_values('weight', ascending=False)
        weights = group.weight.to_numpy()
        samplers[category_id] = CategorySampler(
            product_ids=group.id.to_numpy(),
            cumulative=np.cumsum(weights),
            express_count=max(ALWAYS_STOCKED_RANKS, int(np.ceil(len(group) * 0.35))),
        )
    return samplers


def _index_prices(ctx):
    prices = ctx.prices.sort_values(['product_id', 'valid_from'])
    ctx.price_keys = prices.product_id.to_numpy() * DAY_KEY + prices.valid_from.to_numpy() + DAY_OFFSET
    ctx.price_list = prices.list_cents.to_numpy()
    ctx.price_cost = prices.cost_cents.to_numpy()
    ctx.price_product = prices.product_id.to_numpy()


def price_on(ctx, product_ids, days):
    """List price and cost in cents for each product on each day."""
    index = np.searchsorted(ctx.price_keys, product_ids * DAY_KEY + days + DAY_OFFSET, side='right') - 1
    assert (ctx.price_product[index] == product_ids).all(), 'a product was sold before it had a price'
    return ctx.price_list[index], ctx.price_cost[index]
