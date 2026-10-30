from datetime import UTC, datetime, timedelta

import pytest

from routing.providers.errors import ProviderUnavailable
from routing.services.geometry import LatLon
from routing.services.heatmap import HEATMAP_FRAMES, build_heatmap
from routing.services.weather_lookup import WeatherLookup
from tests.fakes import FakeWeather

START = datetime(2026, 11, 1, 12, tzinfo=UTC)
POINT = (30.0, -100.0)
OTHER = (35.0, -105.0)


def lookup(weather: FakeWeather) -> WeatherLookup:
    return WeatherLookup(weather)


def test_returns_49_frames_per_point() -> None:
    heatmap = build_heatmap([POINT, OTHER], START, 1000, lookup(FakeWeather(START)))
    assert HEATMAP_FRAMES == 49
    assert heatmap.points == (POINT, OTHER)
    assert len(heatmap.risk) == 2
    assert all(len(frames) == 49 for frames in heatmap.risk)


def test_frame_h_samples_departure_plus_h() -> None:
    # Wind rises by hour, so each frame is only right if it reads its own hour.
    def wind(cell: LatLon, at: datetime) -> float:
        hours = (at - START) / timedelta(hours=1)
        return {0: 10.0, 12: 30.0, 24: 40.0, 36: 50.0, 48: 60.0}.get(int(hours), 5.0)

    frames = build_heatmap([POINT], START, 1000, lookup(FakeWeather(START, wind))).risk[0]
    assert [frames[hour] for hour in (0, 1, 12, 24, 36, 48)] == [0, 0, 1, 2, 3, 4]


def test_frames_count_from_departure_not_from_now() -> None:
    departure = START + timedelta(hours=5)

    def wind(cell: LatLon, at: datetime) -> float:
        return 60.0 if at == departure else 5.0

    frames = build_heatmap([POINT], departure, 1000, lookup(FakeWeather(START, wind))).risk[0]
    assert frames[0] == 4
    assert frames[1] == 0


def test_rain_counts_towards_the_risk() -> None:
    weather = FakeWeather(START, rain_at=lambda cell, at: 0.3)
    assert build_heatmap([POINT], START, 1000, lookup(weather)).risk[0][0] == 2


@pytest.mark.parametrize("load,expected", [(40_000, 2), (40_001, 3)])
def test_load_rules_apply(load: float, expected: int) -> None:
    weather = FakeWeather(START, lambda cell, at: 35.0)
    assert build_heatmap([POINT], START, load, lookup(weather)).risk[0][0] == expected


def test_missing_hour_is_null_not_zero() -> None:
    def wind(cell: LatLon, at: datetime) -> float | None:
        return None if at == START + timedelta(hours=3) else 5.0

    frames = build_heatmap([POINT], START, 1000, lookup(FakeWeather(START, wind))).risk[0]
    assert frames[3] is None
    assert frames[0] == 0


def test_hours_past_the_forecast_are_null() -> None:
    frames = build_heatmap([POINT], START, 1000, lookup(FakeWeather(START, hours=10))).risk[0]
    assert frames[9] == 0
    assert frames[10] is None
    assert frames[48] is None


def test_point_whose_batch_failed_is_all_null() -> None:
    weather = FakeWeather(START)
    original = weather.hourly

    def only_first_cell(cells: list[LatLon]) -> dict:  # type: ignore[type-arg]
        return {cell: forecast for cell, forecast in original(cells).items() if cell == POINT}

    weather.hourly = only_first_cell  # type: ignore[method-assign,assignment]
    heatmap = build_heatmap([POINT, OTHER], START, 1000, lookup(weather))
    assert heatmap.risk[0][0] == 0
    assert heatmap.risk[1] == (None,) * 49


def test_total_outage_raises() -> None:
    weather = FakeWeather(START, error=ProviderUnavailable("down"))
    with pytest.raises(ProviderUnavailable):
        build_heatmap([POINT], START, 1000, lookup(weather))
