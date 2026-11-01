from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from routing.domain import RiskLevel
from routing.providers.base import HourlyForecast, Place, ProviderRoute
from routing.providers.errors import NoRouteFound, ProviderUnavailable
from routing.services.eta_calculator import TravelProfile
from routing.services.geometry import LatLon, haversine_miles
from routing.services.route_segments import simplify_indices
from routing.services.trip_planner import TripPlan, TripRequest, plan_trip
from routing.services.weather_lookup import WeatherLookup
from tests.fakes import FakeRouting, FakeWeather, straight_route

START = datetime(2026, 11, 1, 12, tzinfo=UTC)
ORIGIN = Place("Origin", (30.0, -100.0))
DESTINATION = Place("Destination", (31.5, -100.0))
WEST = -101.0
EAST = -99.0


def request(interval: int = 50, load: float = 1000) -> TripRequest:
    return TripRequest(
        origin=ORIGIN,
        destination=DESTINATION,
        departure_at=START,
        load_lb=load,
        interval_miles=interval,
    )


def three_routes() -> list[ProviderRoute]:
    return [
        straight_route(100, 7200, lon=-100.0),
        straight_route(120, 9000, lon=WEST),
        straight_route(140, 10800, lon=EAST),
    ]


def plan(
    weather: FakeWeather, routes: list[ProviderRoute] | None = None, **kwargs: object
) -> TripPlan:
    routing = FakeRouting(routes if routes is not None else three_routes())
    return plan_trip(request(**kwargs), routing, WeatherLookup(weather))  # type: ignore[arg-type]


def test_each_checkpoint_gets_weather_at_its_own_eta() -> None:
    # Only the hour one hour after departure is windy. Mile 50 of the 2-hour route arrives then.
    def wind(cell: LatLon, at: datetime) -> float:
        return 50.0 if at == START + timedelta(hours=1) else 5.0

    route = plan(FakeWeather(START, wind), [straight_route(100, 7200)]).routes[0]
    levels = [checkpoint.assessment.level for checkpoint in route.checkpoints]  # type: ignore[union-attr]
    assert levels == [RiskLevel.LOW, RiskLevel.SEVERE, RiskLevel.LOW]
    assert [checkpoint.eta for checkpoint in route.checkpoints] == [
        START,
        START + timedelta(hours=1),
        START + timedelta(hours=2),
    ]


def test_load_weight_reaches_the_risk_rules() -> None:
    weather = FakeWeather(START, lambda cell, at: 35.0)
    light = plan(weather, [straight_route(100, 7200)], load=40_000).routes[0]
    heavy = plan(weather, [straight_route(100, 7200)], load=40_001).routes[0]
    assert light.score.high_miles == 100
    assert heavy.score.severe_miles == 100


def test_route_planning_receives_the_departure_and_load() -> None:
    routing = FakeRouting(three_routes())
    plan_trip(request(load=45_000), routing, WeatherLookup(FakeWeather(START)))
    assert routing.calls[0]["departure"] == START
    assert routing.calls[0]["load_lb"] == 45_000


def test_recommendation_matches_ranking() -> None:
    # The fastest route is the stormy one, so it must lose to a slower, safer route.
    result = plan(FakeWeather(START, lambda cell, at: 50.0 if cell[1] == -100.0 else 5.0))
    assert [route.rank for route in result.routes] == [1, 2, 3]
    assert result.routes[0].duration_seconds == 9000
    assert result.routes[-1].duration_seconds == 7200
    assert result.recommended_route_id == result.routes[0].id
    assert not result.no_safe_route


def test_route_ids_are_unique() -> None:
    assert len({route.id for route in plan(FakeWeather(START)).routes}) == 3


def test_all_no_travel_returns_no_recommendation_with_every_route() -> None:
    result = plan(FakeWeather(START, lambda cell, at: 60.0))
    assert result.recommended_route_id is None
    assert result.no_safe_route
    assert len(result.routes) == 3


def test_rationale_names_the_deciding_criterion() -> None:
    result = plan(FakeWeather(START, lambda cell, at: 50.0 if cell[1] == -100.0 else 5.0))
    assert (
        "Severe miles" in result.routes[0].rationale or "travel time" in result.routes[0].rationale
    )
    assert "Severe miles" in result.routes[-1].rationale


def test_rationale_explains_a_no_travel_route() -> None:
    result = plan(FakeWeather(START, lambda cell, at: 60.0))
    assert "No Travel" in result.routes[0].rationale


def test_arrival_is_departure_plus_duration() -> None:
    route = plan(FakeWeather(START), [straight_route(100, 7200)]).routes[0]
    assert route.arrival_at == START + timedelta(hours=2)


def test_segments_cover_route_and_match_checkpoint_risk() -> None:
    def wind(cell: LatLon, at: datetime) -> float:
        return 50.0 if at == START + timedelta(hours=1) else 5.0

    route = plan(FakeWeather(START, wind), [straight_route(100, 7200)]).routes[0]
    assert [(s.risk, s.from_mile, s.to_mile) for s in route.segments] == [
        (RiskLevel.LOW, 0.0, 25.0),
        (RiskLevel.SEVERE, 25.0, 75.0),
        (RiskLevel.LOW, 75.0, 100.0),
    ]
    for first, second in zip(route.segments, route.segments[1:], strict=False):
        assert first.coordinates[-1] == second.coordinates[0]
    assert route.segments[0].coordinates[0] == route.geometry[0]
    assert route.segments[-1].coordinates[-1] == route.geometry[-1]


def test_adjacent_checkpoints_of_equal_risk_merge_into_one_segment() -> None:
    route = plan(FakeWeather(START), [straight_route(100, 7200)], interval=10).routes[0]
    assert [(s.risk, s.from_mile, s.to_mile) for s in route.segments] == [
        (RiskLevel.LOW, 0.0, 100.0)
    ]


def test_segment_boundary_lies_on_the_route() -> None:
    def wind(cell: LatLon, at: datetime) -> float:
        return 50.0 if at == START + timedelta(hours=1) else 5.0

    route = plan(FakeWeather(START, wind), [straight_route(100, 7200)]).routes[0]
    boundary = route.segments[0].coordinates[-1]
    assert haversine_miles(route.geometry[0], boundary) == pytest.approx(25, abs=0.1)


def test_coast_to_coast_at_10_miles_batches_requests() -> None:
    weather = FakeWeather(START)
    routes = [
        straight_route(2850, 165_000, lon=-100.0),
        straight_route(2900, 167_000, lon=WEST),
        straight_route(3000, 172_000, lon=EAST),
    ]
    result = plan(weather, routes, interval=10)
    assert all(len(batch) <= 100 for batch in weather.requests)
    assert sum(len(route.checkpoints) for route in result.routes) > 850
    assert all(route.score.unknown_miles == 0 for route in result.routes)


def test_partial_weather_outage_warns_and_ranks_complete_routes_first() -> None:
    # Batches are one route's worth here, so the second route's cells all fail.
    weather = FakeWeather(START, failures=[])
    routes = three_routes()
    lookup = WeatherLookup(weather)
    original = weather.hourly

    def fail_for_west(cells: list[LatLon], forecast_days: int = 16) -> dict:  # type: ignore[type-arg]
        forecasts = original(cells)
        return {cell: forecast for cell, forecast in forecasts.items() if cell[1] != WEST}

    weather.hourly = fail_for_west  # type: ignore[method-assign,assignment]
    result = plan_trip(request(), FakeRouting(routes), lookup)
    assert result.routes[-1].total_miles == 120
    assert result.routes[-1].score.unknown_miles == 120
    assert result.recommended_route_id != result.routes[-1].id
    assert any("120" in warning for warning in result.warnings)


def test_eta_past_the_forecast_is_unknown_and_warned() -> None:
    # The forecast covers 2 hours of a 4-hour route.
    result = plan(FakeWeather(START, hours=3), [straight_route(100, 14400)])
    route = result.routes[0]
    assert route.score.unknown_miles > 0
    assert route.score.low_miles > 0
    assert result.warnings


def test_fewer_routes_warning_is_passed_on() -> None:
    result = plan(FakeWeather(START), [straight_route(100, 7200)])
    assert len(result.routes) == 1
    assert any("1 distinct" in warning for warning in result.warnings)


def test_total_weather_outage_raises() -> None:
    weather = FakeWeather(START, error=ProviderUnavailable("down"))
    with pytest.raises(ProviderUnavailable):
        plan(weather)


def test_no_route_raises() -> None:
    routing = FakeRouting(error=NoRouteFound("none"))
    with pytest.raises(NoRouteFound):
        plan_trip(request(), routing, WeatherLookup(FakeWeather(START)))


def test_geometry_is_simplified_for_display_but_checkpoints_use_the_full_route() -> None:
    # A straight run of 5,000 points with one sharp bend: north, then east.
    north = [(30.0 + i * 0.0002, -100.0) for i in range(2500)]
    bend = north[-1]
    east = [(bend[0], -100.0 + i * 0.0002) for i in range(1, 2500)]
    geometry = tuple(north + east)
    route = ProviderRoute(
        geometry=geometry,
        total_miles=60.0,
        duration_seconds=3600,
        profile=TravelProfile(((0, 0), (60.0, 3600))),
    )
    planned = plan(FakeWeather(START), [route], interval=10).routes[0]
    assert len(planned.geometry) < 10
    assert planned.geometry[0] == geometry[0]
    assert planned.geometry[-1] == geometry[-1]
    assert bend in planned.geometry
    # Mile 30 is at the bend. A checkpoint computed from the simplified line would match anyway,
    # so check one on the second leg sits on the eastbound line.
    assert planned.checkpoints[-2].checkpoint.position[0] == pytest.approx(bend[0], abs=0.001)


def test_simplify_keeps_detail_above_the_tolerance() -> None:
    zigzag: list[LatLon] = [(30.0 + i * 0.01, -100.0 + (i % 2) * 0.01) for i in range(10)]
    assert simplify_indices(zigzag, 0.0005) == list(range(10))


def test_simplify_drops_points_within_the_tolerance() -> None:
    wobble: list[LatLon] = [(30.0 + i * 0.01, -100.0 + (i % 2) * 0.0001) for i in range(10)]
    assert simplify_indices(wobble, 0.0005) == [0, 9]


def test_the_forecast_requested_covers_the_slowest_route() -> None:
    class Recording:
        needed: datetime | None = None

        def forecasts(
            self, positions: Sequence[LatLon], needed_until: datetime | None = None
        ) -> dict[LatLon, HourlyForecast | None]:
            Recording.needed = needed_until
            return dict.fromkeys(positions)

    departure = datetime(2026, 11, 2, 12, tzinfo=UTC)
    routing = FakeRouting(
        [straight_route(100, 7200, lon=-100.0), straight_route(300, 36_000, lon=-90.0)]
    )
    request = TripRequest(
        Place("a", (30.0, -100.0)), Place("b", (31.0, -100.0)), departure, 1000, 50
    )
    plan_trip(request, routing, Recording())
    assert Recording.needed == departure + timedelta(seconds=36_000)
