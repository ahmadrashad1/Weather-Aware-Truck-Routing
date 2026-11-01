"""The load test is only meaningful if the real provider code can read the stand-in's answers."""

import importlib.util
import json
import threading
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from routing.providers.errors import ProviderRateLimited, ProviderUnavailable
from routing.providers.open_meteo import OpenMeteoProvider
from routing.providers.tomtom import TomTomProvider
from routing.services.geometry import haversine_miles
from routing.services.route_alternatives import get_three_routes

STUB_PATH = Path(__file__).resolve().parents[2] / "loadtest" / "stub.py"
DALLAS = (32.78, -96.8)
DENVER = (39.74, -104.99)


@pytest.fixture
def stub() -> Iterator[tuple[ModuleType, str]]:
    spec = importlib.util.spec_from_file_location("load_stub", STUB_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.__dict__["DELAY"] = dict.fromkeys(module.__dict__["DELAY"], 0)
    server = module.Server(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield module, f"http://127.0.0.1:{server.server_address[1]}"
    module.hang_release.set()
    server.shutdown()


def control(url: str, query: str) -> Any:
    request = urllib.request.Request(f"{url}/__control?{query}", method="POST")
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def test_routes_are_realistic_and_three_distinct(stub: tuple[ModuleType, str]) -> None:
    _, url = stub
    provider = TomTomProvider("key", retry_delay_seconds=0, base_url=url)
    result = get_three_routes(provider, DALLAS, DENVER, datetime.now(UTC), 45_000)
    assert len(result.routes) == 3
    assert result.warnings == []
    for route in result.routes:
        assert len(route.geometry) / route.total_miles == pytest.approx(16, abs=1)
        assert route.total_miles > haversine_miles(DALLAS, DENVER)
        assert len(route.profile.points) > 10


def test_search_and_credit_can_be_read(stub: tuple[ModuleType, str]) -> None:
    _, url = stub
    provider = TomTomProvider("key", retry_delay_seconds=0, base_url=url)
    assert provider.search("Dal")[0].label == "Dal, TX"
    assert provider.attribution().cache_control == "max-age=86400"


def test_forecasts_cover_the_app_full_horizon(stub: tuple[ModuleType, str]) -> None:
    _, url = stub
    provider = OpenMeteoProvider(retry_delay_seconds=0, base_url=url)
    cells = [(30.0, -100.0), (30.05, -100.0)]
    forecasts = provider.hourly(cells)
    first = forecasts[cells[0]]
    assert first.times_utc[0] <= datetime.now(UTC)
    assert first.times_utc[-1] >= datetime.now(UTC) + timedelta(days=14)
    assert forecasts[cells[1]].wind_mph != ()
    assert provider.hourly([cells[0]])[cells[0]].times_utc == first.times_utc


def test_the_minute_limit_behaves_like_open_meteos(stub: tuple[ModuleType, str]) -> None:
    _, url = stub
    control(url, "minute_limit=2")
    provider = OpenMeteoProvider(retry_delay_seconds=0, base_url=url)
    provider.hourly([(30.0, -100.0), (30.05, -100.0)])
    with pytest.raises(ProviderRateLimited) as limited:
        provider.hourly([(30.1, -100.0)])
    assert limited.value.retry_after_seconds == 60


def test_outage_modes_reach_the_providers_error_handling(stub: tuple[ModuleType, str]) -> None:
    _, url = stub
    control(url, "mode=error")
    with pytest.raises(ProviderUnavailable):
        OpenMeteoProvider(retry_delay_seconds=0, base_url=url).hourly([(30.0, -100.0)])
    assert control(url, "mode=ok")["mode"] == "ok"
