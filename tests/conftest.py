"""Shared fixtures across all test suites."""
import pytest
from rest_framework.test import APIClient

from rate_limiter.models import Client, ClientLimitConfig


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def test_client_config(db) -> ClientLimitConfig:
    """A client with a tight, predictable limit — 5 requests per 10 seconds —
    small enough to hit the limit quickly in tests without long sleeps."""
    client = Client.objects.create(client_id="test-client", name="Test Client", fail_policy="FAIL_OPEN")
    return ClientLimitConfig.objects.create(
        client=client, resource="test-resource", limit=5, window_seconds=10, strategy="SLIDING_WINDOW"
    )


@pytest.fixture(autouse=True)
def clear_redis():
    """Flush Redis between tests so counters don't leak across test cases."""
    from django_redis import get_redis_connection
    conn = get_redis_connection("default")
    conn.flushdb()
    yield
    conn.flushdb()