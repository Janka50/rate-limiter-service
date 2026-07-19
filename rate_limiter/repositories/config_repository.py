"""
Repository for client/limit configuration. Reads are cache-first (Redis,
via Django's cache framework) with Postgres as the fallback and source of
truth — this keeps the hot path off Postgres entirely under normal operation.
"""
import logging

from django.core.cache import cache
from django.conf import settings

from rate_limiter.domain.entities import LimitConfig
from rate_limiter.exceptions import ClientNotFoundError, LimitConfigNotFoundError
from rate_limiter.models import Client, ClientLimitConfig

logger = logging.getLogger("rate_limiter")

_CACHE_KEY_TEMPLATE = "rl_config:{client_id}:{resource}"


class ConfigRepository:
    def get_limit_config(self, client_id: str, resource: str) -> LimitConfig:
        cache_key = _CACHE_KEY_TEMPLATE.format(client_id=client_id, resource=resource)
        cached = cache.get(cache_key)
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
        cache.set(cache_key, limit_config, timeout=settings.CONFIG_CACHE_TTL_SECONDS)
        return limit_config

    def get_fail_policy(self, client_id: str) -> str:
        """
        Separate cached lookup so a Postgres outage doesn't take down fail-policy
        resolution either — falls back to the global default from settings.
        """
        cache_key = f"rl_fail_policy:{client_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            client = Client.objects.get(client_id=client_id)
            policy = client.fail_policy
        except Client.DoesNotExist:
            policy = settings.DEFAULT_FAIL_POLICY
        cache.set(cache_key, policy, timeout=settings.CONFIG_CACHE_TTL_SECONDS)
        return policy


config_repository = ConfigRepository()