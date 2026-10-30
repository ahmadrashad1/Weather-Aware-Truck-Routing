from functools import lru_cache

from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from routing.api.serializers import (
    ErrorSerializer,
    GeocodeQuerySerializer,
    GeocodeResponseSerializer,
    HeatmapRequestSerializer,
    HeatmapResponseSerializer,
    PlanRequestSerializer,
    PlanResponseSerializer,
    heatmap_to_response,
    plan_to_response,
)
from routing.providers.base import GeocodingProvider, Place, RoutingProvider
from routing.providers.open_meteo import OpenMeteoProvider
from routing.providers.tomtom import TomTomProvider
from routing.services.corridor_grid import corridor_points
from routing.services.heatmap import build_heatmap
from routing.services.trip_planner import TripRequest, plan_trip
from routing.services.weather_lookup import WeatherLookup


@lru_cache(maxsize=1)
def _tomtom() -> TomTomProvider:
    return TomTomProvider(settings.TOMTOM_API_KEY)


def get_routing_provider() -> RoutingProvider:
    return _tomtom()


def get_geocoding_provider() -> GeocodingProvider:
    return _tomtom()


@lru_cache(maxsize=1)
def get_weather_lookup() -> WeatherLookup:
    return WeatherLookup(OpenMeteoProvider(settings.OPEN_METEO_API_KEY))


class PlanTripView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "trip_plan"

    @extend_schema(
        request=PlanRequestSerializer,
        responses={
            200: PlanResponseSerializer,
            400: ErrorSerializer,
            422: ErrorSerializer,
            429: ErrorSerializer,
            503: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plan = plan_trip(
            TripRequest(
                origin=_place(data["origin"]),
                destination=_place(data["destination"]),
                departure_at=data["departure_at"],
                load_lb=data["load_lb"],
                interval_miles=data["interval_miles"],
            ),
            get_routing_provider(),
            get_weather_lookup(),
        )
        return Response(PlanResponseSerializer(plan_to_response(plan)).data)


class HeatmapView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "heatmap"

    @extend_schema(
        request=HeatmapRequestSerializer,
        responses={
            200: HeatmapResponseSerializer,
            400: ErrorSerializer,
            429: ErrorSerializer,
            503: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = HeatmapRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        heatmap = build_heatmap(
            corridor_points(data["routes"]),
            data["departure_at"],
            data["load_lb"],
            get_weather_lookup(),
        )
        return Response(HeatmapResponseSerializer(heatmap_to_response(heatmap)).data)


class GeocodeView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "geocode"

    @extend_schema(
        parameters=[OpenApiParameter("q", str, required=True, description="Search text")],
        responses={
            200: GeocodeResponseSerializer,
            400: ErrorSerializer,
            429: ErrorSerializer,
            503: ErrorSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        serializer = GeocodeQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        places = get_geocoding_provider().search(serializer.validated_data["q"])
        results = [
            {"label": place.label, "lat": place.position[0], "lon": place.position[1]}
            for place in places
        ]
        return Response(GeocodeResponseSerializer({"results": results}).data)


def _place(location: dict[str, object]) -> Place:
    lat = location["lat"]
    lon = location["lon"]
    assert isinstance(lat, float) and isinstance(lon, float)
    return Place(label=str(location["label"]), position=(lat, lon))
