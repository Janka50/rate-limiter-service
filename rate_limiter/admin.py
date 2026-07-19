from django.contrib import admin
from .models import Client, ClientLimitConfig


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("client_id", "name", "is_active", "fail_policy")
    search_fields = ("client_id", "name")


@admin.register(ClientLimitConfig)
class ClientLimitConfigAdmin(admin.ModelAdmin):
    list_display = ("client", "resource", "limit", "window_seconds", "strategy")
    list_filter = ("strategy",)