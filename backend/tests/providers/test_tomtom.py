import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from routing.providers.errors import NoRouteFound, ProviderRateLimited, ProviderUnavailable
from routing.providers.tomtom import TomTomProvider

FIXTURES = Path(__file__).parent.parent / "fixtures" / "tomtom"
API_KEY = "test-secret-key-do-not-leak"
ORIGIN = (32.7767, -96.797)
DESTINATION = (32.7555, -97.3308)
DEPARTURE = datetime(2026, 11, 1, 12, tzinfo=UTC)
SEARCH_URL = "https://api.tomtom.com/search/2/search"
ROUTE_URL = "https://api.tomtom.com/routing/1/calculateRoute/32.7767,-96.797:32.7555,-97.3308/json"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def route_body(
    meters: int = 16093,
    seconds: int = 1000,
    legs: list[list[tuple[float, float]]] | None = None,
    instructions: list[dict[str, int]] | None = None,
) -> dict[str, Any]:
    route: dict[str, Any] = {
        "summary": {"lengthInMeters": meters, "travelTimeInSeconds": seconds},
        "legs": [
            {"points": [{"latitude": lat, "longitude": lon} for lat, lon in leg]}
            for leg in (legs or [[(32.0, -96.0), (32.1, -96.0)]])
        ],
    }
    if instructions is not None:
        route["guidance"] = {"instructions": instructions}
    return {"routes": [route]}


@pytest.fixture
def provider() -> TomTomProvider:
    return TomTomProvider(API_KEY, retry_delay_seconds=0)


@pytest.fixture
def mocked() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def plan(provider: TomTomProvider, **kwargs: Any) -> Any:
    return provider.routes(ORIGIN, DESTINATION, DEPARTURE, 40_000, **kwargs)


def test_parses_fixture_into_routes(provider: TomTomProvider, mocked: respx.MockRouter) -> None:
    mocked.get(ROUTE_URL).mock(httpx.Response(200, json=fixture("dallas_fortworth.json")))
    routes = plan(provider)
    assert [r.duration_seconds for r in routes] == [2209, 2598, 2802]
    assert [round(r.total_miles, 2) for r in routes] == [32.51, 36.82, 40.99]
    assert routes[0].geometry[0] == (32.77667, -96.79699)
    assert routes[0].geometry[-1] == (32.75552, -97.33081)


def test_profile_follows_guidance_times(provider: TomTomProvider, mocked: respx.MockRouter) -> None:
    mocked.get(ROUTE_URL).mock(httpx.Response(200, json=fixture("dallas_fortworth.json")))
    points = plan(provider)[0].profile.points
    assert points[0] == (0, 0)
    assert points[1] == pytest.approx((120 / 1609.344, 24))
    assert points[-1] == pytest.approx((32.5114, 2209), abs=0.001)


def test_profile_without_guidance_is_two_points(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    mocked.get(ROUTE_URL).mock(httpx.Response(200, json=route_body(16093, 1000)))
    start, end, *rest = plan(provider)[0].profile.points
    assert start == (0, 0)
    assert end == pytest.approx((10.0, 1000), abs=0.001)
    assert rest == []


def test_profile_skips_non_increasing_instructions(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    instructions = [
        {"routeOffsetInMeters": 0, "travelTimeInSeconds": 0},
        {"routeOffsetInMeters": 1609, "travelTimeInSeconds": 100},
        {"routeOffsetInMeters": 1609, "travelTimeInSeconds": 150},
        {"routeOffsetInMeters": 3218, "travelTimeInSeconds": 100},
        {"routeOffsetInMeters": 16093, "travelTimeInSeconds": 1000},
    ]
    mocked.get(ROUTE_URL).mock(
        httpx.Response(200, json=route_body(16093, 1000, instructions=instructions))
    )
    miles = [round(point[0], 1) for point in plan(provider)[0].profile.points]
    assert miles == [0, 1.0, 10.0]


def test_profile_always_ends_at_route_totals(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    instructions = [
        {"routeOffsetInMeters": 8046, "travelTimeInSeconds": 500},
        {"routeOffsetInMeters": 20000, "travelTimeInSeconds": 1500},
    ]
    mocked.get(ROUTE_URL).mock(
        httpx.Response(200, json=route_body(16093, 1000, instructions=instructions))
    )
    assert plan(provider)[0].profile.points[-1] == pytest.approx((10.0, 1000), abs=0.001)


def test_legs_join_without_repeating_the_shared_point(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    legs = [[(32.0, -96.0), (32.1, -96.0)], [(32.1, -96.0), (32.2, -96.0)]]
    mocked.get(ROUTE_URL).mock(httpx.Response(200, json=route_body(legs=legs)))
    assert plan(provider)[0].geometry == ((32.0, -96.0), (32.1, -96.0), (32.2, -96.0))


def test_cargo_plus_tare_sent_as_kg(provider: TomTomProvider, mocked: respx.MockRouter) -> None:
    call = mocked.get(ROUTE_URL).mock(httpx.Response(200, json=route_body()))
    plan(provider)
    assert call.calls.last.request.url.params["vehicleWeight"] == "33112"


def test_requests_a_commercial_truck_route_at_the_departure_time(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    call = mocked.get(ROUTE_URL).mock(httpx.Response(200, json=route_body()))
    plan(provider, max_alternatives=2)
    params = call.calls.last.request.url.params
    assert params["travelMode"] == "truck"
    assert params["vehicleCommercial"] == "true"
    assert params["maxAlternatives"] == "2"
    assert params["departAt"] == "2026-11-01T12:00:00+00:00"
    assert params["instructionsType"] == "coded"


def test_route_speed_is_capped_for_a_truck(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    call = mocked.get(ROUTE_URL).mock(httpx.Response(200, json=route_body()))
    plan(provider)
    assert call.calls.last.request.url.params["vehicleMaxSpeed"] == "105"


def test_via_point_goes_between_origin_and_destination(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    call = mocked.get(
        "https://api.tomtom.com/routing/1/calculateRoute/"
        "32.7767,-96.797:33.0,-97.0:32.7555,-97.3308/json"
    ).mock(httpx.Response(200, json=route_body()))
    plan(provider, via=(33.0, -97.0), max_alternatives=0)
    assert call.called


def test_429_raises_rate_limited(provider: TomTomProvider, mocked: respx.MockRouter) -> None:
    call = mocked.get(ROUTE_URL).mock(httpx.Response(429))
    with pytest.raises(ProviderRateLimited):
        plan(provider)
    assert call.call_count == 1


def test_5xx_is_retried_twice_then_raises_unavailable(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    call = mocked.get(ROUTE_URL).mock(httpx.Response(503))
    with pytest.raises(ProviderUnavailable):
        plan(provider)
    assert call.call_count == 3


def test_5xx_then_success_returns_routes(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    mocked.get(ROUTE_URL).mock(
        side_effect=[httpx.Response(502), httpx.Response(200, json=route_body())]
    )
    assert len(plan(provider)) == 1


def test_timeout_raises_unavailable_without_retry(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    call = mocked.get(ROUTE_URL).mock(side_effect=httpx.ConnectTimeout("timed out"))
    with pytest.raises(ProviderUnavailable):
        plan(provider)
    assert call.call_count == 1


def test_no_route_response_raises_no_route(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    mocked.get(ROUTE_URL).mock(httpx.Response(400, json=fixture("no_route_honolulu_la.json")))
    with pytest.raises(NoRouteFound):
        plan(provider)


def test_empty_route_list_raises_no_route(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    mocked.get(ROUTE_URL).mock(httpx.Response(200, json={"routes": []}))
    with pytest.raises(NoRouteFound):
        plan(provider)


def test_zero_length_route_raises_no_route(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    mocked.get(ROUTE_URL).mock(httpx.Response(200, json=route_body(0, 0)))
    with pytest.raises(NoRouteFound):
        plan(provider)


def test_other_400_raises_unavailable_not_no_route(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    body = {"detailedError": {"code": "BAD_INPUT", "message": "Invalid request"}}
    mocked.get(ROUTE_URL).mock(httpx.Response(400, json=body))
    with pytest.raises(ProviderUnavailable):
        plan(provider)


def test_rejected_key_raises_unavailable(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    mocked.get(ROUTE_URL).mock(
        httpx.Response(401, json={"detailedError": {"code": "Unauthorized"}})
    )
    with pytest.raises(ProviderUnavailable):
        plan(provider)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"routes": [{"summary": {}}]}),
    ],
)
def test_malformed_response_raises_unavailable(
    provider: TomTomProvider, mocked: respx.MockRouter, response: httpx.Response
) -> None:
    mocked.get(ROUTE_URL).mock(response)
    with pytest.raises(ProviderUnavailable):
        plan(provider)


def test_missing_key_raises_unavailable_without_a_request(mocked: respx.MockRouter) -> None:
    call = mocked.get(ROUTE_URL)
    with pytest.raises(ProviderUnavailable):
        plan(TomTomProvider(""))
    assert not call.called


@pytest.mark.parametrize(
    "side_effect",
    [
        httpx.Response(500),
        httpx.Response(429),
        httpx.ConnectError("failed"),
    ],
)
def test_api_key_absent_from_logs_and_errors(
    provider: TomTomProvider,
    mocked: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
    side_effect: Any,
) -> None:
    mocked.get(ROUTE_URL).mock(side_effect=[side_effect] * 3)
    caplog.set_level(logging.DEBUG)
    with pytest.raises((ProviderUnavailable, ProviderRateLimited)) as error:
        plan(provider)
    chain: list[BaseException | None] = [
        error.value,
        error.value.__cause__,
        error.value.__context__,
    ]
    assert API_KEY not in " ".join(repr(item) + str(item) for item in chain)
    assert API_KEY not in caplog.text


def test_successful_request_does_not_log_the_url(
    provider: TomTomProvider, mocked: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    mocked.get(ROUTE_URL).mock(httpx.Response(200, json=route_body()))
    caplog.set_level(logging.DEBUG)
    plan(provider)
    assert API_KEY not in caplog.text


def test_search_parses_places(provider: TomTomProvider, mocked: respx.MockRouter) -> None:
    mocked.get(f"{SEARCH_URL}/Dall.json").mock(
        httpx.Response(200, json=fixture("search_dall.json"))
    )
    place = provider.search("Dall")[0]
    assert place.label == "Dallas, TX"
    assert place.position == (32.777976, -96.796215)


def test_search_covers_us_cities_and_addresses_as_the_user_types(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    call = mocked.get(f"{SEARCH_URL}/Dall.json").mock(httpx.Response(200, json={"results": []}))
    provider.search("Dall")
    params = call.calls.last.request.url.params
    assert params["countrySet"] == "US"
    assert params["typeahead"] == "true"
    assert params["idxSet"] == "Geo,Str,PAD,Addr"


def test_search_encodes_path_characters(provider: TomTomProvider, mocked: respx.MockRouter) -> None:
    call = mocked.get(f"{SEARCH_URL}/a%2Fb%3F.json").mock(httpx.Response(200, json={"results": []}))
    assert provider.search("a/b?") == []
    assert call.called


@pytest.mark.parametrize("query", ["", "   "])
def test_blank_search_makes_no_request(
    provider: TomTomProvider, mocked: respx.MockRouter, query: str
) -> None:
    assert provider.search(query) == []
    assert not mocked.calls.called


def test_search_outage_raises_unavailable(
    provider: TomTomProvider, mocked: respx.MockRouter
) -> None:
    mocked.get(f"{SEARCH_URL}/Dallas.json").mock(httpx.Response(500))
    with pytest.raises(ProviderUnavailable):
        provider.search("Dallas")
