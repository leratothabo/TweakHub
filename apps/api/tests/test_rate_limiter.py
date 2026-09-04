"""
Unit tests for services/rate_limiter.py's RateLimiter, exercised directly
against a fakeredis client (no HTTP, no real Redis). HTTP-level enforcement
(429s, Retry-After, per-endpoint wiring) is covered by
test_rate_limiting_routes.py.
"""
import os
import sys

import fakeredis
import pytest
import redis as redis_module

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.rate_limiter import RateLimiter  # noqa: E402


@pytest.fixture()
def limiter() -> RateLimiter:
    return RateLimiter(client=fakeredis.FakeRedis())


def test_allows_up_to_the_limit_then_blocks(limiter):
    results = [limiter.hit("k1", limit=3, window_seconds=60) for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert results[-1].retry_after_seconds > 0


def test_remaining_counts_down(limiter):
    first = limiter.hit("k2", limit=5, window_seconds=60)
    second = limiter.hit("k2", limit=5, window_seconds=60)
    assert first.remaining == 4
    assert second.remaining == 3


def test_different_keys_have_independent_counters(limiter):
    for _ in range(3):
        limiter.hit("alice", limit=3, window_seconds=60)
    # alice is now at the limit, but bob hasn't hit it at all
    assert limiter.hit("alice", limit=3, window_seconds=60).allowed is False
    assert limiter.hit("bob", limit=3, window_seconds=60).allowed is True


def test_limit_zero_or_negative_always_allows_without_touching_redis(limiter):
    # A limit of 0 means "unlimited" (see PLAN_RATE_LIMITS_PER_HOUR's
    # ENTERPRISE=None case, which never calls .hit() at all — this covers
    # the defensive case of a misconfigured limit reaching here anyway).
    result = limiter.hit("unused-key", limit=0, window_seconds=60)
    assert result.allowed is True


def test_fails_open_when_redis_is_unreachable():
    class ExplodingClient:
        def incr(self, key):
            raise redis_module.ConnectionError("connection refused")

    limiter = RateLimiter(client=ExplodingClient())
    result = limiter.hit("any-key", limit=1, window_seconds=60)
    assert result.allowed is True


def test_sets_ttl_on_first_hit(limiter):
    limiter.hit("ttl-key", limit=10, window_seconds=120)
    ttl = limiter._get_client().ttl("ttl-key")
    assert 0 < ttl <= 120
