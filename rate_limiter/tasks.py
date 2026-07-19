"""Celery tasks. Full implementation (Postgres write) added in Phase 4."""
from celery import shared_task


@shared_task(name="rate_limiter.log_rate_limit_request")
def log_rate_limit_request(client_id: str, resource: str, allowed: bool, remaining: int, degraded: bool) -> None:
    # Phase 4 will persist this to analytics.RequestLog.
    pass