"""
Unit tests for the service layer, with repositories mocked — this is
where fail-open/fail-closed policy logic is verified in isolation,
without needing Redis to actually be down.
"""
from unittest.mock import MagicMock, patch

import pytest

from rate_limiter.domain.entities import LimitConfig
from rate_limiter.exceptions import RedisUnavailableError
from rate_limiter.services.rate_limit_service import RateLimitService


@pytest.fixture
def service():
    return RateLimitService()


def _fake_config(fail_policy="FAIL_OPEN"):
    return LimitConfig(client_id="c1", resource="r1", limit=10, window_seconds=60, strategy="SLIDING_WINDOW")


def test_fail_open_degrades_to_local_fallback_instead_of_blind_allow(service):
    with patch.object(service, "_config_repo") as mock_config_repo, \
         patch.object(service, "_redis_repo") as mock_redis_repo:
        mock_config_repo.get_limit_config.return_value = _fake_config()
        mock_config_repo.get_fail_policy.return_value = "FAIL_OPEN"
        mock_redis_repo.check_and_consume.side_effect = RedisUnavailableError("down")

        decision = service.check_rate_limit("c1", "r1")

        assert decision.degraded is True
        assert decision.allowed is True  # first request within the local fallback's own limit


def test_fail_closed_rejects_when_redis_down(service):
    with patch.object(service, "_config_repo") as mock_config_repo, \
         patch.object(service, "_redis_repo") as mock_redis_repo:
        mock_config_repo.get_limit_config.return_value = _fake_config()
        mock_config_repo.get_fail_policy.return_value = "FAIL_CLOSED"
        mock_redis_repo.check_and_consume.side_effect = RedisUnavailableError("down")

        decision = service.check_rate_limit("c1", "r1")

        assert decision.allowed is False
        assert decision.degraded is True


def test_local_fallback_still_enforces_a_cap(service):
    """Even in FAIL_OPEN, the local fallback must eventually reject —
    proving Phase 3's design note (fail-open ≠ unlimited) is actually true."""
    with patch.object(service, "_config_repo") as mock_config_repo, \
         patch.object(service, "_redis_repo") as mock_redis_repo:
        mock_config_repo.get_limit_config.return_value = _fake_config()
        mock_config_repo.get_fail_policy.return_value = "FAIL_OPEN"
        mock_redis_repo.check_and_consume.side_effect = RedisUnavailableError("down")

        decisions = [service.check_rate_limit("c1", "r1") for _ in range(11)]

        assert decisions[-1].allowed is False, "11th request must exceed the limit=10 fallback cap"