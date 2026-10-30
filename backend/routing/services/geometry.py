import math
from collections.abc import Sequence
from itertools import pairwise

LatLon = tuple[float, float]

EARTH_RADIUS_MILES = 3958.8
MILES_PER_DEGREE_LATITUDE = math.radians(EARTH_RADIUS_MILES)


def haversine_miles(a: LatLon, b: LatLon) -> float:
    lat_a, lon_a = map(math.radians, a)
    lat_b, lon_b = map(math.radians, b)
    half_chord = (
        math.sin((lat_b - lat_a) / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin((lon_b - lon_a) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(half_chord))


def sample_along(geometry: Sequence[LatLon], spacing_miles: float) -> list[LatLon]:
    """Return evenly spaced points along a route, including both ends."""
    samples = [geometry[0]]
    travelled = 0.0
    next_sample = spacing_miles
    for start, end in pairwise(geometry):
        leg = haversine_miles(start, end)
        while next_sample <= travelled + leg:
            fraction = (next_sample - travelled) / leg
            samples.append(
                (
                    start[0] + (end[0] - start[0]) * fraction,
                    start[1] + (end[1] - start[1]) * fraction,
                )
            )
            next_sample += spacing_miles
        travelled += leg
    samples.append(geometry[-1])
    return samples
