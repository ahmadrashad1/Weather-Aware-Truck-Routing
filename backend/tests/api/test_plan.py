import gzip
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.test import Client
from rest_framework.throttling import ScopedRateThrottle

from routing.api import views
from routing.providers.base import Place
from routing.providers.errors import NoRouteFound, ProviderRateLimited, ProviderUnavailable
from routing.services.geometry import LatLon
from routing.services.weather_lookup import WeatherLookup
from tests.fakes import FakeRouting, FakeWeather, straight_route

SECRET = "super-secret-provider-key"
NOW = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
DEPARTURE = NOW + timedelta(days=1)


class FakeGeocoding:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def search(self, query: str) -> list[Place]:
        if self.error:
            raise self.error
        return [Place("Dallas, TX", (32.77, -96.79))]


def routes() -> list[Any]:
    return [
        straight_route(100, 7200, lon=-100.0),
        straight_route(120, 9000, lon=-101.0),
        straight_route(140, 10800, lon=-99.0),
    ]


@pytest.fixture
def install(monkeypatch: pytest.MonkeyPatch) -> Any:
    def apply(routing: Any = None, weather: Any = None, geocoding: Any = None) -> None:
        monkeypatch.setattr(views, "get_routing_provider", lambda: routing or FakeRouting(routes()))
        monkeypatch.setattr(
            views, "get_weather_lookup", lambda: WeatherLookup(weather or FakeWeather(NOW))
        )
        monkeypatch.setattr(views, "get_geocoding_provider", lambda: geocoding or FakeGeocoding())

    apply()
    return apply


@pytest.fixture
def payload() -> dict[str, Any]:
    return {
        "origin": {"label": "Dallas, TX", "lat": 32.77, "lon": -96.79},
        "destination": {"label": "Denver, CO", "lat": 39.74, "lon": -104.99},
        "departure_at": DEPARTURE.isoformat(),
        "load_lb": 45_000,
        "interval_miles": 25,
    }


def post(client: Client, body: dict[str, Any]) -> Any:
    return client.post("/api/v1/trips/plan", data=json.dumps(body), content_type="application/json")


def test_plan_returns_the_documented_shape(
    client: Client, install: Any, payload: dict[str, Any]
) -> None:
    response = post(client, payload)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"recommended_route_id", "no_safe_route", "warnings", "routes"}
    assert len(body["routes"]) == 3
    route = body["routes"][0]
    assert body["recommended_route_id"] == route["id"]
    assert set(route) == {
        "id",
        "rank",
        "rationale",
        "summary",
        "geometry",
        "segments",
        "checkpoints",
    }
    assert route["rank"] == 1
    assert set(route["summary"]) == {
        "distance_miles",
        "duration_seconds",
        "arrival_at",
        "severe_miles",
        "high_miles",
        "moderate_miles",
        "low_miles",
        "no_travel_miles",
        "unknown_miles",
        "average_risk",
    }
    assert route["summary"]["distance_miles"] == 100
    assert route["summary"]["low_miles"] == 100
    assert route["summary"]["average_risk"] == 0
    assert route["geometry"]["type"] == "LineString"
    assert route["segments"][0]["risk"] == "low"
    assert set(route["segments"][0]) == {"risk", "from_mile", "to_mile", "coordinates"}


def test_geojson_coordinates_are_lon_lat(
    client: Client, install: Any, payload: dict[str, Any]
) -> None:
    route = post(client, payload).json()["routes"][0]
    assert route["geometry"]["coordinates"][0] == [-100.0, 30.0]
    assert route["segments"][0]["coordinates"][0] == [-100.0, 30.0]


def test_checkpoint_shape_and_values(client: Client, install: Any, payload: dict[str, Any]) -> None:
    def wind(cell: LatLon, at: datetime) -> float:
        return 35.0

    install(weather=FakeWeather(NOW, wind))
    checkpoint = post(client, payload).json()["routes"][0]["checkpoints"][0]
    assert set(checkpoint) == {
        "id",
        "mile",
        "lat",
        "lon",
        "eta",
        "represented_miles",
        "weather",
        "risk",
        "wind_risk",
        "rain_risk",
        "snow_risk",
        "load_adjusted",
        "drivers",
    }
    assert checkpoint["mile"] == 0
    assert (checkpoint["lat"], checkpoint["lon"]) == (30.0, -100.0)
    assert checkpoint["weather"] == {"wind_mph": 35.0, "rain_in_hr": 0.0, "snow_in_hr": 0.0}
    # 35 mph is High, but 45,000 lb is over the 40,000 lb limit.
    assert checkpoint["risk"] == "severe"
    assert checkpoint["wind_risk"] == "severe"
    assert checkpoint["rain_risk"] == "low"
    assert checkpoint["load_adjusted"] is True
    assert checkpoint["drivers"] == ["wind"]
    assert datetime.fromisoformat(checkpoint["eta"]) == DEPARTURE


def test_unknown_checkpoint_has_no_invented_values(
    client: Client, install: Any, payload: dict[str, Any]
) -> None:
    install(weather=FakeWeather(NOW, lambda cell, at: None))
    response = post(client, payload)
    assert response.status_code == 200
    body = response.json()
    checkpoint = body["routes"][0]["checkpoints"][0]
    assert checkpoint["weather"] is None
    assert checkpoint["risk"] == "unknown"
    assert checkpoint["wind_risk"] is None
    assert body["routes"][0]["summary"]["average_risk"] is None
    assert body["recommended_route_id"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("interval_miles", 30),
        ("load_lb", -1),
        ("load_lb", 80_001),
        ("load_lb", "nan"),
        ("load_lb", "inf"),
        ("departure_at", "2020-01-01T00:00:00Z"),
        ("departure_at", (NOW + timedelta(days=15)).isoformat()),
        ("departure_at", "2026-11-01T10:00:00"),
        ("departure_at", "tomorrow"),
    ],
)
def test_invalid_input_returns_400(
    client: Client, install: Any, payload: dict[str, Any], field: str, value: Any
) -> None:
    response = post(client, {**payload, field: value})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "validation_error"
    assert field in body["fields"]


@pytest.mark.parametrize(
    "location",
    [
        {"label": "x", "lat": 91, "lon": 0},
        {"label": "x", "lat": 0, "lon": 181},
        {"label": "x", "lat": "nan", "lon": 0},
        {},
    ],
)
def test_invalid_location_returns_400(
    client: Client, install: Any, payload: dict[str, Any], location: dict[str, Any]
) -> None:
    response = post(client, {**payload, "origin": location})
    assert response.status_code == 400
    assert "origin" in response.json()["fields"]


@pytest.mark.parametrize("load", [0, 80_000])
def test_load_limits_are_inclusive(
    client: Client, install: Any, payload: dict[str, Any], load: int
) -> None:
    assert post(client, {**payload, "load_lb": load}).status_code == 200


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_allowed_intervals(
    client: Client, install: Any, payload: dict[str, Any], interval: int
) -> None:
    assert post(client, {**payload, "interval_miles": interval}).status_code == 200


def test_same_origin_and_destination_returns_400(
    client: Client, install: Any, payload: dict[str, Any]
) -> None:
    response = post(client, {**payload, "destination": payload["origin"]})
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_malformed_json_returns_400(client: Client, install: Any) -> None:
    response = client.post("/api/v1/trips/plan", data="{not json", content_type="application/json")
    assert response.status_code == 400
    assert "code" in response.json()


def test_no_route_returns_422(client: Client, install: Any, payload: dict[str, Any]) -> None:
    install(routing=FakeRouting(error=NoRouteFound("none")))
    response = post(client, payload)
    assert response.status_code == 422
    assert response.json()["code"] == "no_route"


def test_routing_outage_returns_503(client: Client, install: Any, payload: dict[str, Any]) -> None:
    install(routing=FakeRouting(error=ProviderUnavailable("down")))
    response = post(client, payload)
    assert response.status_code == 503
    assert response.json()["code"] == "provider_unavailable"


def test_total_weather_outage_returns_503_with_no_routes(
    client: Client, install: Any, payload: dict[str, Any]
) -> None:
    install(weather=FakeWeather(NOW, error=ProviderUnavailable("down")))
    response = post(client, payload)
    assert response.status_code == 503
    assert "routes" not in response.json()


def test_provider_rate_limit_returns_429(
    client: Client, install: Any, payload: dict[str, Any]
) -> None:
    install(weather=FakeWeather(NOW, error=ProviderRateLimited("slow")))
    response = post(client, payload)
    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"


def test_partial_weather_outage_returns_200_with_warning(
    client: Client, install: Any, payload: dict[str, Any]
) -> None:
    # 100 cells per request and a small trip, so make a long route span two batches.
    weather = FakeWeather(NOW, failures=[])
    original = weather.hourly
    state = {"calls": 0}

    def second_batch_fails(cells: Any, forecast_days: int = 16) -> Any:
        state["calls"] += 1
        if state["calls"] == 2:
            raise ProviderUnavailable("down")
        return original(cells, forecast_days)

    weather.hourly = second_batch_fails  # type: ignore[method-assign]
    install(routing=FakeRouting([straight_route(1500, 90_000)]), weather=weather)
    response = post(client, {**payload, "interval_miles": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["warnings"]
    assert body["routes"][0]["summary"]["unknown_miles"] > 0


def test_response_contains_no_api_key(
    client: Client, install: Any, payload: dict[str, Any]
) -> None:
    install(routing=FakeRouting(error=ProviderUnavailable(f"failed with key={SECRET}")))
    assert SECRET not in post(client, payload).content.decode()


def test_unexpected_error_returns_json_without_details(
    client: Client,
    install: Any,
    payload: dict[str, Any],
) -> None:
    install(routing=FakeRouting(error=RuntimeError(f"boom {SECRET}")))
    client.raise_request_exception = False
    response = post(client, payload)
    assert response.status_code == 500
    assert response.json()["code"] == "server_error"
    assert SECRET not in response.content.decode()


def test_large_response_is_compressed(
    client: Client, install: Any, payload: dict[str, Any]
) -> None:
    response = client.post(
        "/api/v1/trips/plan",
        data=json.dumps(payload),
        content_type="application/json",
        headers={"accept-encoding": "gzip"},
    )
    assert response["Content-Encoding"] == "gzip"
    assert "routes" in json.loads(gzip.decompress(response.content))


@pytest.fixture
def strict_throttle(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(
        ScopedRateThrottle, "THROTTLE_RATES", {"trip_plan": "2/hour", "geocode": "2/minute"}
    )
    yield


def test_plan_requests_are_throttled(
    client: Client, install: Any, payload: dict[str, Any], strict_throttle: None
) -> None:
    assert post(client, payload).status_code == 200
    assert post(client, payload).status_code == 200
    response = post(client, payload)
    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert int(response["Retry-After"]) > 0


def test_geocode_returns_places(client: Client, install: Any) -> None:
    response = client.get("/api/v1/geocode", {"q": "Dall"})
    assert response.status_code == 200
    assert response.json() == {"results": [{"label": "Dallas, TX", "lat": 32.77, "lon": -96.79}]}


def test_geocode_requires_a_query(client: Client, install: Any) -> None:
    response = client.get("/api/v1/geocode")
    assert response.status_code == 400
    assert "q" in response.json()["fields"]


def test_geocode_outage_returns_503(client: Client, install: Any) -> None:
    install(geocoding=FakeGeocoding(error=ProviderUnavailable("down")))
    assert client.get("/api/v1/geocode", {"q": "Dall"}).status_code == 503


def test_geocode_requests_are_throttled(
    client: Client, install: Any, strict_throttle: None
) -> None:
    for _ in range(2):
        assert client.get("/api/v1/geocode", {"q": "Dall"}).status_code == 200
    assert client.get("/api/v1/geocode", {"q": "Dall"}).status_code == 429


def test_schema_is_current() -> None:
    generated = io.StringIO()
    call_command("spectacular", "--validate", "--fail-on-warn", stdout=generated)
    committed = Path(__file__).resolve().parents[2] / "schema.yml"
    assert generated.getvalue() == committed.read_text()
