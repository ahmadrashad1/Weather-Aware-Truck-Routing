import math
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import groupby

from routing.domain import RiskLevel
from routing.services.checkpoint_generator import position_at, scaled_cumulative_miles
from routing.services.geometry import LatLon
from routing.services.route_scorer import AssessedCheckpoint

# About 180 feet, which is not visible at the zoom needed to see a whole trip. A long route has
# nearly 40,000 points, which is too many to send to a browser.
DISPLAY_TOLERANCE_DEGREES = 0.0005


@dataclass(frozen=True)
class RouteSegment:
    risk: RiskLevel | None
    from_mile: float
    to_mile: float
    coordinates: tuple[LatLon, ...]


def simplify_indices(geometry: Sequence[LatLon], tolerance_degrees: float) -> list[int]:
    """Return the indices Douglas-Peucker keeps. Iterative, because routes are very long."""
    last = len(geometry) - 1
    keep = {0, last}
    pending = [(0, last)]
    while pending:
        start, end = pending.pop()
        farthest, distance = _farthest_point(geometry, start, end)
        if distance > tolerance_degrees:
            keep.add(farthest)
            pending.append((start, farthest))
            pending.append((farthest, end))
    return sorted(keep)


def display_indices(geometry: Sequence[LatLon]) -> list[int]:
    return simplify_indices(geometry, DISPLAY_TOLERANCE_DEGREES)


def build_segments(
    geometry: Sequence[LatLon],
    total_miles: float,
    checkpoints: Sequence[AssessedCheckpoint],
    cumulative: Sequence[float] | None = None,
    kept: Sequence[int] | None = None,
) -> list[RouteSegment]:
    """Draw the route in stretches of equal risk, merging adjacent checkpoints that agree.

    `cumulative` and `kept` save repeating work on a long route if the caller already has them.
    """
    if cumulative is None:
        cumulative = scaled_cumulative_miles(geometry, total_miles)
    if kept is None:
        kept = display_indices(geometry)
    kept_miles = [cumulative[i] for i in kept]

    segments = []
    for risk, group in groupby(checkpoints, key=_risk_of):
        stretch = list(group)
        start = stretch[0].checkpoint.start_mile
        end = stretch[-1].checkpoint.end_mile
        inside = kept[bisect_right(kept_miles, start) : bisect_left(kept_miles, end)]
        segments.append(
            RouteSegment(
                risk=risk,
                from_mile=start,
                to_mile=end,
                coordinates=(
                    position_at(start, geometry, cumulative),
                    *(geometry[i] for i in inside),
                    position_at(end, geometry, cumulative),
                ),
            )
        )
    return segments


def _risk_of(checkpoint: AssessedCheckpoint) -> RiskLevel | None:
    return checkpoint.assessment.level if checkpoint.assessment else None


def _farthest_point(geometry: Sequence[LatLon], start: int, end: int) -> tuple[int, float]:
    lat_a, lon_a = geometry[start]
    lat_b, lon_b = geometry[end]
    # A degree of longitude is shorter than a degree of latitude away from the equator.
    scale = math.cos(math.radians(lat_a))
    delta_x = (lon_b - lon_a) * scale
    delta_y = lat_b - lat_a
    length_squared = delta_x * delta_x + delta_y * delta_y

    farthest = start
    largest = 0.0
    for index in range(start + 1, end):
        lat, lon = geometry[index]
        x = (lon - lon_a) * scale
        y = lat - lat_a
        if length_squared == 0:
            distance = x * x + y * y
        else:
            along = max(0.0, min(1.0, (x * delta_x + y * delta_y) / length_squared))
            distance = (x - along * delta_x) ** 2 + (y - along * delta_y) ** 2
        if distance > largest:
            farthest = index
            largest = distance
    return farthest, math.sqrt(largest)
