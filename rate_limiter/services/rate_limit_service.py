"""
Service layer: orchestrates config lookup + Redis check + fail-policy
handling. This is the only place business rules about "what happens when
Redis is down" live — API layer just calls this and translates the result
to HTTP.
"""
import logging
import time
from threading import Lock

from rate_limiter.domain.entities import RateLimitDecision
from rate_limiter.exceptions import RedisUnavailableError, ClientNotFoundError, LimitConfigNotFoundError
from rate_limiter.repositories.config_repository import config_repository
from rate_limiter.repositories.redis_repository import redis_rate_limit_repository

logger = logging.getLogger("rate_limiter")


class _LocalFallbackLimiter:
    """
    In-process, per-instance fallback counter used ONLY when Redis is
    unreachable and policy is FAIL_OPEN-with-local-guard. It is intentionally
    approximate (not shared across instances) — the whole point is that it
    activates precisely when the shared source of truth is unavailable.
    Reset naturally on process restart; bounded by a simple fixed window.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: dict[str, tuple[int, int]] = {}  # key -> (window_start, count)

    def check_and_consume(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        now = int(time.time())
        window_start = now - (now % window_seconds)
        with self._lock:
            stored_start, count = self._counts.get(key, (window_start, 0))
            if stored_start != window_start:
                count = 0
                stored_start = window_start
            if count >= limit:
                retry_after = window_seconds - (now - window_start)
                return RateLimitDecision(
                    allowed=False, remaining=0, limit=limit,
                    retry_after_seconds=retry_after, degraded=True,
                )
            count += 1
            self._counts[key] = (stored_start, count)
            return RateLimitDecision(
                allowed=True, remaining=max(0, limit - count), limit=limit,
                retry_after_seconds=0, degraded=True,
            )


class RateLimitService:
    def __init__(self) -> None:
        self._config_repo = config_repository
        self._redis_repo = redis_rate_limit_repository
        self._local_fallback = _LocalFallbackLimiter()

    def check_rate_limit(self, client_id: str, resource: str) -> RateLimitDecision:
        """
        Main entry point used by the API view. Returns a RateLimitDecision
        that is always populated — this method never raises for Redis
        failures; it converts them into a policy-driven decision instead.
        ClientNotFoundError / LimitConfigNotFoundError DO propagate, since
        those are client misconfiguration, not infra failure.
        """
        limit_config = self._config_repo.get_limit_config(client_id, resource)

        try:
            return self._redis_repo.check_and_consume(
                client_id=client_id,
                resource=resource,
                limit=limit_config.limit,
                window_seconds=limit_config.window_seconds,
            )
        except RedisUnavailableError:
            logger.error(
                "Redis unavailable for client=%s resource=%s — applying fail policy",
                client_id, resource,
            )
            return self._apply_fail_policy(client_id, resource, limit_config.limit, limit_config.window_seconds)

    def _apply_fail_policy(
        self, client_id: str, resource: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        policy = self._config_repo.get_fail_policy(client_id)

        if policy == "FAIL_CLOSED":
            # Business decision: reject everything when we can't verify the limit.
            return RateLimitDecision(
                allowed=False, remaining=0, limit=limit,
                retry_after_seconds=window_seconds, degraded=True,
            )

        # FAIL_OPEN, but not "allow everything blindly" — degrade to a local,
        # per-instance approximation so we still offer *some* protection
        # against runaway bursts during the outage.
        fallback_key = f"{client_id}:{resource}"
        return self._local_fallback.check_and_consume(fallback_key, limit, window_seconds)


rate_limit_service = RateLimitService()