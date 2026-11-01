import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.test import Client
from rest_framework.throttling import ScopedRateThrottle

from routing.api import views
from routing.providers.errors import ProviderUnavailable
from routing.services.weather_budget import BudgetLimits, WeatherBudget
from routing.services.weather_lookup import WeatherLookup
from tests.fakes import FakeRouting, FakeWeather, straight_route

NOW = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
DEPARTURE = NOW + timedelta(days=1)
PLAN = {
    "origin": {"label": "A", "lat": 30.0, "lon": -100.0},
    "destination": {"label": "B", "lat": 31.45, "lon": -100.0},
    "departure_at": DEPARTURE.isoformat(),
    "load_lb": 45_000,
    "interval_miles": 25,
}


def post(client: Client, path: str, body: dict[str, Any], ip: str = "10.0.0.1") -> Any:
    return client.post(
        f"/api/v1/{path}",
        data=json.dumps(body),
        content_type="application/json",
        REMOTE_ADDR=ip,
    )


def heatmap_body(lon: float = -100.0) -> dict[str, Any]:
    route = [[lon, 30.0], [lon, 31.0], [lon, 32.0]]
    return {"routes": [route], "departure_at": DEPARTURE.isoformat(), "load_lb": 45_000}


@pytest.fixture(autouse=True)
def unthrottled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ScopedRateThrottle, "allow_request", lambda *_: True)


def install(
    monkeypatch: pytest.MonkeyPatch, limits: BudgetLimits, weather: Any = None
) -> FakeWeather:
    provider = weather or FakeWeather(NOW)
    lookup = WeatherLookup(provider, budget=WeatherBudget(limits))
    monkeypatch.setattr(views, "get_weather_lookup", lambda: lookup)
    monkeypatch.setattr(
        views, "get_routing_provider", lambda: FakeRouting([straight_route(100, 7200)])
    )
    return provider


def limits(**overrides: Any) -> BudgetLimits:
    values = {"per_hour": 1000, "per_day": 2000, "per_client_hour": 500, "heatmap_share": 0.8}
    return BudgetLimits(**{**values, **overrides})


def test_a_plan_over_budget_is_refused_with_a_clear_error(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    weather = install(monkeypatch, limits(per_client_hour=1))
    response = post(client, "trips/plan", PLAN)
    assert response.status_code == 429
    assert response.json()["code"] == "quota_exhausted"
    assert weather.requests == []


def test_a_plan_is_never_returned_partly_checked_when_the_budget_runs_out(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, limits(per_client_hour=1))
    response = post(client, "trips/plan", PLAN)
    assert "routes" not in response.json()


def test_a_heatmap_is_refused_while_a_plan_still_runs(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, limits(per_hour=30, heatmap_share=0.1, per_client_hour=30))
    refused = post(client, "trips/heatmap", heatmap_body())
    assert refused.status_code == 429
    assert refused.json()["code"] == "quota_exhausted"
    assert "Forecast shading" in refused.json()["message"]
    assert post(client, "trips/plan", PLAN).status_code == 200


def test_a_clients_repeated_new_heatmaps_hit_its_limit_but_not_anothers(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, limits(per_client_hour=100))
    statuses = [
        post(client, "trips/heatmap", heatmap_body(-120.0 + index)).status_code
        for index in range(10)
    ]
    assert statuses[0] == 200
    assert statuses[-1] == 429
    assert post(client, "trips/heatmap", heatmap_body(-80.0), "10.0.0.2").status_code == 200


def test_a_refusal_is_logged_without_the_clients_address(
    client: Client, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    install(monkeypatch, limits(per_client_hour=1))
    post(client, "trips/plan", PLAN, "10.9.8.7")
    [event] = [
        record.fields  # type: ignore[attr-defined]
        for record in caplog.records
        if record.getMessage() == "weather_budget_refused"
    ]
    assert event["window"] == "client_hour"
    assert event["purpose"] == "checkpoints"
    assert "10.9.8.7" not in caplog.text


def test_a_plan_logs_its_weather_cost(
    client: Client, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    weather = install(monkeypatch, limits())
    post(client, "trips/plan", PLAN)
    [event] = [
        record.fields  # type: ignore[attr-defined]
        for record in caplog.records
        if record.getMessage() == "request"
    ]
    assert event["weather_cells_fetched"] == sum(len(request) for request in weather.requests)
    assert event["weather_cells_cached"] == 0


def test_an_outage_still_marks_nothing_as_safe(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, limits(), FakeWeather(NOW, error=ProviderUnavailable("down")))
    assert post(client, "trips/plan", PLAN).status_code == 503


VITAL = {"name": "LCP", "value": 3152.5, "rating": "needs-improvement"}


def test_a_vital_is_accepted_and_logged(client: Client, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    assert post(client, "vitals", VITAL).status_code == 204
    [event] = [
        record.fields  # type: ignore[attr-defined]
        for record in caplog.records
        if record.getMessage() == "web_vital"
    ]
    assert (event["name"], event["value"], event["rating"]) == ("LCP", 3152.5, "needs-improvement")


@pytest.mark.parametrize(
    "body",
    [
        {**VITAL, "name": "made-up"},
        {**VITAL, "value": -1},
        {**VITAL, "value": 10_000_000},
        {**VITAL, "rating": "great"},
        {"name": "LCP"},
    ],
)
def test_bad_vitals_are_refused(client: Client, body: dict[str, Any]) -> None:
    assert post(client, "vitals", body).status_code == 400
