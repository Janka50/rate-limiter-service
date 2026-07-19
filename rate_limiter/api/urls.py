from django.urls import path
from rate_limiter.api.views import RateLimitCheckView

urlpatterns = [
    path("check/", RateLimitCheckView.as_view(), name="rate-limit-check"),
]