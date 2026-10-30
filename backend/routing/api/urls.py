from django.urls import path

from routing.api.views import GeocodeView, PlanTripView

urlpatterns = [
    path("geocode", GeocodeView.as_view()),
    path("trips/plan", PlanTripView.as_view()),
]
