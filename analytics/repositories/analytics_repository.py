"""
Repository for analytics reads/writes. Isolates ORM queries from the
Celery task bodies and API views, so both can be tested against a mocked
repository without touching Postgres.
"""
from datetime import datetime, timedelta

from django.db.models import Sum
from django.utils import timezone

from analytics.models import RequestLog, UsageAggregate


class AnalyticsRepository:
    def insert_log(self, client_id: str, resource: str, allowed: bool, remaining: int, degraded: bool) -> None:
        RequestLog.objects.create(
            client_id=client_id,
            resource=resource,
            allowed=allowed,
            remaining=remaining,
            degraded=degraded,
            created_at=timezone.now(),
        )

    def rollup_hour(self, bucket_start: datetime) -> int:
        """
        Aggregates all RequestLog rows in [bucket_start, bucket_start + 1h)
        into UsageAggregate rows, one per (client_id, resource). Uses
        update_or_create so the task is safe to re-run (idempotent rollup)
        if Beat fires it twice or a previous run partially failed.
        Returns number of aggregate rows written.
        """
        bucket_end = bucket_start + timedelta(hours=1)
        raw_logs = RequestLog.objects.filter(created_at__gte=bucket_start, created_at__lt=bucket_end)

        grouped: dict[tuple[str, str], dict[str, int]] = {}
        for log in raw_logs.iterator(chunk_size=2000):
            key = (log.client_id, log.resource)
            stats = grouped.setdefault(key, {"total": 0, "allowed": 0, "rejected": 0, "degraded": 0})
            stats["total"] += 1
            stats["allowed"] += int(log.allowed)
            stats["rejected"] += int(not log.allowed)
            stats["degraded"] += int(log.degraded)

        written = 0
        for (client_id, resource), stats in grouped.items():
            UsageAggregate.objects.update_or_create(
                client_id=client_id,
                resource=resource,
                bucket_start=bucket_start,
                defaults={
                    "total_requests": stats["total"],
                    "allowed_requests": stats["allowed"],
                    "rejected_requests": stats["rejected"],
                    "degraded_requests": stats["degraded"],
                },
            )
            written += 1
        return written

    def get_usage_trend(self, client_id: str, resource: str, hours: int = 24) -> list[UsageAggregate]:
        since = timezone.now() - timedelta(hours=hours)
        return list(
            UsageAggregate.objects.filter(
                client_id=client_id, resource=resource, bucket_start__gte=since
            ).order_by("bucket_start")
        )

    def get_client_summary(self, client_id: str, hours: int = 24) -> dict:
        since = timezone.now() - timedelta(hours=hours)
        qs = UsageAggregate.objects.filter(client_id=client_id, bucket_start__gte=since)
        totals = qs.aggregate(
            total=Sum("total_requests"),
            allowed=Sum("allowed_requests"),
            rejected=Sum("rejected_requests"),
            degraded=Sum("degraded_requests"),
        )
        return {k: (v or 0) for k, v in totals.items()}


analytics_repository = AnalyticsRepository()