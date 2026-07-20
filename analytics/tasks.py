"""
Celery tasks: one triggered per rate-limit check (fire-and-forget from the
API view), one periodic rollup driven by Celery Beat.
"""
import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.utils import timezone

from analytics.repositories.analytics_repository import analytics_repository

logger = logging.getLogger("analytics")


@shared_task(
    name="rate_limiter.log_rate_limit_request",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=5,
)
def log_rate_limit_request(client_id: str, resource: str, allowed: bool, remaining: int, degraded: bool) -> None:
    """
    Persists one RequestLog row. Retries with backoff on transient Postgres
    failures (up to 5 attempts, then dead-letters via Celery's failure
    handling) — this is what makes "Postgres down" non-fatal to logging,
    per the fail-safe requirement, without ever touching the hot path.
    """
    analytics_repository.insert_log(
        client_id=client_id, resource=resource, allowed=allowed, remaining=remaining, degraded=degraded
    )


@shared_task(name="analytics.rollup_usage_aggregates")
def rollup_usage_aggregates() -> None:
    """
    Runs hourly (scheduled via Celery Beat, see CELERY_BEAT_SCHEDULE).
    Rolls up the PREVIOUS full hour, not the current one, so we never
    aggregate a partially-complete bucket.
    """
    now = timezone.now()
    bucket_start = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    written = analytics_repository.rollup_hour(bucket_start)
    logger.info("Rolled up %d aggregate rows for bucket_start=%s", written, bucket_start)