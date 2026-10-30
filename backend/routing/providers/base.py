from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from routing.services.eta_calculator import TravelProfile
from routing.services.geometry import LatLon


@dataclass(frozen=True)
class ProviderRoute:
    geometry: tuple[LatLon, ...]
    total_miles: float
    duration_seconds: int
    profile: TravelProfile


@dataclass(frozen=True)
class Place:
    label: str
    position: LatLon


@dataclass(frozen=True)
class HourlyForecast:
    times_utc: tuple[datetime, ...]
    wind_mph: tuple[float | None, ...]
    rain_in_hr: tuple[float | None, ...]
    snow_in_hr: tuple[float | None, ...]


class RoutingProvider(Protocol):
    def routes(
        self,
        origin: LatLon,
        destination: LatLon,
        departure: datetime,
        load_lb: float,
        via: LatLon | None = None,
        max_alternatives: int = 2,
    ) -> list[ProviderRoute]: ...


class GeocodingProvider(Protocol):
    def search(self, query: str) -> list[Place]: ...


class WeatherProvider(Protocol):
    def hourly(self, cells: Sequence[LatLon]) -> dict[LatLon, HourlyForecast]: ...
