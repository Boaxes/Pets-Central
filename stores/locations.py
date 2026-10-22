"""Approximate map positions for stores, for the demo sign-in map.

Stores don't store coordinates, so each store is placed near the center of its city, nudged by a small amount worked
out from its store code, so several stores in one city sit apart, and always in the same spots.
"""

import random

from datagen.reference import CITY_COORDINATES


def store_location(store):
    """(latitude, longitude) for a store: its city's center plus a small, stable offset of up to about 5 km."""
    latitude, longitude = CITY_COORDINATES[store.city, store.state]
    rng = random.Random(store.store_code)
    return round(latitude + rng.uniform(-0.06, 0.06), 4), round(longitude + rng.uniform(-0.06, 0.06), 4)
