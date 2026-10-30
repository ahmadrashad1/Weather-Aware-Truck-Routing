from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import accumulate, pairwise

from routing.services.geometry import LatLon, haversine_miles

ALLOWED_INTERVALS_MILES = (10, 25, 50)
MILE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class Checkpoint:
    mile: float
    position: LatLon
    represented_miles: float
    start_mile: float
    end_mile: float


def generate_checkpoints(
    geometry: Sequence[LatLon], total_miles: float, interval_miles: int
) -> list[Checkpoint]:
    """Place checkpoints at the origin, every interval, and the destination.

    Each one represents the stretch between the midpoints with its neighbours, so the represented
    miles sum to the route length. Geometry length rarely equals the provider's reported length,
    so geometry distances are scaled to `total_miles`.
    """
    if interval_miles not in ALLOWED_INTERVALS_MILES:
        raise ValueError(f"Interval must be one of {ALLOWED_INTERVALS_MILES}, got {interval_miles}")
    if total_miles <= 0:
        raise ValueError(f"Route length must be positive, got {total_miles}")
    if len(geometry) < 2:
        raise ValueError("Route geometry needs at least two points")

    cumulative = _scaled_cumulative_miles(geometry, total_miles)
    marks = _checkpoint_miles(total_miles, interval_miles)
    boundaries = [0.0, *((a + b) / 2 for a, b in pairwise(marks)), total_miles]
    return [
        Checkpoint(
            mile=mile,
            position=_position_at(mile, geometry, cumulative),
            represented_miles=end - start,
            start_mile=start,
            end_mile=end,
        )
        for mile, (start, end) in zip(marks, pairwise(boundaries), strict=True)
    ]


def _scaled_cumulative_miles(geometry: Sequence[LatLon], total_miles: float) -> list[float]:
    legs = [haversine_miles(a, b) for a, b in pairwise(geometry)]
    geometry_miles = sum(legs)
    if geometry_miles == 0:
        raise ValueError("Route geometry has no length")
    scale = total_miles / geometry_miles
    return [0.0, *accumulate(leg * scale for leg in legs)]


def _checkpoint_miles(total_miles: float, interval_miles: int) -> list[float]:
    count = int((total_miles - MILE_TOLERANCE) // interval_miles)
    return [float(step * interval_miles) for step in range(count + 1)] + [float(total_miles)]


def _position_at(mile: float, geometry: Sequence[LatLon], cumulative: Sequence[float]) -> LatLon:
    if mile <= 0:
        return geometry[0]
    if mile >= cumulative[-1]:
        return geometry[-1]
    end = bisect_left(cumulative, mile)
    fraction = (mile - cumulative[end - 1]) / (cumulative[end] - cumulative[end - 1])
    (lat_a, lon_a), (lat_b, lon_b) = geometry[end - 1], geometry[end]
    return (lat_a + (lat_b - lat_a) * fraction, lon_a + (lon_b - lon_a) * fraction)
