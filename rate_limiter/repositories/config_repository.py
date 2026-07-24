"""
Repository for client/limit configuration. Reads are cache-first (Redis,
via Django's cache framework) with Postgres as the fallback and source of
truth. If the Redis cache itself is unreachable, that failure must not
propagate — a cache is optional infrastructure by definition, so any
Redis error here is treated as a cache miss and we fall through to
Postgres directly. (Caught by manual fail-safe verification — see notes.)
"""
import logging

from django.core.cache import cache
from django.conf import settings
from redis.exceptions import RedisError

from rate_limiter.domain.entities import LimitConfig
from rate_limiter.exceptions import ClientNotFoundError, LimitConfigNotFoundError
from rate_limiter.models import Client, ClientLimitConfig

logger = logging.getLogger("rate_limiter")

_CACHE_KEY_TEMPLATE = "rl_config:{client_id}:{resource}"


class ConfigRepository:
    def _safe_cache_get(self, cache_key: str):
        """Cache reads must never be able to crash the request. Any error
        talking to the cache backend is treated as a miss."""
        try:
            return cache.get(cache_key)
        except RedisError as exc:
            logger.warning("Cache unavailable during config lookup (%s) — falling back to Postgres", exc)
            return None

    def _safe_cache_set(self, cache_key: str, value, timeout: int) -> None:
        """Cache writes must never be able to crash the request either —
        if we can't warm the cache, the next request just falls back to
        Postgres again, which is correct, just slightly slower."""
        try:
            cache.set(cache_key, value, timeout=timeout)
        except RedisError as exc:
            logger.warning("Could not write config to cache (%s) — continuing without cache", exc)

    def get_limit_config(self, client_id: str, resource: str) -> LimitConfig:
        cache_key = _CACHE_KEY_TEMPLATE.format(client_id=client_id, resource=resource)
        cached = self._safe_cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            client = Client.objects.get(client_id=client_id, is_active=True)
        except Client.DoesNotExist as exc:
            raise ClientNotFoundError(f"No active client '{client_id}'") from exc

        try:
            config_row = ClientLimitConfig.objects.get(client=client, resource=resource)
        except ClientLimitConfig.DoesNotExist as exc:
            raise LimitConfigNotFoundError(
                f"No limit config for client '{client_id}' resource '{resource}'"
            ) from exc

        limit_config = LimitConfig(
            client_id=client_id,
            resource=resource,
            limit=config_row.limit,
            window_seconds=config_row.window_seconds,
            strategy=config_row.strategy,
        )
        self._safe_cache_set(cache_key, limit_config, timeout=settings.CONFIG_CACHE_TTL_SECONDS)
        return limit_config

    def get_fail_policy(self, client_id: str) -> str:
        cache_key = f"rl_fail_policy:{client_id}"
        cached = self._safe_cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            client = Client.objects.get(client_id=client_id)
            policy = client.fail_policy
        except Client.DoesNotExist:
            policy = settings.DEFAULT_FAIL_POLICY
        self._safe_cache_set(cache_key, policy, timeout=settings.CONFIG_CACHE_TTL_SECONDS)
        return policy


config_repository = ConfigRepository()