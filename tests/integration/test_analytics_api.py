import pytest
from django.utils import timezone
from rest_framework import status

from analytics.models import UsageAggregate


@pytest.mark.django_db
def test_trend_endpoint_returns_aggregate_data(api_client):
    UsageAggregate.objects.create(
        client_id="c1", resource="r1", bucket_start=timezone.now(),
        total_requests=10, allowed_requests=8, rejected_requests=2, degraded_requests=0,
    )
    resp = api_client.get("/api/v1/analytics/trend/", {"client_id": "c1", "resource": "r1"})
    assert resp.status_code == status.HTTP_200_OK
    assert len(resp.data) == 1
    assert resp.data[0]["total_requests"] == 10


@pytest.mark.django_db
def test_trend_endpoint_requires_params(api_client):
    resp = api_client.get("/api/v1/analytics/trend/", {"client_id": "c1"})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_summary_endpoint_aggregates_across_resources(api_client):
    now = timezone.now()
    UsageAggregate.objects.create(client_id="c1", resource="r1", bucket_start=now, total_requests=10, allowed_requests=9, rejected_requests=1, degraded_requests=0)
    UsageAggregate.objects.create(client_id="c1", resource="r2", bucket_start=now, total_requests=5, allowed_requests=5, rejected_requests=0, degraded_requests=0)

    resp = api_client.get("/api/v1/analytics/summary/", {"client_id": "c1"})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["total"] == 15
    assert resp.data["allowed"] == 14