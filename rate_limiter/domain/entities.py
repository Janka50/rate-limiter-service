"""
Plain data objects (no Django ORM dependency) passed between layers.
Keeping these framework-agnostic means the service/domain layer is
independently testable without a database or Django app registry.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LimitConfig:
    """Immutable snapshot of a client's limit for one resource."""
    client_id: str
    resource: str
    limit: int
    window_seconds: int
    strategy: str


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of a rate-limit check, returned all the way up to the API layer."""
    allowed: bool
    remaining: int
    limit: int
    retry_after_seconds: int
    degraded: bool = False  # True if decision was made via fail-safe fallback, not Redis