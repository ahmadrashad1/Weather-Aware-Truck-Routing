import time
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta, timezone

import pytest
from django.core.cache import cache

from routing.domain import WeatherSample
from routing.providers.base import HourlyForecast
from routing.providers.errors import ProviderRateLimited, ProviderUnavailable
from routing.services.geometry import LatLon
from routing.services.weather_lookup import WeatherLookup, sample_at, snap_to_cell

START = datetime(2026, 11, 1, 14, tzinfo=UTC)


def forecast(
    wind: tuple[float | None, ...] = (20.0, 30.0, 40.0),
    rain: tuple[float | None, ...] = (0.1, 0.2, 0.3),
    snow: tuple[float | None, ...] = (1.0, 2.0, 3.0),
) -> HourlyForecast:
    return HourlyForecast(
        times_utc=tuple(START + timedelta(hours=hour) for hour in range(3)),
        wind_mph=wind,
        rain_in_hr=rain,
        snow_in_hr=snow,
    )


class FakeWeather:
    def __init__(self, failures: Sequence[Exception | None] = ()) -> None:
        self.failures = list(failures)
        self.requests: list[list[LatLon]] = []

    def hourly(self, cells: Sequence[LatLon]) -> dict[LatLon, HourlyForecast]:
        self.requests.append(list(cells))
        failure = self.failures.pop(0) if self.failures else None
        if failure:
            raise failure
        return {cell: forecast() for cell in cells}


@pytest.fixture(autouse=True)
def clear_cache() -> Iterator[None]:
    cache.clear()
    yield
    cache.clear()


def grid(count: int) -> list[LatLon]:
    return [(30.0 + index * 0.1, -100.0) for index in range(count)]


def test_precip_uses_hour_covering_eta() -> None:
    sample = sample_at(forecast(), START + timedelta(minutes=20))
    assert sample is not None
    assert (sample.rain_in_hr, sample.snow_in_hr) == (0.2, 2.0)


def test_precip_at_exact_hour_uses_that_hour() -> None:
    sample = sample_at(forecast(), START + timedelta(hours=1))
    assert sample is not None
    assert (sample.rain_in_hr, sample.snow_in_hr) == (0.2, 2.0)


def test_wind_interpolates() -> None:
    sample = sample_at(forecast(), START + timedelta(minutes=30))
    assert sample == WeatherSample(wind_mph=25.0, rain_in_hr=0.2, snow_in_hr=2.0)


def test_wind_at_exact_hour_is_not_interpolated() -> None:
    sample = sample_at(forecast(), START + timedelta(hours=1))
    assert sample is not None
    assert sample.wind_mph == 30.0


def test_eta_at_first_and_last_hour_are_covered() -> None:
    assert sample_at(forecast(), START) == WeatherSample(20.0, 0.1, 1.0)
    assert sample_at(forecast(), START + timedelta(hours=2)) == WeatherSample(40.0, 0.3, 3.0)


def test_eta_past_horizon_returns_none() -> None:
    assert sample_at(forecast(), START + timedelta(hours=2, seconds=1)) is None


def test_eta_before_forecast_returns_none() -> None:
    assert sample_at(forecast(), START - timedelta(seconds=1)) is None


@pytest.mark.parametrize(
    "data",
    [
        forecast(wind=(20.0, None, 40.0)),
        forecast(rain=(0.1, None, 0.3)),
        forecast(snow=(1.0, None, 3.0)),
    ],
)
def test_null_values_return_none(data: HourlyForecast) -> None:
    assert sample_at(data, START + timedelta(minutes=30)) is None


def test_eta_with_offset_matches_utc_hour() -> None:
    # 09:20 at UTC-5 is 14:20 UTC, which the 15:00 UTC value covers.
    eta = datetime(2026, 11, 1, 9, 20, tzinfo=timezone(timedelta(hours=-5)))
    sample = sample_at(forecast(), eta)
    assert sample is not None
    assert sample.rain_in_hr == 0.2


def test_naive_eta_rejected() -> None:
    with pytest.raises(ValueError):
        sample_at(forecast(), datetime(2026, 11, 1, 14, 20))


@pytest.mark.parametrize(
    "position,expected",
    [
        ((39.7392, -104.9903), (39.75, -105.0)),
        ((32.7767, -96.797), (32.8, -96.8)),
        ((30.024, -100.024), (30.0, -100.0)),
        ((30.026, -100.026), (30.05, -100.05)),
    ],
)
def test_snap_to_cell(position: LatLon, expected: LatLon) -> None:
    assert snap_to_cell(position) == expected


def test_forecasts_are_keyed_by_the_requested_position() -> None:
    position = (39.7392, -104.9903)
    assert WeatherLookup(FakeWeather()).forecasts([position])[position] == forecast()


def test_nearby_positions_share_one_cell() -> None:
    weather = FakeWeather()
    result = WeatherLookup(weather).forecasts([(39.7392, -104.9903), (39.74, -104.99)])
    assert weather.requests == [[(39.75, -105.0)]]
    assert len(result) == 2


def test_no_positions_makes_no_request() -> None:
    weather = FakeWeather()
    assert WeatherLookup(weather).forecasts([]) == {}
    assert weather.requests == []


def test_batches_100_cells_per_request() -> None:
    weather = FakeWeather()
    WeatherLookup(weather).forecasts(grid(250))
    assert [len(request) for request in weather.requests] == [100, 100, 50]


def test_cache_hit_makes_no_request() -> None:
    weather = FakeWeather()
    lookup = WeatherLookup(weather)
    first = lookup.forecasts(grid(3))
    assert lookup.forecasts(grid(3)) == first
    assert len(weather.requests) == 1


def test_only_missing_cells_are_requested() -> None:
    weather = FakeWeather()
    lookup = WeatherLookup(weather)
    lookup.forecasts(grid(2))
    lookup.forecasts(grid(3))
    assert weather.requests[1] == [snap_to_cell(grid(3)[2])]


def test_long_trip_stays_in_the_default_cache() -> None:
    # A coast-to-coast trip needs far more than Django's default 300 local cache entries.
    weather = FakeWeather()
    lookup = WeatherLookup(weather)
    lookup.forecasts(grid(1000))
    requests_after_first_trip = len(weather.requests)
    lookup.forecasts(grid(1000))
    assert len(weather.requests) == requests_after_first_trip


def test_cache_entries_expire_after_one_hour(monkeypatch: pytest.MonkeyPatch) -> None:
    weather = FakeWeather()
    lookup = WeatherLookup(weather)
    now = time.time()
    lookup.forecasts(grid(1))

    monkeypatch.setattr(time, "time", lambda: now + 3590)
    lookup.forecasts(grid(1))
    assert len(weather.requests) == 1

    monkeypatch.setattr(time, "time", lambda: now + 3610)
    lookup.forecasts(grid(1))
    assert len(weather.requests) == 2


def test_failed_batch_marks_only_its_cells_none() -> None:
    weather = FakeWeather([None, ProviderUnavailable("down"), None])
    positions = grid(250)
    result = WeatherLookup(weather).forecasts(positions)
    assert sum(result[position] is None for position in positions[100:200]) == 100
    assert all(result[position] is not None for position in positions[:100] + positions[200:])


def test_failed_batch_is_not_cached() -> None:
    weather = FakeWeather([ProviderUnavailable("down"), None, None])
    lookup = WeatherLookup(weather)
    lookup_positions = grid(101)
    lookup.forecasts(lookup_positions)
    result = lookup.forecasts(lookup_positions)
    assert all(forecast_ is not None for forecast_ in result.values())


def test_total_outage_raises_unavailable() -> None:
    weather = FakeWeather([ProviderUnavailable("down"), ProviderUnavailable("down")])
    with pytest.raises(ProviderUnavailable):
        WeatherLookup(weather).forecasts(grid(150))


def test_total_rate_limit_raises_rate_limited() -> None:
    weather = FakeWeather([ProviderRateLimited("slow")])
    with pytest.raises(ProviderRateLimited):
        WeatherLookup(weather).forecasts(grid(1))


def test_outage_with_cached_cells_is_partial_not_total() -> None:
    weather = FakeWeather([None, ProviderUnavailable("down")])
    lookup = WeatherLookup(weather)
    lookup.forecasts(grid(1))
    result = lookup.forecasts(grid(2))
    assert result[grid(2)[0]] is not None
    assert result[grid(2)[1]] is None


def test_rate_limit_stops_further_batches() -> None:
    weather = FakeWeather([None, ProviderRateLimited("slow")])
    result = WeatherLookup(weather).forecasts(grid(250))
    assert len(weather.requests) == 2
    assert sum(value is None for value in result.values()) == 150


def minute_limit() -> ProviderRateLimited:
    return ProviderRateLimited("slow", retry_after_seconds=60)


def test_minute_limit_waits_once_and_finishes_every_cell() -> None:
    weather = FakeWeather([None, minute_limit(), None, None])
    naps: list[float] = []
    result = WeatherLookup(weather, sleep=naps.append).forecasts(grid(250))
    assert naps == [61]
    assert [len(request) for request in weather.requests] == [100, 100, 100, 50]
    assert all(value is not None for value in result.values())


def test_second_minute_limit_stops_without_another_wait() -> None:
    weather = FakeWeather([None, minute_limit(), minute_limit()])
    naps: list[float] = []
    result = WeatherLookup(weather, sleep=naps.append).forecasts(grid(250))
    assert naps == [61]
    assert len(weather.requests) == 3
    assert sum(value is None for value in result.values()) == 150


def test_minute_limit_on_every_attempt_raises() -> None:
    weather = FakeWeather([minute_limit(), minute_limit()])
    with pytest.raises(ProviderRateLimited):
        WeatherLookup(weather, sleep=lambda _: None).forecasts(grid(1))


def test_longer_limit_does_not_wait() -> None:
    weather = FakeWeather([None, ProviderRateLimited("daily limit")])
    naps: list[float] = []
    WeatherLookup(weather, sleep=naps.append).forecasts(grid(250))
    assert naps == []
    assert len(weather.requests) == 2
