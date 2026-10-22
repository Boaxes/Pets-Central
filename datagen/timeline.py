"""Dates the history covers, how busy each day is, and time zone conversion."""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from dateutil.easter import easter

from .reference import ANNUAL_GROWTH, MONTH_FACTOR, WEEKDAY_FACTOR

START = date(2023, 10, 1)
END = date(2026, 9, 30)
ACQUISITION_DATE = date(2025, 4, 1)  # Pets Central buys Critter Corner.

START64 = np.datetime64(START, 'D')
N_DAYS = (END - START).days + 1


@dataclass(frozen=True)
class Size:
    name: str
    stores: int
    products: int
    customers: int
    sale_lines: int


SIZES = {
    'tiny': Size('tiny', stores=6, products=400, customers=800, sale_lines=15_000),
    'small': Size('small', stores=20, products=1_500, customers=10_000, sale_lines=250_000),
    'medium': Size('medium', stores=100, products=8_000, customers=120_000, sale_lines=2_500_000),
    'full': Size('full', stores=200, products=15_000, customers=500_000, sale_lines=10_000_000),
}


def day_index(d):
    return (d - START).days


def day_to_date(day):
    return START + timedelta(days=int(day))


def _thanksgiving(year):
    november_first = date(year, 11, 1)
    first_thursday = november_first + timedelta(days=(3 - november_first.weekday()) % 7)
    return first_thursday + timedelta(weeks=3)


def _holiday_factor(d):
    thanksgiving = _thanksgiving(d.year)
    if d == thanksgiving or (d.month, d.day) == (12, 25):
        return 0.0  # Stores are closed.
    if d == thanksgiving + timedelta(days=1):
        return 1.8  # Black Friday.
    if d.month == 12 and 15 <= d.day <= 23:
        return 1.35
    if (d.month, d.day) == (12, 24):
        return 1.15
    if (d.month, d.day) == (1, 1):
        return 0.55
    if (d.month, d.day) == (7, 4):
        return 0.7
    if d == easter(d.year):
        return 0.5
    return 1.0


def build_day_factors():
    """Relative store traffic for every day, averaging 1.0. Closed days are 0."""
    factors = np.empty(N_DAYS)
    for day in range(N_DAYS):
        d = day_to_date(day)
        growth = (1 + ANNUAL_GROWTH) ** (day / 365.25)
        factors[day] = MONTH_FACTOR[d.month] * WEEKDAY_FACTOR[d.weekday()] * _holiday_factor(d) * growth
    return factors / factors.mean()


DAY_FACTORS = build_day_factors()
DAY_MONTHS = np.array([day_to_date(d).month for d in range(N_DAYS)])
# Month number counted from START, used to group work by store and month.
DAY_MONTH_INDEX = np.array([(day_to_date(d).year - START.year) * 12 + day_to_date(d).month - START.month
                            for d in range(N_DAYS)])
N_MONTHS = DAY_MONTH_INDEX[-1] + 1
MONTH_FIRST_DAY = np.array([np.argmax(DAY_MONTH_INDEX == m) for m in range(N_MONTHS)])
MONTH_LAST_DAY = np.array([N_DAYS - 1 - np.argmax(DAY_MONTH_INDEX[::-1] == m) for m in range(N_MONTHS)])


def local_to_utc_seconds(day, minute_of_day, time_zones):
    """Convert local store times (days from START, minute of day) to Unix seconds in UTC."""
    local = pd.Series(START64 + day.astype('timedelta64[D]')).astype('datetime64[s]') + pd.to_timedelta(minute_of_day, unit='m')
    out = np.empty(len(day), dtype=np.int64)
    zones = pd.Series(time_zones)
    for tz in zones.unique():
        mask = (zones == tz).to_numpy()
        converted = pd.DatetimeIndex(local[mask]).tz_localize(tz, ambiguous=False, nonexistent='shift_forward')
        out[mask] = converted.tz_convert('UTC').as_unit('s').asi8
    return out


def days_to_strings(days, missing=None):
    """Days from START as ISO dates. Days equal to `missing` become empty strings (NULL)."""
    text = np.datetime_as_string(START64 + np.asarray(days).astype('timedelta64[D]'), unit='D').astype(object)
    if missing is not None:
        text[np.asarray(days) == missing] = ''
    return text


def seconds_to_strings(seconds):
    text = np.datetime_as_string(np.asarray(seconds).astype('datetime64[s]'), unit='s').astype(object)
    return text + '+00:00'


def day_start_seconds(days):
    return (START64 + np.asarray(days).astype('timedelta64[D]')).astype('datetime64[s]').astype(np.int64)
