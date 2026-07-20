"""
Load test verifying the "few milliseconds" latency requirement holds
under sustained concurrent load. Run with:
    locust -f tests/load/locustfile.py --host=http://localhost:8000
Requires a Client + ClientLimitConfig for 'load-test-client' / 'load-test-resource'
to be seeded beforehand (see README seeding section).
"""
from locust import HttpUser, task, between


class RateLimiterUser(HttpUser):
    wait_time = between(0.01, 0.05)

    @task
    def check_rate_limit(self):
        self.client.post(
            "/api/v1/check/",
            json={"client_id": "load-test-client", "resource": "load-test-resource"},
            name="/api/v1/check/",
        )