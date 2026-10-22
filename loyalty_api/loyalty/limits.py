"""API keys, rate limiting and the occasional failure, the way a vendor API behaves."""

import math
import random
import threading
import time

from fastapi import HTTPException


class RateLimiter:
    """A token bucket per API key, kept in memory. Each Azure Functions instance has its own buckets."""

    def __init__(self, per_second, burst):
        self.per_second, self.burst = per_second, burst
        self.buckets = {}
        self.lock = threading.Lock()

    def check(self, key):
        now = time.monotonic()
        with self.lock:
            tokens, updated = self.buckets.get(key, (self.burst, now))
            tokens = min(self.burst, tokens + (now - updated) * self.per_second)
            if tokens < 1:
                self.buckets[key] = (tokens, now)
                retry_after = math.ceil((1 - tokens) / self.per_second)
                raise HTTPException(429, headers={'Retry-After': str(retry_after)},
                                    detail={'error': 'rate_limited', 'message': 'Too many requests; slow down.'})
            self.buckets[key] = (tokens - 1, now)


def authenticate(api_key, settings):
    if not api_key or not (api_key in settings.api_keys or api_key == settings.demo_key):
        raise HTTPException(401, detail={'error': 'unauthorized', 'message': 'Send a valid X-API-Key header.'})


def maybe_fail(settings):
    if settings.failure_rate and random.random() < settings.failure_rate:
        raise HTTPException(503, headers={'Retry-After': '1'},
                            detail={'error': 'temporarily_unavailable', 'message': 'Please retry.'})
