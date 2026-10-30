import pytest

from routing.services.corridor_grid import corridor_points
from routing.services.geometry import LatLon, haversine_miles, sample_along

MILES_PER_DEGREE_LATITUDE = 69.09


def north(miles: float, lon: float = -100.0) -> list[LatLon]:
    return [(30.0, lon), (30.0 + miles / MILES_PER_DEGREE_LATITUDE, lon)]


def bent(miles: float) -> list[LatLon]:
    half = miles / 2 / MILES_PER_DEGREE_LATITUDE
    return [(30.0, -100.0), (30.0 + half, -100.0), (30.0 + half, -100.0 + half * 1.15)]


def miles_to_route(point: LatLon, route: list[LatLon]) -> float:
    return min(haversine_miles(point, sample) for sample in sample_along(route, 1.0))


@pytest.mark.parametrize("miles", [20, 100, 800, 3000])
def test_points_stay_within_corridor(miles: float) -> None:
    route = bent(miles)
    points = corridor_points([route], half_width_miles=25)
    assert points
    # One mile of allowance for measuring against route samples a mile apart.
    assert all(miles_to_route(point, route) <= 26 for point in points)


def test_point_count_never_exceeds_cap_on_long_routes() -> None:
    routes = [north(3000, -100.0), north(3100, -101.0), north(3200, -99.0)]
    assert len(corridor_points(routes, max_points=300)) <= 300


@pytest.mark.parametrize("cap", [10, 50, 300])
def test_cap_is_respected(cap: int) -> None:
    assert len(corridor_points([north(800)], max_points=cap)) <= cap


def test_short_route_still_gets_a_usable_grid() -> None:
    assert len(corridor_points([north(20)])) >= 9


def test_medium_route_has_width_across_the_corridor() -> None:
    points = corridor_points([north(300)], half_width_miles=25)
    longitudes = [point[1] for point in points]
    assert min(longitudes) < -100.3
    assert max(longitudes) > -99.7
    assert -100.0 in longitudes


@pytest.mark.parametrize("miles", [100, 800, 3000])
def test_no_stretch_of_route_is_left_uncovered(miles: float) -> None:
    route = north(miles)
    points = corridor_points([route], max_points=300)
    for sample in sample_along(route, 20.0):
        assert min(haversine_miles(sample, point) for point in points) <= 30


def test_every_route_is_covered_when_routes_separate() -> None:
    routes = [north(1000, -100.0), north(1000, -105.0), north(1000, -95.0)]
    points = corridor_points(routes, max_points=300)
    for route in routes:
        assert any(miles_to_route(point, route) <= 26 for point in points)


def test_points_dedupe_across_overlapping_routes() -> None:
    once = corridor_points([north(300)])
    twice = corridor_points([north(300), north(300)], max_points=len(once) * 2)
    assert len(twice) <= len(once) * 1.1


def test_grid_is_deterministic() -> None:
    assert corridor_points([bent(500)]) == corridor_points([bent(500)])


def test_no_routes_gives_no_points() -> None:
    assert corridor_points([]) == []
