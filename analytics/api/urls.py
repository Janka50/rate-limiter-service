from django.urls import path
from analytics.api.views import UsageTrendView, ClientSummaryView

urlpatterns = [
    path("trend/", UsageTrendView.as_view(), name="analytics-trend"),
    path("summary/", ClientSummaryView.as_view(), name="analytics-summary"),
]