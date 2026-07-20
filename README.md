# Global Rate Limiter Service

A centralized, high-availability rate limiting service for microservices calling external APIs with per-client, per-resource limits.

## Architecture

See `architecture.mmd` (Mermaid) for the full diagram. Summary:

- **Django + DRF** — stateless API layer, horizontally scalable.
- **Redis** — shared source of truth for rate-limit counters, accessed via a single atomic Lua script (Sliding Window Counter algorithm — see "Algorithm Choice" below).
- **PostgreSQL** — durable config (`Client`, `ClientLimitConfig`) and analytics (`RequestLog`, `UsageAggregate`).
- **Celery** — async request logging (never blocks the rate-limit decision) + hourly usage rollups via Celery Beat.
- **Circuit breaker (`pybreaker`)** around Redis calls, with a per-client configurable fail-open/fail-closed policy for outages.

## Algorithm Choice: Sliding Window Counter

Chosen over Fixed Window (boundary burst problem), Sliding Log (memory cost), and Token Bucket (allows bursts that can still trigger real external-API penalties). Full trade-off analysis in `docs/algorithm-decision.md` (or see Phase 1 of the design conversation). Implemented as a strategy behind a `RateLimitStrategy` interface so Token Bucket can be added per-client without touching callers.

## Fail-Safe Strategy

If Redis is unreachable (detected via a circuit breaker after 5 consecutive failures):
- **`FAIL_CLOSED`** clients: requests are rejected until Redis recovers.
- **`FAIL_OPEN`** clients: requests are checked against a local, per-instance, in-memory fallback counter (a degraded approximation, not a blind allow-all) — trades some cross-instance consistency for availability during an outage. Configurable per `Client.fail_policy`.

If Postgres is unreachable: only config lookups and logging are affected (see below), never the Redis-backed rate-limit decision itself.
- Config lookups are cache-first (Redis cache, `CONFIG_CACHE_TTL_SECONDS`), so brief Postgres blips don't affect already-cached clients.
- Logging retries via Celery with exponential backoff; a rate-limit decision is returned to the caller immediately regardless of logging success.

## Running Locally

```bash
cp .env.example .env
docker compose build
docker compose run web python manage.py migrate
docker compose up -d
```

Seed a test client:

```bash
docker compose run web python manage.py shell -c "
from rate_limiter.models import Client, ClientLimitConfig
c = Client.objects.create(client_id='load-test-client', name='Load Test', fail_policy='FAIL_OPEN')
ClientLimitConfig.objects.create(client=c, resource='load-test-resource', limit=100, window_seconds=60)
"
```

## API

### `POST /api/v1/check/`

Request:
```json
{ "client_id": "acme-corp", "resource": "stripe_api" }
```

Response (200 — allowed):
```json
{ "allowed": true, "remaining": 42, "limit": 100, "retry_after_seconds": 0, "degraded": false }
```

Response (429 — rejected):
```json
{ "allowed": false, "remaining": 0, "limit": 100, "retry_after_seconds": 12, "degraded": false }
```

Other codes: `404` unknown client, `422` no limit config for that client+resource, `400` invalid input.

### `GET /api/v1/analytics/trend/?client_id=&resource=&hours=24`
Returns hourly usage buckets for charting.

### `GET /api/v1/analytics/summary/?client_id=&hours=24`
Returns aggregate totals across all resources for a client (billing view).

Full interactive OpenAPI docs: `GET /api/docs/` (Swagger UI via drf-spectacular).

## Testing

```bash
docker compose run web pytest tests/unit tests/integration tests/race_condition
```

Load test (run against a live `docker compose up` stack):
```bash
locust -f tests/load/locustfile.py --host=http://localhost:8000
```

## Known Trade-offs (documented, not hidden)

1. **Local fallback limiter during Redis outages is per-instance**, so effective capacity during an outage is `N instances × limit`, not `limit`. Financially-sensitive clients should use `FAIL_CLOSED`.
2. **`RequestLog` may contain rare duplicate rows** if a Celery worker crashes after commit but before ack. Acceptable for analytics; add an idempotency key if used for exact billing reconciliation.
3. **Hourly rollup uses a Python-side aggregation loop** for correctness/clarity under time constraints; should move to a single SQL conditional aggregation at very high volume (>millions of rows/hour).