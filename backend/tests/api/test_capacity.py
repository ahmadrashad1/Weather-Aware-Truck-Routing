import json
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.test import Client
from rest_framework.throttling import ScopedRateThrottle

from routing.api import capacity, views
from routing.services.weather_lookup import WeatherLookup
from tests.fakes import FakeWeather
from tests.services.test_trip_planner import START

BODY = {
    "routes": [[[-100.0, 30.0], [-100.0, 31.0]]],
    "load_lb": 1000,
}


def test_slots_are_refused_once_all_are_taken() -> None:
    limiter = capacity.HeavyRequestLimiter(2)
    with limiter.slot(), limiter.slot(), pytest.raises(capacity.ServerBusy), limiter.slot():
        pass


def test_a_slot_is_given_back_when_its_request_ends() -> None:
    limiter = capacity.HeavyRequestLimiter(1)
    with limiter.slot():
        pass
    with limiter.slot():
        pass


def test_a_slot_is_given_back_when_its_request_fails() -> None:
    limiter = capacity.HeavyRequestLimiter(1)
    with pytest.raises(ValueError), limiter.slot():
        raise ValueError
    with limiter.slot():
        pass


def post_heatmap(client: Client) -> Any:
    departure = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    return client.post(
        "/api/v1/trips/heatmap",
        data=json.dumps({**BODY, "departure_at": departure}),
        content_type="application/json",
    )


@pytest.fixture(autouse=True)
def unthrottled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ScopedRateThrottle, "allow_request", lambda *_: True)


def test_a_full_server_refuses_heavy_work_with_a_clear_error(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(views, "heavy_requests", capacity.HeavyRequestLimiter(0))
    response = post_heatmap(client)
    assert response.status_code == 503
    assert response.json()["code"] == "busy"
    assert response["Retry-After"] == "15"


def test_a_full_server_still_answers_searches_and_health(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(views, "heavy_requests", capacity.HeavyRequestLimiter(0))
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/geocode").status_code == 400


def test_a_refused_request_spends_no_weather(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    weather = FakeWeather(START)
    monkeypatch.setattr(views, "get_weather_lookup", lambda: WeatherLookup(weather))
    monkeypatch.setattr(views, "heavy_requests", capacity.HeavyRequestLimiter(0))
    post_heatmap(client)
    assert weather.requests == []


def test_limiter_is_thread_safe() -> None:
    limiter = capacity.HeavyRequestLimiter(5)
    release = threading.Event()
    admitted: list[int] = []
    refused: list[int] = []

    def attempt() -> None:
        try:
            with limiter.slot():
                admitted.append(1)
                release.wait(5)
        except capacity.ServerBusy:
            refused.append(1)

    threads = [threading.Thread(target=attempt) for _ in range(20)]
    for thread in threads:
        thread.start()
    while len(admitted) + len(refused) < 20:
        pass
    release.set()
    for thread in threads:
        thread.join()
    assert (len(admitted), len(refused)) == (5, 15)
