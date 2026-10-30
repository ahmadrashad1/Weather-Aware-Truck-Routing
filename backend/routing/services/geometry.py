import math

LatLon = tuple[float, float]

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(a: LatLon, b: LatLon) -> float:
    lat_a, lon_a = map(math.radians, a)
    lat_b, lon_b = map(math.radians, b)
    half_chord = (
        math.sin((lat_b - lat_a) / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin((lon_b - lon_a) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(half_chord))
