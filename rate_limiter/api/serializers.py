from rest_framework import serializers


class RateLimitCheckRequestSerializer(serializers.Serializer):
    client_id = serializers.CharField(max_length=100)
    resource = serializers.CharField(max_length=150)


class RateLimitCheckResponseSerializer(serializers.Serializer):
    allowed = serializers.BooleanField()
    remaining = serializers.IntegerField()
    limit = serializers.IntegerField()
    retry_after_seconds = serializers.IntegerField()
    degraded = serializers.BooleanField()