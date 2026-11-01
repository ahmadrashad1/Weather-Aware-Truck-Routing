import math
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from routing.domain import RiskLevel
from routing.services.geometry import LatLon, haversine_miles
from routing.services.heatmap import HEATMAP_FRAMES, Heatmap
from routing.services.route_scorer import AssessedCheckpoint
from routing.services.trip_planner import PlannedRoute, TripPlan

INTERVALS_MILES = [10, 25, 50]
MAX_LOAD_LB = 80_000
DEPARTURE_GRACE = timedelta(minutes=15)
# The forecast covers 16 days, and this leaves room for the trip and the 48-hour heatmap.
DEPARTURE_HORIZON = timedelta(days=14)
MIN_TRIP_MILES = 0.1
MAX_HEATMAP_ROUTES = 3
MAX_ROUTE_POINTS = 20_000
MAX_VITAL_VALUE = 600_000

RISK_CODES = ["low", "moderate", "high", "severe", "no_travel"]
RISK_OR_UNKNOWN_CODES = [*RISK_CODES, "unknown"]
COORDINATE_DECIMALS = 5
MILES_DECIMALS = 2
AVERAGE_RISK_DECIMALS = 3


class FiniteFloatField(serializers.FloatField):
    """Reject NaN and infinity, which a plain float field accepts as the strings "nan" and "inf"."""

    def to_internal_value(self, data: Any) -> float:
        value = super().to_internal_value(data)
        if not math.isfinite(value):
            self.fail("invalid")
        return float(value)


class OffsetDateTimeField(serializers.DateTimeField):
    """Require a UTC offset, rather than guessing which time zone the driver meant."""

    default_error_messages = {
        "naive": "Include a UTC offset, for example 2026-11-01T12:00:00-05:00."
    }

    def enforce_timezone(self, value: datetime) -> datetime:
        if timezone.is_naive(value):
            self.fail("naive")
        return value


class LocationSerializer(serializers.Serializer[Any]):
    label = serializers.CharField(max_length=200)  # type: ignore[assignment]
    lat = FiniteFloatField(min_value=-90, max_value=90)
    lon = FiniteFloatField(min_value=-180, max_value=180)


def validate_departure_window(value: datetime) -> None:
    now = timezone.now()
    if value < now - DEPARTURE_GRACE:
        raise serializers.ValidationError("Departure cannot be in the past.")
    if value > now + DEPARTURE_HORIZON:
        raise serializers.ValidationError("Departure must be within the next 14 days.")


class PlanRequestSerializer(serializers.Serializer[Any]):
    origin = LocationSerializer()
    destination = LocationSerializer()
    departure_at = OffsetDateTimeField(validators=[validate_departure_window])
    load_lb = FiniteFloatField(min_value=0, max_value=MAX_LOAD_LB)
    interval_miles = serializers.ChoiceField(choices=INTERVALS_MILES)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        origin = (attrs["origin"]["lat"], attrs["origin"]["lon"])
        destination = (attrs["destination"]["lat"], attrs["destination"]["lon"])
        if haversine_miles(origin, destination) < MIN_TRIP_MILES:
            raise serializers.ValidationError(
                {"destination": ["Destination must be different from the origin."]}
            )
        return attrs


@extend_schema_field(
    {
        "type": "array",
        "description": "A route line as [longitude, latitude] pairs, as GeoJSON orders them.",
        "items": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        "minItems": 2,
        "maxItems": MAX_ROUTE_POINTS,
    }
)
class RouteLineField(serializers.Field[list[LatLon], list[list[float]], Any, Any]):
    """Accept a GeoJSON-ordered line and turn it into (latitude, longitude) points."""

    default_error_messages = {
        "invalid": f"Send 2 to {MAX_ROUTE_POINTS} [longitude, latitude] pairs in range.",
    }

    def to_internal_value(self, data: Any) -> list[LatLon]:
        if not isinstance(data, list) or not 2 <= len(data) <= MAX_ROUTE_POINTS:
            self.fail("invalid")
        return [self._point(item) for item in data]

    def _point(self, item: Any) -> LatLon:
        if not isinstance(item, list) or len(item) != 2:
            self.fail("invalid")
        lon, lat = item
        for value in (lon, lat):
            # A bool counts as an int in Python, and a string such as "nan" must not pass.
            if isinstance(value, bool) or not isinstance(value, int | float):
                self.fail("invalid")
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            self.fail("invalid")
        return (float(lat), float(lon))

    def to_representation(self, value: list[LatLon]) -> list[list[float]]:
        return [[lon, lat] for lat, lon in value]


class HeatmapRequestSerializer(serializers.Serializer[Any]):
    routes = serializers.ListField(
        child=RouteLineField(), min_length=1, max_length=MAX_HEATMAP_ROUTES
    )
    departure_at = OffsetDateTimeField(validators=[validate_departure_window])
    load_lb = FiniteFloatField(min_value=0, max_value=MAX_LOAD_LB)


class GeocodeQuerySerializer(serializers.Serializer[Any]):
    q = serializers.CharField(max_length=200)


class AttributionResponseSerializer(serializers.Serializer[Any]):
    routing_caption = serializers.CharField()


class VitalSerializer(serializers.Serializer[Any]):
    name = serializers.ChoiceField(choices=["CLS", "FCP", "INP", "LCP", "TTFB"])
    value = FiniteFloatField(min_value=0, max_value=MAX_VITAL_VALUE)
    rating = serializers.ChoiceField(choices=["good", "needs-improvement", "poor"])


class ErrorSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    message = serializers.CharField()
    fields = serializers.DictField(required=False)  # type: ignore[assignment]


class GeocodeResponseSerializer(serializers.Serializer[Any]):
    results = LocationSerializer(many=True)


@extend_schema_field(
    {
        "type": "array",
        "description": "[longitude, latitude] pairs, as GeoJSON orders them.",
        "items": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
    }
)
class CoordinatesField(serializers.JSONField):
    """Pass prepared coordinates through, as a nested field per point is slow on long routes."""


class WeatherSerializer(serializers.Serializer[Any]):
    wind_mph = serializers.FloatField()
    rain_in_hr = serializers.FloatField()
    snow_in_hr = serializers.FloatField()


class CheckpointSerializer(serializers.Serializer[Any]):
    id = serializers.CharField()
    mile = serializers.FloatField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    eta = serializers.DateTimeField()
    represented_miles = serializers.FloatField()
    weather = WeatherSerializer(allow_null=True)
    risk = serializers.ChoiceField(choices=RISK_OR_UNKNOWN_CODES)
    wind_risk = serializers.ChoiceField(choices=RISK_CODES, allow_null=True)
    rain_risk = serializers.ChoiceField(choices=RISK_CODES, allow_null=True)
    snow_risk = serializers.ChoiceField(choices=RISK_CODES, allow_null=True)
    load_adjusted = serializers.BooleanField()
    drivers = serializers.ListField(child=serializers.CharField())


class SegmentSerializer(serializers.Serializer[Any]):
    risk = serializers.ChoiceField(choices=RISK_OR_UNKNOWN_CODES)
    from_mile = serializers.FloatField()
    to_mile = serializers.FloatField()
    coordinates = CoordinatesField()


class LineStringSerializer(serializers.Serializer[Any]):
    type = serializers.ChoiceField(choices=["LineString"])
    coordinates = CoordinatesField()


class RouteSummarySerializer(serializers.Serializer[Any]):
    distance_miles = serializers.FloatField()
    duration_seconds = serializers.IntegerField()
    arrival_at = serializers.DateTimeField()
    severe_miles = serializers.FloatField()
    high_miles = serializers.FloatField()
    moderate_miles = serializers.FloatField()
    low_miles = serializers.FloatField()
    no_travel_miles = serializers.FloatField()
    unknown_miles = serializers.FloatField()
    average_risk = serializers.FloatField(allow_null=True)


class RouteSerializer(serializers.Serializer[Any]):
    id = serializers.CharField()
    rank = serializers.IntegerField()
    rationale = serializers.CharField()
    summary = RouteSummarySerializer()
    geometry = LineStringSerializer()
    segments = SegmentSerializer(many=True)
    checkpoints = CheckpointSerializer(many=True)


@extend_schema_field(
    {
        "type": "array",
        "description": (
            "One list per point, holding the risk level at each hour from departure: "
            "0 Low, 1 Moderate, 2 High, 3 Severe, 4 No Travel, "
            "or null where weather is unavailable."
        ),
        "items": {"type": "array", "items": {"type": "integer", "nullable": True}},
    }
)
class RiskFramesField(serializers.JSONField):
    """Pass prepared frames through, as a nested field per value is slow at 300 x 49."""


class HeatmapResponseSerializer(serializers.Serializer[Any]):
    departure_at = serializers.DateTimeField()
    hours = serializers.IntegerField()
    points = CoordinatesField()
    risk = RiskFramesField()


class PlanResponseSerializer(serializers.Serializer[Any]):
    recommended_route_id = serializers.CharField(allow_null=True)
    no_safe_route = serializers.BooleanField()
    warnings = serializers.ListField(child=serializers.CharField())
    routes = RouteSerializer(many=True)


def heatmap_to_response(heatmap: Heatmap) -> dict[str, Any]:
    return {
        "departure_at": heatmap.departure_at,
        "hours": HEATMAP_FRAMES,
        "points": _coordinates(heatmap.points),
        "risk": [list(frames) for frames in heatmap.risk],
    }


def plan_to_response(plan: TripPlan) -> dict[str, Any]:
    return {
        "recommended_route_id": plan.recommended_route_id,
        "no_safe_route": plan.no_safe_route,
        "warnings": plan.warnings,
        "routes": [_route_to_response(route) for route in plan.routes],
    }


def _route_to_response(route: PlannedRoute) -> dict[str, Any]:
    score = route.score
    return {
        "id": route.id,
        "rank": route.rank,
        "rationale": route.rationale,
        "summary": {
            "distance_miles": _miles(route.total_miles),
            "duration_seconds": route.duration_seconds,
            "arrival_at": route.arrival_at,
            "severe_miles": _miles(score.severe_miles),
            "high_miles": _miles(score.high_miles),
            "moderate_miles": _miles(score.moderate_miles),
            "low_miles": _miles(score.low_miles),
            "no_travel_miles": _miles(score.no_travel_miles),
            "unknown_miles": _miles(score.unknown_miles),
            "average_risk": (
                None
                if score.average_risk is None
                else round(score.average_risk, AVERAGE_RISK_DECIMALS)
            ),
        },
        "geometry": {"type": "LineString", "coordinates": _coordinates(route.geometry)},
        "segments": [
            {
                "risk": _risk_code(segment.risk),
                "from_mile": _miles(segment.from_mile),
                "to_mile": _miles(segment.to_mile),
                "coordinates": _coordinates(segment.coordinates),
            }
            for segment in route.segments
        ],
        "checkpoints": [
            _checkpoint_to_response(f"{route.id}-{index}", checkpoint)
            for index, checkpoint in enumerate(route.checkpoints)
        ],
    }


def _checkpoint_to_response(checkpoint_id: str, item: AssessedCheckpoint) -> dict[str, Any]:
    lat, lon = item.checkpoint.position
    assessment = item.assessment
    return {
        "id": checkpoint_id,
        "mile": _miles(item.checkpoint.mile),
        "lat": round(lat, COORDINATE_DECIMALS),
        "lon": round(lon, COORDINATE_DECIMALS),
        "eta": item.eta,
        "represented_miles": _miles(item.checkpoint.represented_miles),
        "weather": (
            None
            if item.sample is None
            else {
                "wind_mph": round(item.sample.wind_mph, 1),
                "rain_in_hr": round(item.sample.rain_in_hr, 3),
                "snow_in_hr": round(item.sample.snow_in_hr, 3),
            }
        ),
        "risk": _risk_code(assessment.level if assessment else None),
        "wind_risk": _risk_code(assessment.wind) if assessment else None,
        "rain_risk": _risk_code(assessment.rain) if assessment else None,
        "snow_risk": _risk_code(assessment.snow) if assessment else None,
        "load_adjusted": assessment.load_adjusted if assessment else False,
        "drivers": list(assessment.drivers) if assessment else [],
    }


def _risk_code(level: RiskLevel | None) -> str:
    return "unknown" if level is None else level.name.lower()


def _miles(value: float) -> float:
    return round(value, MILES_DECIMALS)


def _coordinates(points: tuple[LatLon, ...]) -> list[list[float]]:
    return [
        [round(lon, COORDINATE_DECIMALS), round(lat, COORDINATE_DECIMALS)] for lat, lon in points
    ]
