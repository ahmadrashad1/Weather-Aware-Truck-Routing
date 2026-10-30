import time
from bisect import bisect_left
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from itertools import batched

from django.core.cache import cache

from routing.domain import WeatherSample
from routing.providers.base import HourlyForecast, WeatherProvider
from routing.providers.errors import ProviderError, ProviderRateLimited, ProviderUnavailable
from routing.providers.open_meteo import MAX_CELLS_PER_REQUEST
from routing.services.geometry import LatLon

CELLS_PER_DEGREE = 20
CACHE_SECONDS = 60 * 60
RATE_LIMIT_WAIT_MARGIN_SECONDS = 1


def snap_to_cell(position: LatLon) -> LatLon:
    """Round to a 0.05 degree grid (about 3.5 miles), so nearby points share a forecast."""
    lat, lon = position
    return (
        round(round(lat * CELLS_PER_DEGREE) / CELLS_PER_DEGREE, 2),
        round(round(lon * CELLS_PER_DEGREE) / CELLS_PER_DEGREE, 2),
    )


def sample_at(forecast: HourlyForecast, at: datetime) -> WeatherSample | None:
    """Read the weather at an instant, or None if the forecast cannot answer.

    Rain and snow are sums over the preceding hour, so the next whole hour's value covers `at`.
    Wind is instantaneous, so it is interpolated between the surrounding hours.
    """
    if at.utcoffset() is None:
        raise ValueError("Time must include a UTC offset")
    moment = at.astimezone(UTC)
    times = forecast.times_utc
    if not times or moment < times[0] or moment > times[-1]:
        return None
    covering = bisect_left(times, moment)
    wind = _wind_at(forecast, moment, covering)
    rain = forecast.rain_in_hr[covering]
    snow = forecast.snow_in_hr[covering]
    if wind is None or rain is None or snow is None:
        return None
    return WeatherSample(wind_mph=wind, rain_in_hr=rain, snow_in_hr=snow)


def _wind_at(forecast: HourlyForecast, moment: datetime, covering: int) -> float | None:
    after = forecast.wind_mph[covering]
    if forecast.times_utc[covering] == moment:
        return after
    before = forecast.wind_mph[covering - 1]
    if before is None or after is None:
        return None
    start = forecast.times_utc[covering - 1]
    span = forecast.times_utc[covering] - start
    return before + (after - before) * ((moment - start) / span)


class WeatherLookup:
    def __init__(
        self, provider: WeatherProvider, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self._provider = provider
        self._sleep = sleep

    def forecasts(self, positions: Sequence[LatLon]) -> dict[LatLon, HourlyForecast | None]:
        """Return each position's forecast, or None where it could not be fetched.

        Raises only when no position has a forecast at all, because partial results are still
        useful: the affected checkpoints become unknown rather than failing the whole trip.
        """
        cell_by_position = {position: snap_to_cell(position) for position in positions}
        cells = list(dict.fromkeys(cell_by_position.values()))
        by_cell, error = self._load(cells)
        if cells and not by_cell and error:
            raise error
        return {position: by_cell.get(cell) for position, cell in cell_by_position.items()}

    def _load(
        self, cells: list[LatLon]
    ) -> tuple[dict[LatLon, HourlyForecast], ProviderError | None]:
        keys = {cell: f"weather:{cell[0]:.2f}:{cell[1]:.2f}" for cell in cells}
        cached = cache.get_many(keys.values())
        found = {cell: cached[key] for cell, key in keys.items() if key in cached}
        missing = [cell for cell in cells if cell not in found]

        error: ProviderError | None = None
        may_wait = True
        for batch in batched(missing, MAX_CELLS_PER_REQUEST, strict=False):
            while True:
                try:
                    fetched = self._provider.hourly(batch)
                except ProviderRateLimited as rate_limited:
                    # Giving up here would leave later routes unknown and rank them lower because
                    # of request order rather than weather, so wait out a short limit once.
                    if rate_limited.retry_after_seconds is None or not may_wait:
                        return found, rate_limited
                    may_wait = False
                    self._sleep(rate_limited.retry_after_seconds + RATE_LIMIT_WAIT_MARGIN_SECONDS)
                    continue
                except ProviderUnavailable as unavailable:
                    error = unavailable
                    break
                found.update(fetched)
                cache.set_many({keys[cell]: fetched[cell] for cell in fetched}, CACHE_SECONDS)
                break
        return found, error
