"""
app/services/rate_limiter.py

Redis-backed fixed-window rate limiter, shared by the auth endpoints
(signup/login/password-reset, keyed by client IP), the tool-processing
endpoint (keyed by user id, limit chosen by plan tier), and the DPO
payment callback (keyed by client IP).

Fixed window, not sliding: the first hit against a key sets a TTL of
`window_seconds`, and the count resets when that key expires. That means
the window is anchored to "time of first request in this window" rather
than a fixed clock boundary (e.g. the top of the hour) — simpler to reason
about and implement correctly with a single INCR+EXPIRE, at the cost of
allowing a burst of up to 2x the limit right at a window boundary (a
request at the very end of one window plus a full new window's worth
immediately after). That trade-off is fine here: this is abuse/cost
protection, not a strict quota system.

Fails open on Redis errors (connection refused, timeout, etc.) rather than
blocking every request — logged as a warning so it's visible in practice,
but a Redis hiccup should degrade to "no rate limiting" rather than taking
down login, signup, or tool processing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

import redis

from config import get_settings

logger = logging.getLogger("tweakhub.rate_limiter")


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class RateLimiter:
    """Wraps a redis-py-compatible client. Pass `client` explicitly in tests
    (e.g. a fakeredis instance) — otherwise it's built lazily from
    REDIS_URL on first use, so importing this module never requires a
    reachable Redis."""

    def __init__(self, client=None) -> None:
        self._client = client

    def _get_client(self):
        if self._client is None:
            settings = get_settings()
            self._client = redis.Redis.from_url(
                settings.redis_url, socket_connect_timeout=2, socket_timeout=2
            )
        return self._client

    def hit(self, key: str, limit: int, window_seconds: int = 3600) -> RateLimitResult:
        """Record one hit against `key`. `limit <= 0` disables limiting for
        that key entirely (used for PlanTier.ENTERPRISE and similar
        "unlimited" cases) without a Redis round-trip."""
        if limit <= 0:
            return RateLimitResult(allowed=True, remaining=0, retry_after_seconds=0)

        try:
            client = self._get_client()
            count = client.incr(key)
            if count == 1:
                client.expire(key, window_seconds)
                ttl = window_seconds
            else:
                ttl = client.ttl(key)
                if not ttl or ttl < 0:
                    # Key exists but somehow lost its TTL (e.g. a previous
                    # crash between INCR and EXPIRE) — put one back rather
                    # than leaving the key to live forever.
                    client.expire(key, window_seconds)
                    ttl = window_seconds
        except redis.RedisError as exc:
            logger.warning("Rate limiter backend unavailable (%s) — failing open for key=%s", exc, key)
            return RateLimitResult(allowed=True, remaining=limit, retry_after_seconds=0)

        if count > limit:
            return RateLimitResult(allowed=False, remaining=0, retry_after_seconds=int(ttl))
        return RateLimitResult(allowed=True, remaining=max(0, limit - count), retry_after_seconds=0)


@lru_cache
def get_rate_limiter() -> RateLimiter:
    return RateLimiter()
