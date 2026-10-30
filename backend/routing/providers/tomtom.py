import logging
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from routing.providers.base import Place, ProviderRoute
from routing.providers.errors import NoRouteFound, ProviderRateLimited, ProviderUnavailable
from routing.services.eta_calculator import TravelProfile
from routing.services.geometry import LatLon

# TomTom takes its key in the query string, and httpx logs full request URLs at INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

ROUTING_URL = "https://api.tomtom.com/routing/1/calculateRoute"
SEARCH_URL = "https://api.tomtom.com/search/2/search"
TIMEOUT_SECONDS = 30
SERVER_ERROR_RETRIES = 2
SEARCH_RESULT_LIMIT = 5
# The assessment's rules are in miles, mph and pounds, so this serves US trips.
SEARCH_COUNTRIES = "US"
# Cities, streets and addresses. The geocode endpoint ranks street names above cities on partial
# input ("Dall" gives "Dall Lane"), which suits an address form but not a type-ahead.
SEARCH_INDEXES = "Geo,Str,PAD,Addr"
NO_ROUTE_CODES = frozenset({"NO_ROUTE_FOUND", "MAP_MATCHING_FAILURE"})

METERS_PER_MILE = 1609.344
KG_PER_LB = 0.45359237
# Road restrictions apply to gross weight, but the user enters cargo weight.
TARE_LB = 33_000
# About 65 mph. Without a cap TomTom assumes legal limits, which puts ETAs, and so the weather
# sampled at each checkpoint, too early.
TRUCK_MAX_SPEED_KMH = 105


class TomTomProvider:
    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        retry_delay_seconds: float = 0.5,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
        self._retry_delay_seconds = retry_delay_seconds

    def routes(
        self,
        origin: LatLon,
        destination: LatLon,
        departure: datetime,
        load_lb: float,
        via: LatLon | None = None,
        max_alternatives: int = 2,
    ) -> list[ProviderRoute]:
        stops = [origin, *([via] if via else []), destination]
        locations = ":".join(f"{lat},{lon}" for lat, lon in stops)
        response = self._get(
            f"{ROUTING_URL}/{locations}/json",
            {
                "travelMode": "truck",
                "vehicleCommercial": "true",
                "vehicleWeight": round((load_lb + TARE_LB) * KG_PER_LB),
                "vehicleMaxSpeed": TRUCK_MAX_SPEED_KMH,
                "maxAlternatives": max_alternatives,
                "departAt": departure.astimezone(UTC).isoformat(),
                "instructionsType": "coded",
                "routeRepresentation": "polyline",
            },
        )
        if _is_no_route(response):
            raise NoRouteFound("No truck route connects these locations")
        body = _json_body(response)
        try:
            routes = [_parse_route(route) for route in body["routes"]]
        except (KeyError, TypeError, ValueError, IndexError):
            raise ProviderUnavailable("TomTom returned an unreadable route") from None
        if not routes:
            raise NoRouteFound("No truck route connects these locations")
        return routes

    def search(self, query: str) -> list[Place]:
        cleaned = query.strip()
        if not cleaned:
            return []
        response = self._get(
            f"{SEARCH_URL}/{quote(cleaned, safe='')}.json",
            {
                "limit": SEARCH_RESULT_LIMIT,
                "typeahead": "true",
                "countrySet": SEARCH_COUNTRIES,
                "idxSet": SEARCH_INDEXES,
            },
        )
        body = _json_body(response)
        try:
            return [
                Place(
                    label=result["address"]["freeformAddress"],
                    position=(result["position"]["lat"], result["position"]["lon"]),
                )
                for result in body["results"]
            ]
        except (KeyError, TypeError):
            raise ProviderUnavailable("TomTom returned an unreadable place") from None

    def _get(self, url: str, params: Mapping[str, str | int]) -> httpx.Response:
        if not self._api_key:
            raise ProviderUnavailable("TomTom API key is not configured")
        for attempt in range(SERVER_ERROR_RETRIES + 1):
            if attempt:
                time.sleep(self._retry_delay_seconds)
            try:
                response = self._client.get(url, params={**params, "key": self._api_key})
            except httpx.HTTPError:
                raise ProviderUnavailable("TomTom could not be reached") from None
            if response.status_code < 500:
                break
        if response.status_code == 429:
            raise ProviderRateLimited("TomTom rate limit reached")
        if response.status_code >= 400 and not _is_no_route(response):
            raise ProviderUnavailable(f"TomTom returned HTTP {response.status_code}")
        return response


def _is_no_route(response: httpx.Response) -> bool:
    return response.status_code == 400 and _error_code(response) in NO_ROUTE_CODES


def _error_code(response: httpx.Response) -> str | None:
    try:
        code = response.json()["detailedError"]["code"]
    except (ValueError, KeyError, TypeError):
        return None
    return code if isinstance(code, str) else None


def _json_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        raise ProviderUnavailable("TomTom returned an unreadable response") from None


def _parse_route(route: Mapping[str, Any]) -> ProviderRoute:
    summary = route["summary"]
    meters = summary["lengthInMeters"]
    seconds = summary["travelTimeInSeconds"]
    if meters <= 0 or seconds <= 0:
        raise NoRouteFound("No truck route connects these locations")
    total_miles = meters / METERS_PER_MILE
    return ProviderRoute(
        geometry=_parse_geometry(route["legs"]),
        total_miles=total_miles,
        duration_seconds=seconds,
        profile=_parse_profile(route.get("guidance"), total_miles, seconds),
    )


def _parse_geometry(legs: list[Mapping[str, Any]]) -> tuple[LatLon, ...]:
    geometry: list[LatLon] = []
    for leg in legs:
        for point in leg["points"]:
            position = (point["latitude"], point["longitude"])
            if not geometry or geometry[-1] != position:
                geometry.append(position)
    if len(geometry) < 2:
        raise ValueError("Route geometry needs at least two points")
    return tuple(geometry)


def _parse_profile(
    guidance: Mapping[str, Any] | None, total_miles: float, total_seconds: int
) -> TravelProfile:
    """Follow TomTom's elapsed time at each instruction, so ETAs reflect the speed of each road.

    Without guidance this falls back to two points, which assumes a constant average speed.
    """
    points: list[tuple[float, float]] = [(0.0, 0.0)]
    for instruction in (guidance or {}).get("instructions", []):
        mile = instruction["routeOffsetInMeters"] / METERS_PER_MILE
        seconds = instruction["travelTimeInSeconds"]
        last_mile, last_seconds = points[-1]
        if last_mile < mile < total_miles and last_seconds < seconds < total_seconds:
            points.append((mile, float(seconds)))
    points.append((total_miles, float(total_seconds)))
    return TravelProfile(tuple(points))
