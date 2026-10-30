import pytest

from routing.services.checkpoint_generator import generate_checkpoints
from routing.services.geometry import LatLon, haversine_miles

# One degree of latitude is about 69.09 miles on the sphere haversine_miles uses.
MILES_PER_DEGREE_LATITUDE = 69.09


def straight_line(miles: float) -> list[LatLon]:
    return [(30.0, -100.0), (30.0 + miles / MILES_PER_DEGREE_LATITUDE, -100.0)]


def curved_line() -> list[LatLon]:
    return [(30.0, -100.0), (31.0, -100.0), (31.5, -99.0), (33.0, -98.5), (34.0, -97.0)]


def test_haversine_one_degree_of_latitude() -> None:
    assert haversine_miles((30.0, -100.0), (31.0, -100.0)) == pytest.approx(69.09, abs=0.05)


def test_120_mile_route_at_50() -> None:
    cps = generate_checkpoints(straight_line(120), 120, 50)
    assert [round(c.mile, 2) for c in cps] == [0, 50, 100, 120]
    assert [round(c.represented_miles, 2) for c in cps] == [25, 50, 35, 10]


def test_represented_ranges_are_contiguous() -> None:
    cps = generate_checkpoints(straight_line(120), 120, 50)
    assert [(round(c.start_mile, 2), round(c.end_mile, 2)) for c in cps] == [
        (0, 25),
        (25, 75),
        (75, 110),
        (110, 120),
    ]


@pytest.mark.parametrize(
    "interval,expected_miles",
    [
        (10, [0, 10, 20, 30, 35]),
        (25, [0, 25, 35]),
        (50, [0, 35]),
    ],
)
def test_interval_sets_checkpoint_spacing(interval: int, expected_miles: list[float]) -> None:
    cps = generate_checkpoints(straight_line(35), 35, interval)
    assert [round(c.mile, 2) for c in cps] == expected_miles


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_represented_miles_sum_to_length(interval: int) -> None:
    cps = generate_checkpoints(curved_line(), 333.3, interval)
    assert sum(c.represented_miles for c in cps) == pytest.approx(333.3)


def test_route_shorter_than_interval_has_endpoints_only() -> None:
    assert [c.mile for c in generate_checkpoints(straight_line(8), 8, 50)] == [0, 8]


def test_route_of_exact_multiple_does_not_duplicate_destination() -> None:
    assert [c.mile for c in generate_checkpoints(straight_line(100), 100, 50)] == [0, 50, 100]


def test_interval_outside_allowed_values_rejected() -> None:
    with pytest.raises(ValueError):
        generate_checkpoints(straight_line(50), 50, 30)


@pytest.mark.parametrize("miles", [0, -1])
def test_non_positive_length_rejected(miles: float) -> None:
    with pytest.raises(ValueError):
        generate_checkpoints(straight_line(50), miles, 10)


def test_geometry_needs_two_points() -> None:
    with pytest.raises(ValueError):
        generate_checkpoints([(30.0, -100.0)], 50, 10)


def test_endpoints_match_geometry() -> None:
    geometry = curved_line()
    cps = generate_checkpoints(geometry, 333.3, 25)
    assert cps[0].position == geometry[0]
    assert cps[-1].position == geometry[-1]


def test_position_lies_on_second_leg_of_bent_line() -> None:
    # Two 69.09-mile legs: north, then east along latitude 31.
    geometry: list[LatLon] = [(30.0, -100.0), (31.0, -100.0), (31.0, -98.8)]
    length = haversine_miles(geometry[0], geometry[1]) + haversine_miles(geometry[1], geometry[2])
    cps = generate_checkpoints(geometry, length, 50)
    at_100 = next(c for c in cps if round(c.mile) == 100)
    assert at_100.position[0] == pytest.approx(31.0, abs=0.001)
    miles_past_bend = haversine_miles(geometry[1], at_100.position)
    assert miles_past_bend == pytest.approx(
        100 - haversine_miles(geometry[0], geometry[1]), abs=0.01
    )


def test_position_scales_when_reported_length_differs_from_geometry() -> None:
    # The provider reports 200 miles for a 100-mile line, so mile 100 is the geometric midpoint.
    cps = generate_checkpoints(straight_line(100), 200, 50)
    midpoint = next(c for c in cps if c.mile == 100)
    assert midpoint.position[0] == pytest.approx(30.0 + 50 / MILES_PER_DEGREE_LATITUDE, abs=0.001)


def test_repeated_geometry_points_are_tolerated() -> None:
    geometry: list[LatLon] = [(30.0, -100.0), (30.0, -100.0), (31.0, -100.0), (31.0, -100.0)]
    cps = generate_checkpoints(geometry, 69.09, 25)
    assert [round(c.mile, 2) for c in cps] == [0, 25, 50, 69.09]
    assert cps[-1].position == (31.0, -100.0)
