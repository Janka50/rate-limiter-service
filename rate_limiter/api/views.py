"""
API layer: thin — validates input, calls the service layer, maps domain
results/exceptions to HTTP status codes. No business logic here.
"""
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from rate_limiter.api.serializers import (
    RateLimitCheckRequestSerializer,
    RateLimitCheckResponseSerializer,
)
from rate_limiter.exceptions import ClientNotFoundError, LimitConfigNotFoundError
from rate_limiter.services.rate_limit_service import rate_limit_service
from analytics.tasks import log_rate_limit_request  # added in Phase 4

logger = logging.getLogger("rate_limiter")


class RateLimitCheckView(APIView):
    """
    POST /api/v1/check/
    Checks whether a request for (client_id, resource) is within its
    configured rate limit, and atomically consumes one unit if allowed.
    """

    @extend_schema(
        request=RateLimitCheckRequestSerializer,
        responses={200: RateLimitCheckResponseSerializer, 404: None, 422: None},
    )
    def post(self, request):
        req_serializer = RateLimitCheckRequestSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)
        client_id = req_serializer.validated_data["client_id"]
        resource = req_serializer.validated_data["resource"]

        try:
            decision = rate_limit_service.check_rate_limit(client_id, resource)
        except ClientNotFoundError:
            return Response({"detail": f"Unknown client '{client_id}'"}, status=status.HTTP_404_NOT_FOUND)
        except LimitConfigNotFoundError:
            return Response(
                {"detail": f"No limit configured for client '{client_id}' on resource '{resource}'"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # Fire-and-forget async log — never blocks this response (Phase 4 wires the task body).
        # Fire-and-forget async log — never blocks this response. Wrapped in
        # try/except because this call itself can raise if the broker
        # (Redis) is unreachable — logging failures must never break the
        # rate-limit decision response.
        try:
            log_rate_limit_request.delay(
                client_id=client_id,
                resource=resource,
                allowed=decision.allowed,
                remaining=decision.remaining,
                degraded=decision.degraded,
            )
        except Exception:
            logger.exception(
                "Failed to enqueue analytics log for client=%s resource=%s — continuing without it",
                client_id, resource,
            )

        response_data = RateLimitCheckResponseSerializer(instance={
            "allowed": decision.allowed,
            "remaining": decision.remaining,
            "limit": decision.limit,
            "retry_after_seconds": decision.retry_after_seconds,
            "degraded": decision.degraded,
        }).data

        http_status = status.HTTP_200_OK if decision.allowed else status.HTTP_429_TOO_MANY_REQUESTS
        return Response(response_data, status=http_status)
