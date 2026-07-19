"""Domain-specific exceptions. Kept separate from Django/DRF exceptions
so the service layer never depends on the web framework (Clean Architecture)."""


class RateLimiterError(Exception):
    """Base exception for all rate limiter domain errors."""


class ClientNotFoundError(RateLimiterError):
    """Raised when a client_id has no matching Client record."""


class LimitConfigNotFoundError(RateLimiterError):
    """Raised when no ClientLimitConfig exists for (client, resource)."""


class RedisUnavailableError(RateLimiterError):
    """Raised when Redis cannot be reached, before fail-policy is applied."""