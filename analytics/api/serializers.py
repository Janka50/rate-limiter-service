from rest_framework import serializers


class UsageAggregatePointSerializer(serializers.Serializer):
    bucket_start = serializers.DateTimeField()
    total_requests = serializers.IntegerField()
    allowed_requests = serializers.IntegerField()
    rejected_requests = serializers.IntegerField()
    degraded_requests = serializers.IntegerField()


class ClientSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    allowed = serializers.IntegerField()
    rejected = serializers.IntegerField()
    degraded = serializers.IntegerField()