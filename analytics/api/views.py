"""
Dashboard API layer. Reads exclusively from UsageAggregate (never raw
RequestLog) to guarantee fast, bounded-cost responses regardless of how
much history has accumulated.
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter

from analytics.api.serializers import UsageAggregatePointSerializer, ClientSummarySerializer
from analytics.repositories.analytics_repository import analytics_repository


class UsageTrendView(APIView):
    """
    GET /api/v1/analytics/trend/?client_id=...&resource=...&hours=24
    Returns hourly usage buckets for charting.
    """

    @extend_schema(
        parameters=[
            OpenApiParameter("client_id", str, required=True),
            OpenApiParameter("resource", str, required=True),
            OpenApiParameter("hours", int, required=False),
        ],
        responses={200: UsageAggregatePointSerializer(many=True)},
    )
    def get(self, request):
        client_id = request.query_params.get("client_id")
        resource = request.query_params.get("resource")
        hours = int(request.query_params.get("hours", 24))

        if not client_id or not resource:
            return Response(
                {"detail": "client_id and resource are required query parameters"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        aggregates = analytics_repository.get_usage_trend(client_id, resource, hours)
        data = UsageAggregatePointSerializer(aggregates, many=True).data
        return Response(data, status=status.HTTP_200_OK)


class ClientSummaryView(APIView):
    """
    GET /api/v1/analytics/summary/?client_id=...&hours=24
    Returns totals across all resources for a client — the "billing" view.
    """

    @extend_schema(
        parameters=[
            OpenApiParameter("client_id", str, required=True),
            OpenApiParameter("hours", int, required=False),
        ],
        responses={200: ClientSummarySerializer},
    )
    def get(self, request):
        client_id = request.query_params.get("client_id")
        hours = int(request.query_params.get("hours", 24))

        if not client_id:
            return Response({"detail": "client_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        summary = analytics_repository.get_client_summary(client_id, hours)
        data = ClientSummarySerializer(summary).data
        return Response(data, status=status.HTTP_200_OK)