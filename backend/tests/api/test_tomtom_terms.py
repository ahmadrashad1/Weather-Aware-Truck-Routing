from typing import Any

import pytest
from django.test import Client

from routing.api import views
from routing.providers.base import Attribution, Place
from routing.providers.errors import ProviderUnavailable


class FakeTomTom:
    def __init__(self, attribution: Attribution | None = None) -> None:
        self.result = attribution
        self.calls = 0

    def attribution(self) -> Attribution:
        self.calls += 1
        if not self.result:
            raise ProviderUnavailable("down")
        return self.result

    def search(self, query: str) -> list[Place]:
        return [Place("Dallas, TX", (32.77, -96.79))]


def install(monkeypatch: pytest.MonkeyPatch, fake: FakeTomTom) -> FakeTomTom:
    monkeypatch.setattr(views, "get_attribution_provider", lambda: fake)
    monkeypatch.setattr(views, "get_geocoding_provider", lambda: fake)
    return fake


def get(client: Client) -> Any:
    return client.get("/api/v1/attribution")


def test_attribution_returns_the_providers_caption(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeTomTom(Attribution("©TomTom", "max-age=86400")))
    response = get(client)
    assert response.status_code == 200
    assert response.json() == {"routing_caption": "©TomTom"}


def test_attribution_passes_on_tomtoms_cache_period_so_browsers_follow_it(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeTomTom(Attribution("©TomTom", "max-age=86400")))
    assert get(client)["Cache-Control"] == "max-age=86400"


def test_attribution_is_not_kept_when_tomtom_sets_no_cache_period(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeTomTom(Attribution("©TomTom", None)))
    assert get(client)["Cache-Control"] == "no-store"


def test_the_server_never_stores_tomtoms_attribution(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(monkeypatch, FakeTomTom(Attribution("©TomTom", "max-age=86400")))
    get(client)
    get(client)
    assert fake.calls == 2


def test_attribution_outage_is_an_error_rather_than_a_made_up_caption(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeTomTom())
    response = get(client)
    assert response.status_code == 503
    assert "routing_caption" not in response.json()


def test_search_results_tell_browsers_not_to_keep_them(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeTomTom())
    assert client.get("/api/v1/geocode", {"q": "Dal"})["Cache-Control"] == "no-store"
