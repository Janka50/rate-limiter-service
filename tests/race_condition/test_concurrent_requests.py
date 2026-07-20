"""
Race condition tests: fire concurrent requests at the same (client, resource)
from multiple threads simultaneously and assert the counter never overshoots
the configured limit. This is the empirical proof for the atomicity claims
made in Phase 3 — without this test, "atomic" is just an assertion in a comment.
"""
import threading

import pytest

from rate_limiter.repositories.redis_repository import redis_rate_limit_repository


@pytest.fixture(autouse=True)
def load_script():
    redis_rate_limit_repository.load_script()


def test_concurrent_requests_never_exceed_limit():
    limit = 50
    num_threads = 200  # deliberately 4x the limit to stress-test the race window
    results = []
    lock = threading.Lock()

    def worker():
        decision = redis_rate_limit_repository.check_and_consume(
            "race-client", "race-resource", limit=limit, window_seconds=30
        )
        with lock:
            results.append(decision.allowed)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    allowed_count = sum(1 for r in results if r is True)
    assert allowed_count == limit, (
        f"Expected exactly {limit} allowed requests under concurrency, got {allowed_count}. "
        "Any deviation indicates the Lua script is not executing atomically."
    )


def test_concurrent_requests_across_multiple_processes_simulated():
    """
    Simulates multiple app instances (not just threads within one process)
    by using separate Redis connections per 'worker', which is the realistic
    HA scenario — multiple Django instances, one shared Redis.
    """
    from django_redis import get_redis_connection

    limit = 20
    num_workers = 100
    results = []
    lock = threading.Lock()

    def worker():
        # Each thread grabs its own connection from the pool, simulating
        # a separate instance rather than one shared client object.
        conn = get_redis_connection("default")
        from rate_limiter.domain.strategies import SlidingWindowCounterStrategy
        strategy = SlidingWindowCounterStrategy(script_sha_provider=redis_rate_limit_repository._get_sha)
        decision = strategy.check_and_consume(conn, "race-client-2", "race-resource-2", limit=limit, window_seconds=30)
        with lock:
            results.append(decision.allowed)

    threads = [threading.Thread(target=worker) for _ in range(num_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) == limit