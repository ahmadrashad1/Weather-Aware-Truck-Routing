import time
from bisect import bisect_left
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import time as day_time
from itertools import batched
from typing import Protocol

from django.core.cache import cache

from config.observability import count, log_event
from routing.domain import WeatherSample
from routing.providers.base import HourlyForecast, WeatherProvider
from routing.providers.errors import ProviderError, ProviderRateLimited, ProviderUnavailable
from routing.providers.open_meteo import (
    FORECAST_DAYS,
    MAX_CELLS_PER_REQUEST,
    SHORT_FORECAST_DAYS,
)
from routing.services.geometry import LatLon
from routing.services.weather_budget import Purpose, WeatherBudget, WeatherBudgetExceeded

CELLS_PER_DEGREE = 20
CACHE_SECONDS = 60 * 60
RATE_LIMIT_WAIT_MARGIN_SECONDS = 1
# One more request can start just before this and take its 30-second timeout, which still ends
# within nginx's 170-second limit. A slow provider can't then hold a thread after nginx gives up.
DEADLINE_SECONDS = 120
# Precipitation reads the next whole hour, so a forecast must run an hour past the moment needed.
LAST_HOUR_MARGIN = timedelta(hours=2)


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


class WeatherSource(Protocol):
    def forecasts(
        self, positions: Sequence[LatLon], needed_until: datetime | None = None
    ) -> dict[LatLon, HourlyForecast | None]: ...


class WeatherLookup:
    def __init__(
        self,
        provider: WeatherProvider,
        sleep: Callable[[float], None] = time.sleep,
        budget: WeatherBudget | None = None,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._today = today
        self._provider = provider
        self._sleep = sleep
        self._budget = budget
        self._clock = clock

    def for_request(
        self, client: str, purpose: Purpose, deadline_seconds: float = DEADLINE_SECONDS
    ) -> "RequestWeather":
        """Bind one request's budget and time limit, with the time limit starting now."""
        return RequestWeather(self, client, purpose, self._clock() + deadline_seconds)

    def forecasts(
        self,
        positions: Sequence[LatLon],
        needed_until: datetime | None = None,
        scope: "RequestWeather | None" = None,
    ) -> dict[LatLon, HourlyForecast | None]:
        """Return each position's forecast, or None where it could not be fetched.

        `needed_until` is the latest moment the caller will read, which allows a shorter forecast.

        Raises only when no position has a forecast at all, because partial results are still
        useful: the affected checkpoints become unknown rather than failing the whole trip. Being
        over budget always raises, so a trip is never ranked on weather it chose not to fetch.
        """
        cell_by_position = {position: snap_to_cell(position) for position in positions}
        cells = list(dict.fromkeys(cell_by_position.values()))
        by_cell, error = self._load(cells, needed_until, scope)
        if cells and not by_cell and error:
            raise error
        return {position: by_cell.get(cell) for position, cell in cell_by_position.items()}

    def _load(
        self, cells: list[LatLon], needed_until: datetime | None, scope: "RequestWeather | None"
    ) -> tuple[dict[LatLon, HourlyForecast], ProviderError | None]:
        days = self._days_for(needed_until)
        full_keys = {cell: _full_key(cell) for cell in cells}
        # A short forecast starts at today's midnight, so it isn't reused on another day, where
        # it would end too soon. A full forecast has days to spare and serves either need.
        keys = full_keys
        lookups = [*full_keys.values()]
        if days == SHORT_FORECAST_DAYS:
            date = self._today().date().isoformat()
            keys = {cell: f"weather:short:{date}:{cell[0]:.2f}:{cell[1]:.2f}" for cell in cells}
            lookups += keys.values()
        cached = cache.get_many(lookups)
        found = {
            cell: cached.get(full_keys[cell]) or cached[keys[cell]]
            for cell in cells
            if full_keys[cell] in cached or keys[cell] in cached
        }
        missing = [cell for cell in cells if cell not in found]
        count("weather_cells_cached", len(found))
        count("weather_cells_fetched", 0)
        receipt = self._charge(len(missing), scope) if scope else ()
        try:
            return self._fetch(missing, keys, found, scope, days)
        finally:
            # Only fetched locations count, so an outage can't lock anyone out once it's over.
            if self._budget and receipt:
                self._budget.refund(receipt, sum(cell not in found for cell in missing))

    def _fetch(
        self,
        missing: list[LatLon],
        keys: dict[LatLon, str],
        found: dict[LatLon, HourlyForecast],
        scope: "RequestWeather | None",
        days: int,
    ) -> tuple[dict[LatLon, HourlyForecast], ProviderError | None]:
        error: ProviderError | None = None
        may_wait = True
        failed_last_batch = False
        for batch in batched(missing, MAX_CELLS_PER_REQUEST, strict=False):
            if scope and self._clock() >= scope.deadline:
                log_event("weather_deadline_reached")
                return found, error or ProviderUnavailable("Weather took too long to load")
            while True:
                try:
                    fetched = self._provider.hourly(batch, days)
                except ProviderRateLimited as rate_limited:
                    # Giving up here would leave later routes unknown and rank them lower because
                    # of request order rather than weather, so wait out a short limit once.
                    wait = rate_limited.retry_after_seconds
                    if wait is None or not may_wait or not self._can_wait(wait, scope):
                        return found, rate_limited
                    may_wait = False
                    log_event("weather_rate_limit_wait", seconds=wait)
                    self._sleep(wait + RATE_LIMIT_WAIT_MARGIN_SECONDS)
                    continue
                except ProviderUnavailable as unavailable:
                    # One blip shouldn't lose the rest of a trip, but two suggest an outage, and
                    # each failure can take a full timeout.
                    if failed_last_batch:
                        return found, unavailable
                    error = unavailable
                    failed_last_batch = True
                    break
                failed_last_batch = False
                found.update(fetched)
                count("weather_cells_fetched", len(fetched))
                cache.set_many({keys[cell]: fetched[cell] for cell in fetched}, CACHE_SECONDS)
                break
        return found, error

    def _days_for(self, needed_until: datetime | None) -> int:
        if needed_until is None:
            return FORECAST_DAYS
        today = datetime.combine(self._today().date(), day_time.min, UTC)
        short_ends = today + timedelta(days=SHORT_FORECAST_DAYS) - LAST_HOUR_MARGIN
        return SHORT_FORECAST_DAYS if needed_until <= short_ends else FORECAST_DAYS

    def _charge(self, locations: int, scope: "RequestWeather") -> tuple[str, ...]:
        if not self._budget:
            return ()
        try:
            return self._budget.spend(locations, scope.client, scope.purpose)
        except WeatherBudgetExceeded as refused:
            log_event(
                "weather_budget_refused",
                window=refused.window,
                purpose=refused.purpose.value,
                locations=locations,
            )
            raise

    def _can_wait(self, seconds: float, scope: "RequestWeather | None") -> bool:
        if not scope:
            return True
        return self._clock() + seconds + RATE_LIMIT_WAIT_MARGIN_SECONDS < scope.deadline


@dataclass(frozen=True)
class RequestWeather:
    """A lookup bound to one request's client, purpose and deadline."""

    lookup: WeatherLookup
    client: str
    purpose: Purpose
    deadline: float

    def forecasts(
        self, positions: Sequence[LatLon], needed_until: datetime | None = None
    ) -> dict[LatLon, HourlyForecast | None]:
        return self.lookup.forecasts(positions, needed_until, self)


def _full_key(cell: LatLon) -> str:
    return f"weather:{cell[0]:.2f}:{cell[1]:.2f}"
