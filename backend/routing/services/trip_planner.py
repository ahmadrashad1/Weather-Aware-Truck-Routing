from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from routing.providers.base import HourlyForecast, Place, ProviderRoute, RoutingProvider
from routing.services.checkpoint_generator import Checkpoint, generate_checkpoints
from routing.services.eta_calculator import eta_at
from routing.services.geometry import LatLon
from routing.services.risk_engine import assess
from routing.services.route_alternatives import get_three_routes
from routing.services.route_scorer import (
    AssessedCheckpoint,
    RouteScore,
    explain_rank,
    rank_routes,
    score_route,
)
from routing.services.route_segments import RouteSegment, build_segments, simplify
from routing.services.weather_lookup import WeatherSource, sample_at


@dataclass(frozen=True)
class TripRequest:
    origin: Place
    destination: Place
    departure_at: datetime
    load_lb: float
    interval_miles: int


@dataclass(frozen=True)
class PlannedRoute:
    id: str
    rank: int
    rationale: str
    total_miles: float
    duration_seconds: int
    arrival_at: datetime
    score: RouteScore
    geometry: tuple[LatLon, ...]
    segments: list[RouteSegment]
    checkpoints: list[AssessedCheckpoint]


@dataclass(frozen=True)
class TripPlan:
    recommended_route_id: str | None
    no_safe_route: bool
    warnings: list[str]
    routes: list[PlannedRoute]


def plan_trip(request: TripRequest, routing: RoutingProvider, weather: WeatherSource) -> TripPlan:
    """Route, place checkpoints, work out each ETA, read the weather at it, then rank."""
    alternatives = get_three_routes(
        routing,
        request.origin.position,
        request.destination.position,
        request.departure_at,
        request.load_lb,
    )
    routes = {f"route-{index}": route for index, route in enumerate(alternatives.routes, start=1)}
    checkpoints = {
        route_id: generate_checkpoints(route.geometry, route.total_miles, request.interval_miles)
        for route_id, route in routes.items()
    }
    forecasts = weather.forecasts(
        [checkpoint.position for group in checkpoints.values() for checkpoint in group]
    )
    assessed = {
        route_id: [
            _assess(checkpoint, routes[route_id], request, forecasts)
            for checkpoint in checkpoints[route_id]
        ]
        for route_id in routes
    }
    scores = {
        route_id: score_route(assessed[route_id], routes[route_id].duration_seconds)
        for route_id in routes
    }
    ranking = rank_routes(scores)

    planned = []
    ordered = ranking.ordered_ids
    for position, route_id in enumerate(ordered):
        route = routes[route_id]
        # The first route is explained against the one below it, and the rest against the one above.
        neighbour = ordered[1:2] if position == 0 else ordered[position - 1 : position]
        planned.append(
            PlannedRoute(
                id=route_id,
                rank=position + 1,
                rationale=explain_rank(
                    scores[route_id],
                    scores[neighbour[0]] if neighbour else None,
                    recommended=route_id == ranking.recommended_id,
                ),
                total_miles=route.total_miles,
                duration_seconds=route.duration_seconds,
                arrival_at=request.departure_at.astimezone(UTC)
                + timedelta(seconds=route.duration_seconds),
                score=scores[route_id],
                geometry=simplify(route.geometry),
                segments=build_segments(route.geometry, route.total_miles, assessed[route_id]),
                checkpoints=assessed[route_id],
            )
        )
    return TripPlan(
        recommended_route_id=ranking.recommended_id,
        no_safe_route=ranking.no_safe_route,
        warnings=[*alternatives.warnings, *_missing_weather_warnings(planned)],
        routes=planned,
    )


def _assess(
    checkpoint: Checkpoint,
    route: ProviderRoute,
    request: TripRequest,
    forecasts: Mapping[LatLon, HourlyForecast | None],
) -> AssessedCheckpoint:
    eta = eta_at(checkpoint.mile, request.departure_at, route.profile)
    forecast = forecasts[checkpoint.position]
    sample = sample_at(forecast, eta) if forecast else None
    return AssessedCheckpoint(
        checkpoint=checkpoint,
        eta=eta,
        sample=sample,
        assessment=assess(sample, request.load_lb) if sample else None,
    )


def _missing_weather_warnings(routes: Sequence[PlannedRoute]) -> list[str]:
    return [
        f"Weather is unavailable for {route.score.unknown_miles:.0f} of "
        f"{route.total_miles:.0f} miles on route {route.rank}. It ranks after routes with complete "
        "weather, so the ranking may reflect missing data rather than conditions."
        for route in routes
        if route.score.unknown_miles > 0
    ]
