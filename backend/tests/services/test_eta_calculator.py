from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from routing.services.eta_calculator import TravelProfile, eta_at

DEPARTURE = datetime(2026, 11, 1, 12, tzinfo=UTC)


def test_eta_uses_profile_not_average_speed() -> None:
    profile = TravelProfile(((0, 0), (50, 3600), (100, 10800)))
    assert eta_at(50, DEPARTURE, profile) == DEPARTURE + timedelta(hours=1)
    assert eta_at(75, DEPARTURE, profile) == DEPARTURE + timedelta(hours=2)


def test_eta_at_route_ends() -> None:
    profile = TravelProfile(((0, 0), (100, 7200)))
    assert eta_at(0, DEPARTURE, profile) == DEPARTURE
    assert eta_at(100, DEPARTURE, profile) == DEPARTURE + timedelta(hours=2)


def test_eta_preserves_instant_across_dst() -> None:
    # New York falls back at 02:00 local on 2026-11-01, so 3 elapsed hours land at 02:30 EST.
    departure = datetime(2026, 11, 1, 0, 30, tzinfo=ZoneInfo("America/New_York"))
    profile = TravelProfile(((0, 0), (100, 10800)))
    eta = eta_at(100, departure, profile)
    assert eta.astimezone(UTC) == datetime(2026, 11, 1, 7, 30, tzinfo=UTC)


def test_naive_departure_rejected() -> None:
    profile = TravelProfile(((0, 0), (100, 7200)))
    with pytest.raises(ValueError):
        eta_at(10, datetime(2026, 11, 1, 12), profile)


@pytest.mark.parametrize("mile", [-1, 100.5])
def test_mile_outside_route_rejected(mile: float) -> None:
    profile = TravelProfile(((0, 0), (100, 7200)))
    with pytest.raises(ValueError):
        eta_at(mile, DEPARTURE, profile)


@pytest.mark.parametrize(
    "points",
    [
        ((0, 0),),
        ((1, 0), (100, 7200)),
        ((0, 10), (100, 7200)),
        ((0, 0), (50, 3600), (50, 3700)),
        ((0, 0), (50, 3600), (100, 3600)),
    ],
)
def test_invalid_profile_rejected(points: tuple[tuple[float, float], ...]) -> None:
    with pytest.raises(ValueError):
        TravelProfile(points)
