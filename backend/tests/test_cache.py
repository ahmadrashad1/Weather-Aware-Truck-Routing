import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.core.cache import cache
from django.test import Client, override_settings

from routing.api import views
from routing.services.weather_lookup import WeatherLookup
from tests.fakes import FakeRouting, FakeWeather, straight_route

# Nothing listens on this port, so this behaves like Redis being down.
UNREACHABLE_REDIS = {
    "default": {
        "BACKEND": "config.cache.ResilientRedisCache",
        "LOCATION": "redis://127.0.0.1:1/0",
    }
}


@pytest.fixture
def redis_down() -> Iterator[None]:
    with override_settings(CACHES=UNREACHABLE_REDIS):
        yield


@pytest.mark.usefixtures("redis_down")
class TestRedisOutage:
    def test_reads_look_like_a_miss(self) -> None:
        assert cache.get("key") is None
        assert cache.get("key", "fallback") == "fallback"
        assert cache.get_many(["a", "b"]) == {}

    def test_writes_are_dropped_without_an_error(self) -> None:
        cache.set("key", "value", 60)
        assert cache.set_many({"a": 1}, 60) == ["a"]
        assert cache.add("key", "value", 60) is False
        assert cache.delete("key") is False

    def test_weather_still_comes_from_the_provider(self) -> None:
        now = datetime(2026, 11, 1, 12, tzinfo=UTC)
        weather = FakeWeather(now)
        position = (30.0, -100.0)
        assert WeatherLookup(weather).forecasts([position])[position] is not None
        assert len(weather.requests) == 1

    def test_the_outage_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        cache.get("key")
        assert "Redis" in caplog.text

    def test_planning_a_trip_still_works(
        self, client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Throttling needs the cache too, so this covers a whole request.
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        routing: Any = FakeRouting([straight_route(100, 7200)])
        monkeypatch.setattr(views, "get_routing_provider", lambda: routing)
        monkeypatch.setattr(views, "get_weather_lookup", lambda: WeatherLookup(FakeWeather(now)))
        response = client.post(
            "/api/v1/trips/plan",
            data=json.dumps(
                {
                    "origin": {"label": "A", "lat": 30.0, "lon": -100.0},
                    "destination": {"label": "B", "lat": 31.0, "lon": -100.0},
                    "departure_at": (now + timedelta(days=1)).isoformat(),
                    "load_lb": 1000,
                    "interval_miles": 50,
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 200
