from django.db import models
"""
Analytics models. Placeholder now — full RequestLog + aggregate models
built in Phase 4 alongside the Celery logging task, so the schema is
designed together with its write path.
"""
# Create your models here.
"""
Analytics models. RequestLog is the append-only fact table (billing/audit
source of truth). UsageAggregate is a periodic rollup used to serve fast
dashboard queries without scanning RequestLog.
"""
from django.db import models


class RequestLog(models.Model):
    """One row per rate-limit check. Never updated after insert."""

    client_id = models.CharField(max_length=100, db_index=True)
    resource = models.CharField(max_length=150, db_index=True)
    allowed = models.BooleanField()
    remaining = models.IntegerField()
    degraded = models.BooleanField(
        default=False,
        help_text="True if this decision was made via fail-safe fallback, not Redis.",
    )
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "al_request_log"
        indexes = [
            models.Index(fields=["client_id", "resource", "created_at"]),
        ]
        # Append-only: no custom save()/delete() overrides needed, but we
        # intentionally do not expose an update path anywhere in the app.

    def __str__(self) -> str:
        return f"{self.client_id}/{self.resource} @ {self.created_at} allowed={self.allowed}"


class UsageAggregate(models.Model):
    """
    Pre-computed per-client, per-resource, per-hour rollup.
    Populated by a periodic Celery Beat task (analytics.tasks.rollup_usage_aggregates).
    Dashboard reads come from here, never from RequestLog directly.
    """

    client_id = models.CharField(max_length=100, db_index=True)
    resource = models.CharField(max_length=150, db_index=True)
    bucket_start = models.DateTimeField(help_text="Start of the hourly bucket (UTC).")
    total_requests = models.PositiveIntegerField(default=0)
    allowed_requests = models.PositiveIntegerField(default=0)
    rejected_requests = models.PositiveIntegerField(default=0)
    degraded_requests = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "al_usage_aggregate"
        unique_together = ("client_id", "resource", "bucket_start")
        indexes = [models.Index(fields=["client_id", "resource", "bucket_start"])]

    def __str__(self) -> str:
        return f"{self.client_id}/{self.resource} @ {self.bucket_start}: {self.total_requests} reqs"