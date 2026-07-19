"""
Strategy pattern (Open/Closed Principle): the service layer depends on
this interface, not on a concrete algorithm. Adding Token Bucket later
means adding a class here — zero changes to repository, service, or API code.
"""
from abc import ABC, abstractmethod
from redis import Redis

from rate_limiter.domain.entities import RateLimitDecision


class RateLimitStrategy(ABC):
    """Each strategy owns its Redis key scheme and its Lua script."""

    @abstractmethod
    def check_and_consume(
        self,
        redis_client: Redis,
        client_id: str,
        resource: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        """Atomically check whether a request is allowed and, if so, consume one unit."""
        raise NotImplementedError


class SlidingWindowCounterStrategy(RateLimitStrategy):
    """
    Approximates a rolling window using two fixed windows (current + previous)
    weighted by time-overlap. O(1) memory (2 keys per client+resource),
    single atomic round trip via Lua.
    """

    # Loaded once per process from the .lua file (see redis_repository.py for SCRIPT LOAD).
    def __init__(self, script_sha_provider):
        # script_sha_provider is a callable returning the SHA of the loaded Lua script,
        # injected by the repository so this class doesn't do file I/O itself.
        self._script_sha_provider = script_sha_provider

    def check_and_consume(
        self,
        redis_client: Redis,
        client_id: str,
        resource: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        import time

        now_ms = int(time.time() * 1000)
        window_ms = window_seconds * 1000

        current_key = f"rl:{{{client_id}}}:{resource}:current"
        previous_key = f"rl:{{{client_id}}}:{resource}:previous"
        # Note: hash tag {client_id} ensures both keys land on the same Redis Cluster
        # slot, so the Lua script works correctly if we move to Redis Cluster later.

        sha = self._script_sha_provider()
        result = redis_client.evalsha(
            sha,
            2,
            current_key,
            previous_key,
            now_ms,
            window_ms,
            limit,
        )
        allowed, remaining, retry_after_ms = result
        return RateLimitDecision(
            allowed=bool(allowed),
            remaining=int(remaining),
            limit=limit,
            retry_after_seconds=max(0, int(retry_after_ms) // 1000),
        )