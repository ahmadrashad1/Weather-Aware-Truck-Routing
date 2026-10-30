from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Any

from routing.providers.base import HourlyForecast, ProviderRoute
from routing.providers.errors import NoRouteFound
from routing.services.eta_calculator import TravelProfile
from routing.services.geometry import LatLon

MILES_PER_DEGREE_LATITUDE = 69.09


def straight_route(miles: float, seconds: int, lon: float = -100.0) -> ProviderRoute:
    """A due-north route, so routes at different longitudes never count as duplicates."""
    return ProviderRoute(
        geometry=((30.0, lon), (30.0 + miles / MILES_PER_DEGREE_LATITUDE, lon)),
        total_miles=miles,
        duration_seconds=seconds,
        profile=TravelProfile(((0, 0), (miles, seconds))),
    )


class FakeRouting:
    def __init__(self, routes: Sequence[ProviderRoute] = (), error: Exception | None = None):
        self.routes_to_return = list(routes)
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def routes(
        self,
        origin: LatLon,
        destination: LatLon,
        departure: datetime,
        load_lb: float,
        via: LatLon | None = None,
        max_alternatives: int = 2,
    ) -> list[ProviderRoute]:
        self.calls.append({"departure": departure, "load_lb": load_lb, "via": via})
        if self.error:
            raise self.error
        if via is not None:
            raise NoRouteFound("no detour in this fake")
        return self.routes_to_return


class FakeWeather:
    """Answers each cell's hourly forecast from a function of position and time."""

    def __init__(
        self,
        start: datetime,
        wind_at: Callable[[LatLon, datetime], float | None] = lambda cell, at: 5.0,
        rain_at: Callable[[LatLon, datetime], float | None] = lambda cell, at: 0.0,
        hours: int = 120,
        error: Exception | None = None,
        failures: Sequence[Exception] = (),
    ) -> None:
        self.start = start
        self.wind_at = wind_at
        self.rain_at = rain_at
        self.hours = hours
        self.error = error
        self.failures = list(failures)
        self.requests: list[list[LatLon]] = []

    def hourly(self, cells: Sequence[LatLon]) -> dict[LatLon, HourlyForecast]:
        self.requests.append(list(cells))
        if self.error:
            raise self.error
        if self.failures:
            raise self.failures.pop(0)
        times = tuple(self.start + timedelta(hours=hour) for hour in range(self.hours))
        return {
            cell: HourlyForecast(
                times_utc=times,
                wind_mph=tuple(self.wind_at(cell, at) for at in times),
                rain_in_hr=tuple(self.rain_at(cell, at) for at in times),
                snow_in_hr=tuple(0.0 for _ in times),
            )
            for cell in cells
        }
