from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from routing.services.geometry import LatLon
from routing.services.risk_engine import assess
from routing.services.weather_lookup import WeatherSource, sample_at

# The forecast slider runs from hour 0 at departure to hour 48 inclusive.
HEATMAP_FRAMES = 49


@dataclass(frozen=True)
class Heatmap:
    departure_at: datetime
    points: tuple[LatLon, ...]
    # One tuple per point: the risk level at each hour, or None where weather is unavailable.
    risk: tuple[tuple[int | None, ...], ...]


def build_heatmap(
    points: Sequence[LatLon], departure: datetime, load_lb: float, weather: WeatherSource
) -> Heatmap:
    forecasts = weather.forecasts(points)
    start = departure.astimezone(UTC)
    frames = [start + timedelta(hours=hour) for hour in range(HEATMAP_FRAMES)]

    risk = []
    for point in points:
        forecast = forecasts[point]
        levels: list[int | None] = []
        for frame in frames:
            sample = sample_at(forecast, frame) if forecast else None
            levels.append(int(assess(sample, load_lb).level) if sample else None)
        risk.append(tuple(levels))
    return Heatmap(departure_at=start, points=tuple(points), risk=tuple(risk))
