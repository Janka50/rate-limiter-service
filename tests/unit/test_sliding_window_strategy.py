"""
Unit tests for the Lua-backed sliding window strategy, run against a real
Redis. Time is mocked via unittest.mock.patch("time.time") rather than
real sleep(), so these tests are deterministic and immune to Docker/CI
scheduling jitter — a real sleep-based version of this test proved flaky
under coverage instrumentation (see race-condition writeup).
"""
from unittest.mock import patch

import pytest

from rate_limiter.repositories.redis_repository import redis_rate_limit_repository


@pytest.fixture(autouse=True)
def load_script():
    redis_rate_limit_repository.load_script()


def test_allows_requests_under_limit():
    with patch("time.time", return_value=1_000_000.0):
        for i in range(5):
            decision = redis_rate_limit_repository.check_and_consume("c1", "r1", limit=5, window_seconds=10)
            assert decision.allowed is True
            assert decision.remaining == 4 - i


def test_rejects_request_over_limit():
    with patch("time.time", return_value=1_000_000.0):
        for _ in range(5):
            redis_rate_limit_repository.check_and_consume("c1", "r1", limit=5, window_seconds=10)
        decision = redis_rate_limit_repository.check_and_consume("c1", "r1", limit=5, window_seconds=10)
    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.retry_after_seconds >= 0


def test_window_rolls_over_and_admits_new_requests():
    """
    Deterministic version of the rollover edge case: all 5 'fill' requests
    are pinned to the exact same instant (t0), so they are guaranteed to
    land in the same fixed window — the 6th request at the same instant
    must be denied. Then we jump the clock forward past the window
    boundary and confirm a new request is admitted.
    """
    t0 = 1_000_000.0  # arbitrary fixed epoch second
    window_seconds = 1

    with patch("time.time", return_value=t0):
        for _ in range(5):
            decision = redis_rate_limit_repository.check_and_consume(
                "c2", "r1", limit=5, window_seconds=window_seconds
            )
            assert decision.allowed is True
        denied = redis_rate_limit_repository.check_and_consume(
            "c2", "r1", limit=5, window_seconds=window_seconds
        )
    assert denied.allowed is False, "6th request in the same instant must be denied"

    with patch("time.time", return_value=t0 + window_seconds + 0.1):
        decision = redis_rate_limit_repository.check_and_consume(
            "c2", "r1", limit=5, window_seconds=window_seconds
        )
    assert decision.allowed is True, "request must be admitted once the window has rolled"


def test_independent_clients_do_not_share_counters():
    with patch("time.time", return_value=1_000_000.0):
        for _ in range(5):
            redis_rate_limit_repository.check_and_consume("client-A", "r1", limit=5, window_seconds=10)
        decision_b = redis_rate_limit_repository.check_and_consume("client-B", "r1", limit=5, window_seconds=10)
    assert decision_b.allowed is True, "client-B must not be affected by client-A's usage"