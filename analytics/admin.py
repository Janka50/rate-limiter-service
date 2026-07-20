from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import RequestLog, UsageAggregate


@admin.register(RequestLog)
class RequestLogAdmin(admin.ModelAdmin):
    list_display = ("client_id", "resource", "allowed", "degraded", "created_at")
    list_filter = ("allowed", "degraded")
    search_fields = ("client_id", "resource")
    ordering = ("-created_at",)


@admin.register(UsageAggregate)
class UsageAggregateAdmin(admin.ModelAdmin):
    list_display = ("client_id", "resource", "bucket_start", "total_requests", "rejected_requests")
    ordering = ("-bucket_start",)