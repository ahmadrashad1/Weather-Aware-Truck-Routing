from django.urls import path

from routing.api.views import (
    AttributionView,
    GeocodeView,
    HeatmapView,
    PlanTripView,
    VitalsView,
)

urlpatterns = [
    path("geocode", GeocodeView.as_view()),
    path("trips/plan", PlanTripView.as_view()),
    path("trips/heatmap", HeatmapView.as_view()),
    path("vitals", VitalsView.as_view()),
    path("attribution", AttributionView.as_view()),
]
