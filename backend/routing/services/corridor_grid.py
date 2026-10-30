import math
from collections.abc import Sequence
from itertools import pairwise

from routing.services.geometry import (
    MILES_PER_DEGREE_LATITUDE,
    LatLon,
    haversine_miles,
    sample_along,
)

# Rows of points to try across the corridor, widest first. A long trip falls back to fewer rows,
# because thinning along the route instead would leave gaps between checkpoints of weather.
ROW_OPTIONS = (5, 3)
# How much farther apart points may be along the route than across it before dropping a row.
MAX_ALONG_TO_ACROSS = 1.5
# Points closer together than this share of the spacing count as the same place.
DEDUPE_SHARE_OF_SPACING = 0.6
SPACING_GROWTH = 1.1


def corridor_points(
    routes: Sequence[Sequence[LatLon]], half_width_miles: float = 25, max_points: int = 300
) -> list[LatLon]:
    """Place heatmap sample points along each route and across its corridor, within the cap."""
    if not routes:
        return []
    total_miles = sum(
        haversine_miles(start, end) for route in routes for start, end in pairwise(route)
    )
    rows, spacing = _choose_layout(total_miles, half_width_miles, max_points)
    points = _lay_out(routes, half_width_miles, rows, spacing)
    # Route ends add a few points beyond the estimate, so widen until they fit.
    while len(points) > max_points and spacing < total_miles:
        spacing *= SPACING_GROWTH
        points = _lay_out(routes, half_width_miles, rows, spacing)
    return points[:max_points]


def _choose_layout(total_miles: float, half_width: float, max_points: int) -> tuple[int, float]:
    for rows in ROW_OPTIONS:
        across = half_width / ((rows - 1) / 2)
        along = total_miles * rows / max_points
        if along <= across * MAX_ALONG_TO_ACROSS:
            return rows, max(along, across)
    return 1, max(total_miles / max_points, half_width)


def _lay_out(
    routes: Sequence[Sequence[LatLon]], half_width: float, rows: int, spacing: float
) -> list[LatLon]:
    offsets = (
        [half_width * (2 * row / (rows - 1) - 1) for row in range(rows)] if rows > 1 else [0.0]
    )
    points: dict[tuple[int, int], LatLon] = {}
    for route in routes:
        samples = sample_along(route, spacing)
        for index, sample in enumerate(samples):
            before = samples[max(index - 1, 0)]
            after = samples[min(index + 1, len(samples) - 1)]
            for offset in offsets:
                point = _offset_sideways(sample, before, after, offset)
                points.setdefault(_dedupe_key(point, spacing), point)
    return list(points.values())


def _offset_sideways(sample: LatLon, before: LatLon, after: LatLon, miles: float) -> LatLon:
    if miles == 0:
        return sample
    miles_per_degree_longitude = MILES_PER_DEGREE_LATITUDE * math.cos(math.radians(sample[0]))
    east = (after[1] - before[1]) * miles_per_degree_longitude
    north = (after[0] - before[0]) * MILES_PER_DEGREE_LATITUDE
    length = math.hypot(east, north)
    if length == 0:
        return sample
    return (
        sample[0] + (east / length) * miles / MILES_PER_DEGREE_LATITUDE,
        sample[1] - (north / length) * miles / miles_per_degree_longitude,
    )


def _dedupe_key(point: LatLon, spacing: float) -> tuple[int, int]:
    cell = spacing * DEDUPE_SHARE_OF_SPACING
    miles_per_degree_longitude = MILES_PER_DEGREE_LATITUDE * math.cos(math.radians(point[0]))
    return (
        round(point[0] * MILES_PER_DEGREE_LATITUDE / cell),
        round(point[1] * miles_per_degree_longitude / cell),
    )
