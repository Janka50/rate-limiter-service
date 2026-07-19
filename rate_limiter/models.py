"""
Domain models for rate limiter configuration.
Postgres is the durable source of truth for config; the service layer
(Phase 3) caches these in Redis with a short TTL so the hot path never
hits Postgres per-request.
"""
from django.db import models


class Client(models.Model):
    """Represents a consumer of the rate limiter service (an API key / tenant)."""

    client_id = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    fail_policy = models.CharField(
        max_length=20,
        choices=[("FAIL_OPEN", "Fail Open"), ("FAIL_CLOSED", "Fail Closed")],
        default="FAIL_OPEN",
        help_text="Behavior when Redis is unavailable for this client.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rl_client"

    def __str__(self) -> str:
        return f"{self.name} ({self.client_id})"


class ClientLimitConfig(models.Model):
    """
    Per-client, per-resource rate limit definition.
    'resource' identifies the external API/endpoint being protected
    (e.g. "stripe_api", "twilio_sms") so one client can have different
    limits for different upstream APIs.
    """

    STRATEGY_CHOICES = [
        ("SLIDING_WINDOW", "Sliding Window Counter"),
        ("TOKEN_BUCKET", "Token Bucket"),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="limit_configs")
    resource = models.CharField(max_length=150, db_index=True)
    limit = models.PositiveIntegerField(help_text="Max requests allowed per window.")
    window_seconds = models.PositiveIntegerField(help_text="Rolling window size in seconds.")
    strategy = models.CharField(max_length=30, choices=STRATEGY_CHOICES, default="SLIDING_WINDOW")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rl_client_limit_config"
        unique_together = ("client", "resource")
        indexes = [models.Index(fields=["client", "resource"])]

    def __str__(self) -> str:
        return f"{self.client.client_id}:{self.resource} -> {self.limit}/{self.window_seconds}s"