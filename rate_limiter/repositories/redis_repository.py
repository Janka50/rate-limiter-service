"""
Repository pattern: isolates all raw Redis access (connection handling,
script loading, circuit breaker) behind a clean interface.
"""
import logging
import threading
from pathlib import Path

import pybreaker
from django_redis import get_redis_connection
from redis.exceptions import RedisError, NoScriptError

from rate_limiter.domain.entities import RateLimitDecision
from rate_limiter.domain.strategies import SlidingWindowCounterStrategy
from rate_limiter.exceptions import RedisUnavailableError

logger = logging.getLogger("rate_limiter")

_LUA_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "sliding_window.lua"

redis_breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=10, exclude=[])


class RedisRateLimitRepository:
    """
    Owns the Redis connection, script SHA cache, and circuit breaker.
    Script loading is lazy and self-healing.

    NOTE: uses RLock (reentrant), not Lock, because load_script() is called
    both externally (e.g. warm-up in wsgi.py) and internally from _get_sha's
    double-checked-locking path on the same thread — a plain Lock would
    deadlock on that internal call. (This was a real bug caught by the
    integration test suite hanging — see race-condition writeup.)
    """

    def __init__(self) -> None:
        self._sha: str | None = None
        self._sha_lock = threading.RLock()
        self._strategy = SlidingWindowCounterStrategy(script_sha_provider=self._get_sha)

    def load_script(self) -> str:
        """Load (or reload) the Lua script into Redis's script cache."""
        client = get_redis_connection("default")
        script_body = _LUA_SCRIPT_PATH.read_text()
        with self._sha_lock:
            self._sha = client.script_load(script_body)
            logger.info("Loaded sliding_window.lua with SHA=%s", self._sha)
            return self._sha

    def _get_sha(self) -> str:
        """Double-checked locking: cheap read in the common case, safe first-load."""
        if self._sha is None:
            with self._sha_lock:
                if self._sha is None:
                    return self.load_script()
        return self._sha

    @redis_breaker
    def _check_and_consume_raw(
        self, client_id: str, resource: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        client = get_redis_connection("default")
        try:
            return self._strategy.check_and_consume(
                client, client_id, resource, limit, window_seconds
            )
        except NoScriptError:
            logger.warning("NOSCRIPT from Redis — reloading sliding_window.lua and retrying once")
            self.load_script()
            return self._strategy.check_and_consume(
                client, client_id, resource, limit, window_seconds
            )
        except RedisError as exc:
            logger.warning("Redis error during rate check: %s", exc)
            raise

    def check_and_consume(
        self, client_id: str, resource: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        try:
            return self._check_and_consume_raw(client_id, resource, limit, window_seconds)
        except pybreaker.CircuitBreakerError as exc:
            raise RedisUnavailableError("Circuit open: Redis presumed down") from exc
        except RedisError as exc:
            raise RedisUnavailableError(str(exc)) from exc


redis_rate_limit_repository = RedisRateLimitRepository()