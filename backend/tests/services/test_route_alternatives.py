import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from routing.providers.base import ProviderRoute
from routing.providers.errors import NoRouteFound, ProviderRateLimited, ProviderUnavailable
from routing.services.eta_calculator import TravelProfile
from routing.services.geometry import LatLon
from routing.services.route_alternatives import get_three_routes, overlap_fraction

ORIGIN = (30.0, -100.0)
DESTINATION = (32.0, -100.0)
DEPARTURE = datetime(2026, 11, 1, 12, tzinfo=UTC)
FIXTURE = Path(__file__).parent.parent / "fixtures" / "tomtom" / "dallas_fortworth.json"


def route(*geometry: LatLon, miles: float = 138.0, seconds: int = 7200) -> ProviderRoute:
    return ProviderRoute(
        geometry=tuple(geometry),
        total_miles=miles,
        duration_seconds=seconds,
        profile=TravelProfile(((0, 0), (miles, seconds))),
    )


STRAIGHT = route(ORIGIN, DESTINATION)
WEST = route(ORIGIN, (31.0, -101.0), DESTINATION, miles=180)
EAST = route(ORIGIN, (31.0, -99.0), DESTINATION, miles=180)


class FakeRouting:
    """Answers the primary call and each via call from separate scripts, and records calls."""

    def __init__(self, primary: list[ProviderRoute], via_answers: list[Any] | None = None) -> None:
        self.primary = primary
        self.via_answers = list(via_answers or [])
        self.calls: list[dict[str, Any]] = []

    def routes(
        self,
        origin: LatLon,
        destination: LatLon,
        departure: datetime,
        load_lb: float,
        via: LatLon | None = None,
        max_alternatives: int = 2,
    ) -> list[ProviderRoute]:
        self.calls.append({"via": via, "max_alternatives": max_alternatives, "load_lb": load_lb})
        if via is None:
            return self.primary
        answer = self.via_answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return [answer]


def run(provider: FakeRouting) -> Any:
    return get_three_routes(provider, ORIGIN, DESTINATION, DEPARTURE, 40_000)


def test_three_returned_needs_no_via() -> None:
    provider = FakeRouting([STRAIGHT, WEST, EAST])
    result = run(provider)
    assert result.routes == [STRAIGHT, WEST, EAST]
    assert result.warnings == []
    assert len(provider.calls) == 1
    assert provider.calls[0]["max_alternatives"] == 2


def test_real_alternatives_are_not_treated_as_duplicates() -> None:
    body = json.loads(FIXTURE.read_text())
    geometries = [
        tuple((p["latitude"], p["longitude"]) for p in r["legs"][0]["points"])
        for r in body["routes"]
    ]
    routes = [route(*g, miles=40) for g in geometries]
    assert len(run(FakeRouting(routes)).routes) == 3


def test_near_duplicates_are_dropped() -> None:
    copy = route(ORIGIN, (31.0, -100.0), DESTINATION)
    result = run(FakeRouting([STRAIGHT, copy, WEST], [EAST, EAST]))
    assert result.routes == [STRAIGHT, WEST, EAST]


def test_more_than_three_candidates_keeps_the_first_three() -> None:
    far_east = route(ORIGIN, (31.0, -98.0), DESTINATION, miles=200)
    result = run(FakeRouting([STRAIGHT, WEST, EAST, far_east]))
    assert result.routes == [STRAIGHT, WEST, EAST]


def test_via_points_requested_when_short() -> None:
    provider = FakeRouting([STRAIGHT], [WEST, EAST])
    result = run(provider)
    assert result.routes == [STRAIGHT, WEST, EAST]
    assert result.warnings == []
    vias = [call["via"] for call in provider.calls[1:]]
    assert all(call["max_alternatives"] == 0 for call in provider.calls[1:])
    # 15% of 138 miles is 20.7 miles, about 0.35 degrees of longitude at latitude 31.
    assert {round(via[0], 2) for via in vias} == {31.0}
    assert sorted(round(via[1], 1) for via in vias) == [-100.3, -99.7]


def test_only_needed_via_calls_are_made() -> None:
    provider = FakeRouting([STRAIGHT, WEST], [EAST])
    assert run(provider).routes == [STRAIGHT, WEST, EAST]
    assert len(provider.calls) == 2


def test_returns_fewer_with_warning_when_exhausted() -> None:
    copy = route(ORIGIN, (31.0, -100.0), DESTINATION)
    result = run(FakeRouting([STRAIGHT], [copy, copy]))
    assert result.routes == [STRAIGHT]
    assert len(result.warnings) == 1
    assert "1" in result.warnings[0]


def test_unroutable_via_is_skipped() -> None:
    result = run(FakeRouting([STRAIGHT], [NoRouteFound("no road"), EAST]))
    assert result.routes == [STRAIGHT, EAST]
    assert len(result.warnings) == 1


@pytest.mark.parametrize("error", [ProviderUnavailable("down"), ProviderRateLimited("slow")])
def test_via_outage_keeps_the_routes_already_found(error: Exception) -> None:
    provider = FakeRouting([STRAIGHT], [error, EAST])
    result = run(provider)
    assert result.routes == [STRAIGHT]
    assert len(result.warnings) == 1
    assert len(provider.calls) == 2


def test_primary_outage_propagates() -> None:
    class Down(FakeRouting):
        def routes(self, *args: Any, **kwargs: Any) -> list[ProviderRoute]:
            raise ProviderUnavailable("down")

    with pytest.raises(ProviderUnavailable):
        run(Down([]))


def test_overlap_of_identical_routes_is_total() -> None:
    assert overlap_fraction(STRAIGHT.geometry, STRAIGHT.geometry) == 1.0


def test_overlap_of_separate_routes_is_small() -> None:
    assert overlap_fraction(WEST.geometry, EAST.geometry) < 0.05


def test_overlap_counts_a_shared_stretch_by_distance() -> None:
    shared_half = ((30.0, -100.0), (31.0, -100.0), (32.0, -101.0))
    whole = ((30.0, -100.0), (31.0, -100.0), (32.0, -100.0))
    assert overlap_fraction(whole, shared_half) == pytest.approx(0.5, abs=0.03)


def test_overlap_tolerates_a_small_offset() -> None:
    # About 180 feet east, like the opposite carriageway of a highway.
    nearby = ((30.0, -99.9994), (32.0, -99.9994))
    assert overlap_fraction(STRAIGHT.geometry, nearby) == 1.0
