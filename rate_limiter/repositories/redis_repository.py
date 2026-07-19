"""
Repository pattern: isolates all raw Redis access (connection handling,
script loading, circuit breaker) behind a clean interface. The service
layer depends on this abstraction, never on `redis-py` directly.
"""
import logging
from pathlib import Path

import pybreaker
from django.conf import settings
from django_redis import get_redis_connection
from redis.exceptions import RedisError

from rate_limiter.domain.entities import RateLimitDecision
from rate_limiter.domain.strategies import SlidingWindowCounterStrategy
from rate_limiter.exceptions import RedisUnavailableError

logger = logging.getLogger("rate_limiter")

_LUA_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "sliding_window.lua"

# Circuit breaker: after 5 consecutive Redis failures, open the circuit for
# 10 seconds so we stop paying the connection-timeout cost on every request
# during an outage — fail straight to the fallback policy instead.
redis_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=10,
    exclude=[],  # only RedisError trips it; programming errors should not
)


class RedisRateLimitRepository:
    """Owns the Redis connection, script SHA cache, and circuit breaker."""

    def __init__(self) -> None:
        self._sha: str | None = None
        self._strategy = SlidingWindowCounterStrategy(script_sha_provider=self._get_sha)

    def _get_sha(self) -> str:
        if self._sha is None:
            raise RuntimeError("Lua script not loaded — call load_script() at startup.")
        return self._sha

    def load_script(self) -> None:
        """Load the Lua script into Redis's script cache once (e.g. at app startup)."""
        client = get_redis_connection("default")
        script_body = _LUA_SCRIPT_PATH.read_text()
        self._sha = client.script_load(script_body)
        logger.info("Loaded sliding_window.lua with SHA=%s", self._sha)

    @redis_breaker
    def _check_and_consume_raw(
        self, client_id: str, resource: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        client = get_redis_connection("default")
        try:
            return self._strategy.check_and_consume(
                client, client_id, resource, limit, window_seconds
            )
        except RedisError as exc:
            logger.warning("Redis error during rate check: %s", exc)
            raise  # let pybreaker count this as a failure

    def check_and_consume(
        self, client_id: str, resource: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        """
        Public entry point. Raises RedisUnavailableError if Redis is down or
        the circuit is open — the service layer decides the fail policy from there.
        This repository does NOT decide fail-open/fail-closed; that's a
        business policy decision, which belongs in the service layer.
        """
        try:
            return self._check_and_consume_raw(client_id, resource, limit, window_seconds)
        except pybreaker.CircuitBreakerError as exc:
            raise RedisUnavailableError("Circuit open: Redis presumed down") from exc
        except RedisError as exc:
            raise RedisUnavailableError(str(exc)) from exc


# Module-level singleton: script SHA and breaker state must be shared across
# requests within a process, not recreated per-request.
redis_rate_limit_repository = RedisRateLimitRepository()