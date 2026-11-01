from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import httpx

from routing.providers.base import HourlyForecast
from routing.providers.errors import ProviderUnavailable
from routing.providers.http import (
    DEFAULT_RETRY_DELAY_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    get_with_retries,
)
from routing.services.geometry import LatLon

FREE_URL = "https://api.open-meteo.com/v1/forecast"
PAID_URL = "https://customer-api.open-meteo.com/v1/forecast"
MAX_CELLS_PER_REQUEST = 100
FORECAST_DAYS = 16
# Each location counts as one call, so the free tier allows 600 cells per minute (measured; the
# docs do not say). The hourly limit is 5,000 and the daily limit 10,000.
MINUTE_LIMIT_RESET_SECONDS = 60

MM_PER_INCH = 25.4
CM_PER_INCH = 2.54
RATE_DECIMALS = 6


class OpenMeteoProvider:
    def __init__(
        self,
        api_key: str = "",
        client: httpx.Client | None = None,
        retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
        self._retry_delay_seconds = retry_delay_seconds

    def hourly(self, cells: Sequence[LatLon]) -> dict[LatLon, HourlyForecast]:
        """Fetch hourly forecasts. Send at most MAX_CELLS_PER_REQUEST cells per call.

        Units stay in mm and cm and are converted here, because the docs do not say whether
        `precipitation_unit` also changes `snowfall`.
        """
        if not cells:
            return {}
        params: dict[str, str | int] = {
            "latitude": ",".join(str(lat) for lat, _ in cells),
            "longitude": ",".join(str(lon) for _, lon in cells),
            "hourly": "wind_speed_10m,rain,showers,snowfall",
            "wind_speed_unit": "mph",
            "timezone": "GMT",
            "timeformat": "unixtime",
            "forecast_days": FORECAST_DAYS,
        }
        if self._api_key:
            params["apikey"] = self._api_key
        response = get_with_retries(
            self._client,
            PAID_URL if self._api_key else FREE_URL,
            params,
            "Open-Meteo",
            self._retry_delay_seconds,
            read_retry_after=_minute_limit_retry_after,
        )
        if response.status_code >= 400:
            raise ProviderUnavailable(f"Open-Meteo returned HTTP {response.status_code}")
        try:
            body = response.json()
            # A single location comes back as an object rather than a one-item list.
            locations = body if isinstance(body, list) else [body]
            if len(locations) != len(cells):
                raise ValueError("Open-Meteo returned the wrong number of locations")
            return {
                cell: _parse_forecast(location)
                for cell, location in zip(cells, locations, strict=True)
            }
        except (KeyError, TypeError, ValueError):
            raise ProviderUnavailable("Open-Meteo returned an unreadable forecast") from None


def _minute_limit_retry_after(response: httpx.Response) -> float | None:
    """Only the per-minute limit clears soon. Waiting would not help the hourly or daily ones."""
    try:
        reason = response.json()["reason"]
    except (ValueError, KeyError, TypeError):
        return None
    return MINUTE_LIMIT_RESET_SECONDS if "Minutely" in str(reason) else None


def _parse_forecast(location: Mapping[str, Any]) -> HourlyForecast:
    hourly = location["hourly"]
    times = hourly["time"]
    wind = hourly["wind_speed_10m"]
    rain = hourly["rain"]
    showers = hourly["showers"]
    snowfall = hourly["snowfall"]
    if not len(times) == len(wind) == len(rain) == len(showers) == len(snowfall):
        raise ValueError("Open-Meteo hourly arrays differ in length")
    return HourlyForecast(
        times_utc=tuple(datetime.fromtimestamp(time, UTC) for time in times),
        wind_mph=tuple(wind),
        # `precipitation` would include snow, and `rain` alone would miss convective showers.
        # Values are sums over the preceding hour, so they are already rates per hour.
        rain_in_hr=tuple(
            # Rounded so float error can't push exactly 1 in/hr over the No Travel limit.
            None if a is None or b is None else round((a + b) / MM_PER_INCH, RATE_DECIMALS)
            for a, b in zip(rain, showers, strict=True)
        ),
        snow_in_hr=tuple(
            None if value is None else round(value / CM_PER_INCH, RATE_DECIMALS)
            for value in snowfall
        ),
    )
