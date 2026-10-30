from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise


@dataclass(frozen=True)
class TravelProfile:
    """(mile, elapsed_seconds) points from (0, 0) to (total_miles, total_seconds)."""

    points: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("A travel profile needs at least two points")
        if self.points[0] != (0, 0):
            raise ValueError("A travel profile must start at mile 0, second 0")
        for (mile_a, seconds_a), (mile_b, seconds_b) in pairwise(self.points):
            if mile_b <= mile_a or seconds_b <= seconds_a:
                raise ValueError("Travel profile points must strictly increase")


def eta_at(mile: float, departure: datetime, profile: TravelProfile) -> datetime:
    """Return the arrival instant in UTC.

    Adding a timedelta to an aware local datetime does wall-clock arithmetic and goes wrong across
    a DST change, so the elapsed time is added in UTC.
    """
    if departure.utcoffset() is None:
        raise ValueError("Departure must include a UTC offset")
    points = profile.points
    if not 0 <= mile <= points[-1][0]:
        raise ValueError(f"Mile {mile} is outside the route")
    return departure.astimezone(UTC) + timedelta(seconds=_elapsed_seconds(mile, points))


def _elapsed_seconds(mile: float, points: tuple[tuple[float, float], ...]) -> float:
    if mile == 0:
        return 0.0
    end = bisect_left(points, mile, key=lambda point: point[0])
    (mile_a, seconds_a), (mile_b, seconds_b) = points[end - 1], points[end]
    return seconds_a + (seconds_b - seconds_a) * (mile - mile_a) / (mile_b - mile_a)
