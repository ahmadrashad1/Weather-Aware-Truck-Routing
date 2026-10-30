import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.test import Client
from rest_framework.throttling import ScopedRateThrottle

from routing.api import views
from routing.providers.errors import ProviderRateLimited, ProviderUnavailable
from routing.services.weather_lookup import WeatherLookup
from tests.fakes import FakeWeather

NOW = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
DEPARTURE = NOW + timedelta(days=1)
ROUTE = [[-100.0, 30.0], [-100.0, 31.0], [-100.0, 32.0]]


@pytest.fixture
def install(monkeypatch: pytest.MonkeyPatch) -> Any:
    def apply(weather: Any = None) -> None:
        monkeypatch.setattr(
            views, "get_weather_lookup", lambda: WeatherLookup(weather or FakeWeather(NOW))
        )

    apply()
    return apply


@pytest.fixture
def payload() -> dict[str, Any]:
    return {"routes": [ROUTE], "departure_at": DEPARTURE.isoformat(), "load_lb": 45_000}


def post(client: Client, body: dict[str, Any]) -> Any:
    return client.post(
        "/api/v1/trips/heatmap", data=json.dumps(body), content_type="application/json"
    )


def test_heatmap_returns_the_documented_shape(
    client: Client, install: Any, payload: dict[str, Any]
) -> None:
    response = post(client, payload)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"departure_at", "hours", "points", "risk"}
    assert body["hours"] == 49
    assert datetime.fromisoformat(body["departure_at"]) == DEPARTURE
    assert len(body["points"]) == len(body["risk"])
    assert all(len(frames) == 49 for frames in body["risk"])


def test_points_are_lon_lat_near_the_route(
    client: Client, install: Any, payload: dict[str, Any]
) -> None:
    points = post(client, payload).json()["points"]
    assert all(-101 < lon < -99 and 29 < lat < 33 for lon, lat in points)


def test_load_weight_changes_the_risk(
    client: Client, install: Any, payload: dict[str, Any]
) -> None:
    install(FakeWeather(NOW, lambda cell, at: 35.0))
    # 45,000 lb is over the limit that raises 35 mph from High to Severe.
    assert post(client, payload).json()["risk"][0][0] == 3
    assert post(client, {**payload, "load_lb": 40_000}).json()["risk"][0][0] == 2


def test_missing_weather_is_null(client: Client, install: Any, payload: dict[str, Any]) -> None:
    install(FakeWeather(NOW, lambda cell, at: None))
    assert post(client, payload).json()["risk"][0][0] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("routes", []),
        ("routes", [ROUTE, ROUTE, ROUTE, ROUTE]),
        ("routes", [[[-100.0, 30.0]]]),
        ("routes", [[[-100.0, 91.0], [-100.0, 30.0]]]),
        ("routes", [[[-181.0, 30.0], [-100.0, 30.0]]]),
        ("routes", [[["a", "b"], [-100.0, 30.0]]]),
        ("routes", [[[-100.0, 30.0, 5.0], [-100.0, 31.0]]]),
        ("routes", [[[-100.0, "nan"], [-100.0, 31.0]]]),
        ("routes", "not a list"),
        ("load_lb", -1),
        ("load_lb", 80_001),
        ("departure_at", "2020-01-01T00:00:00Z"),
        ("departure_at", "2026-11-01T10:00:00"),
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


def test_overlong_route_returns_400(client: Client, install: Any, payload: dict[str, Any]) -> None:
    long_route = [[-100.0, 30.0 + i * 0.0001] for i in range(20_001)]
    response = post(client, {**payload, "routes": [long_route]})
    assert response.status_code == 400


def test_outage_returns_503(client: Client, install: Any, payload: dict[str, Any]) -> None:
    install(FakeWeather(NOW, error=ProviderUnavailable("down")))
    response = post(client, payload)
    assert response.status_code == 503
    assert response.json()["code"] == "provider_unavailable"


def test_rate_limit_returns_429(client: Client, install: Any, payload: dict[str, Any]) -> None:
    install(FakeWeather(NOW, error=ProviderRateLimited("slow")))
    assert post(client, payload).status_code == 429


@pytest.fixture
def strict_throttle(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"heatmap": "1/hour"})
    yield


def test_heatmap_requests_are_throttled(
    client: Client, install: Any, payload: dict[str, Any], strict_throttle: None
) -> None:
    assert post(client, payload).status_code == 200
    assert post(client, payload).status_code == 429
