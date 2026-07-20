"""
Integration tests: real Django test client, real Redis, real Postgres
(via pytest-django's transactional DB). Verifies HTTP-level behavior end
to end, including status codes.
"""
import pytest
from rest_framework import status


@pytest.mark.django_db
def test_check_endpoint_allows_and_returns_200(api_client, test_client_config):
    resp = api_client.post("/api/v1/check/", {"client_id": "test-client", "resource": "test-resource"})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["allowed"] is True
    assert resp.data["remaining"] == 4


@pytest.mark.django_db
def test_check_endpoint_returns_429_when_exhausted(api_client, test_client_config):
    for _ in range(5):
        api_client.post("/api/v1/check/", {"client_id": "test-client", "resource": "test-resource"})
    resp = api_client.post("/api/v1/check/", {"client_id": "test-client", "resource": "test-resource"})
    assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert resp.data["allowed"] is False


@pytest.mark.django_db
def test_check_endpoint_returns_404_for_unknown_client(api_client):
    resp = api_client.post("/api/v1/check/", {"client_id": "ghost", "resource": "r1"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_check_endpoint_returns_422_for_unconfigured_resource(api_client, test_client_config):
    resp = api_client.post("/api/v1/check/", {"client_id": "test-client", "resource": "unconfigured"})
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.django_db
def test_check_endpoint_validates_input(api_client):
    resp = api_client.post("/api/v1/check/", {"client_id": ""})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST