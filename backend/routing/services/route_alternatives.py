import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from routing.providers.base import ProviderRoute, RoutingProvider
from routing.providers.errors import NoRouteFound, ProviderRateLimited, ProviderUnavailable
from routing.services.geometry import MILES_PER_DEGREE_LATITUDE, LatLon, sample_along

TARGET_ROUTES = 3
DUPLICATE_OVERLAP = 0.9
VIA_OFFSET_FRACTION = 0.15
OVERLAP_SAMPLE_MILES = 0.1
# About 0.14 miles, so opposite carriageways of one highway count as the same road.
OVERLAP_CELL_DEGREES = 0.002


@dataclass(frozen=True)
class AlternativesResult:
    routes: list[ProviderRoute]
    warnings: list[str]


def get_three_routes(
    provider: RoutingProvider,
    origin: LatLon,
    destination: LatLon,
    departure: datetime,
    load_lb: float,
) -> AlternativesResult:
    """Return up to three distinct routes, forcing detours when the provider offers too few.

    A failure on the first request propagates. A failure while forcing detours keeps what was
    already found, because real routes with a warning are more useful than an error.
    """
    routes: list[ProviderRoute] = []
    for candidate in provider.routes(
        origin, destination, departure, load_lb, max_alternatives=TARGET_ROUTES - 1
    ):
        _keep_if_distinct(candidate, routes)
    del routes[TARGET_ROUTES:]

    for via in _via_points(routes[0], origin, destination):
        if len(routes) == TARGET_ROUTES:
            break
        try:
            for candidate in provider.routes(
                origin, destination, departure, load_lb, via=via, max_alternatives=0
            ):
                _keep_if_distinct(candidate, routes)
        except NoRouteFound:
            continue
        except (ProviderUnavailable, ProviderRateLimited):
            break

    warnings = []
    if len(routes) < TARGET_ROUTES:
        warnings.append(
            f"Only {len(routes)} distinct route(s) could be found between these locations."
        )
    return AlternativesResult(routes=routes, warnings=warnings)


def overlap_fraction(route: Sequence[LatLon], other: Sequence[LatLon]) -> float:
    """Return the share of `route`, by distance, that runs along `other`."""
    other_cells = {_cell(point) for point in sample_along(other, OVERLAP_SAMPLE_MILES)}
    samples = sample_along(route, OVERLAP_SAMPLE_MILES)
    shared = sum(1 for point in samples if _near_cells(_cell(point)) & other_cells)
    return shared / len(samples)


def _keep_if_distinct(candidate: ProviderRoute, routes: list[ProviderRoute]) -> None:
    if not any(_is_duplicate(candidate, kept) for kept in routes):
        routes.append(candidate)


def _is_duplicate(a: ProviderRoute, b: ProviderRoute) -> bool:
    # Both directions, so a short route is not a duplicate of a long detour that contains it.
    return (
        overlap_fraction(a.geometry, b.geometry) > DUPLICATE_OVERLAP
        and overlap_fraction(b.geometry, a.geometry) > DUPLICATE_OVERLAP
    )


def _cell(point: LatLon) -> tuple[int, int]:
    return (
        math.floor(point[0] / OVERLAP_CELL_DEGREES),
        math.floor(point[1] / OVERLAP_CELL_DEGREES),
    )


def _near_cells(cell: tuple[int, int]) -> set[tuple[int, int]]:
    return {(cell[0] + lat, cell[1] + lon) for lat in (-1, 0, 1) for lon in (-1, 0, 1)}


def _via_points(primary: ProviderRoute, origin: LatLon, destination: LatLon) -> list[LatLon]:
    """Offset the primary route's midpoint to each side of the origin-destination line."""
    samples = sample_along(primary.geometry, OVERLAP_SAMPLE_MILES)
    mid_lat, mid_lon = samples[len(samples) // 2]
    miles_per_degree_longitude = MILES_PER_DEGREE_LATITUDE * math.cos(math.radians(mid_lat))
    east = (destination[1] - origin[1]) * miles_per_degree_longitude
    north = (destination[0] - origin[0]) * MILES_PER_DEGREE_LATITUDE
    length = math.hypot(east, north)
    if length == 0:
        return []
    offset = primary.total_miles * VIA_OFFSET_FRACTION
    lat_step = (east / length) * offset / MILES_PER_DEGREE_LATITUDE
    lon_step = (-north / length) * offset / miles_per_degree_longitude
    return [(mid_lat + lat_step, mid_lon + lon_step), (mid_lat - lat_step, mid_lon - lon_step)]
