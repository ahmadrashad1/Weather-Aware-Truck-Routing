import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from routing.providers.errors import ProviderRateLimited, ProviderUnavailable
from routing.providers.open_meteo import OpenMeteoProvider

FIXTURE = Path(__file__).parent.parent / "fixtures" / "open_meteo" / "two_cells.json"
FREE_URL = "https://api.open-meteo.com/v1/forecast"
PAID_URL = "https://customer-api.open-meteo.com/v1/forecast"
DENVER = (39.75, -105.0)
DALLAS = (32.8, -96.8)
HOUR_0 = 1793318400
HOUR_1 = HOUR_0 + 3600


def location(
    wind: list[float | None] | None = None,
    rain: list[float | None] | None = None,
    showers: list[float | None] | None = None,
    snowfall: list[float | None] | None = None,
) -> dict[str, Any]:
    return {
        "latitude": 39.75,
        "longitude": -105.0,
        "hourly": {
            "time": [HOUR_0, HOUR_1],
            "wind_speed_10m": wind if wind is not None else [10.0, 20.0],
            "rain": rain if rain is not None else [0.0, 0.0],
            "showers": showers if showers is not None else [0.0, 0.0],
            "snowfall": snowfall if snowfall is not None else [0.0, 0.0],
        },
    }


@pytest.fixture
def provider() -> OpenMeteoProvider:
    return OpenMeteoProvider(retry_delay_seconds=0)


@pytest.fixture
def mocked() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def test_parses_real_response(provider: OpenMeteoProvider, mocked: respx.MockRouter) -> None:
    mocked.get(FREE_URL).mock(httpx.Response(200, json=json.loads(FIXTURE.read_text())))
    forecasts = provider.hourly([DENVER, DALLAS])
    assert set(forecasts) == {DENVER, DALLAS}
    forecast = forecasts[DENVER]
    assert len(forecast.times_utc) == 384
    assert forecast.times_utc[0] == datetime(2026, 10, 30, 0, tzinfo=UTC)
    assert forecast.times_utc[1] == datetime(2026, 10, 30, 1, tzinfo=UTC)
    assert len(forecast.wind_mph) == len(forecast.rain_in_hr) == len(forecast.snow_in_hr) == 384


def test_single_location_response_is_an_object(
    provider: OpenMeteoProvider, mocked: respx.MockRouter
) -> None:
    mocked.get(FREE_URL).mock(httpx.Response(200, json=location(wind=[11.0, 12.0])))
    assert provider.hourly([DENVER])[DENVER].wind_mph == (11.0, 12.0)


def test_results_match_cells_by_request_order(
    provider: OpenMeteoProvider, mocked: respx.MockRouter
) -> None:
    body = [location(wind=[1.0, 1.0]), location(wind=[2.0, 2.0])]
    mocked.get(FREE_URL).mock(httpx.Response(200, json=body))
    forecasts = provider.hourly([DENVER, DALLAS])
    assert forecasts[DENVER].wind_mph == (1.0, 1.0)
    assert forecasts[DALLAS].wind_mph == (2.0, 2.0)


def test_rain_sums_rain_and_showers_and_excludes_snow(
    provider: OpenMeteoProvider, mocked: respx.MockRouter
) -> None:
    body = location(rain=[12.7, 0.0], showers=[12.7, 0.0], snowfall=[50.0, 0.0])
    mocked.get(FREE_URL).mock(httpx.Response(200, json=body))
    assert provider.hourly([DENVER])[DENVER].rain_in_hr == (1.0, 0.0)


def test_units_convert_to_inches(provider: OpenMeteoProvider, mocked: respx.MockRouter) -> None:
    body = location(rain=[25.4, 0.0], snowfall=[2.54, 5.08])
    mocked.get(FREE_URL).mock(httpx.Response(200, json=body))
    forecast = provider.hourly([DENVER])[DENVER]
    assert forecast.rain_in_hr[0] == 1.0
    assert forecast.snow_in_hr == (1.0, 2.0)


def test_null_values_stay_null(provider: OpenMeteoProvider, mocked: respx.MockRouter) -> None:
    body = location(wind=[None, 5.0], rain=[1.0, None], showers=[None, 1.0], snowfall=[None, 1.0])
    mocked.get(FREE_URL).mock(httpx.Response(200, json=body))
    forecast = provider.hourly([DENVER])[DENVER]
    assert forecast.wind_mph == (None, 5.0)
    assert forecast.rain_in_hr == (None, None)
    assert forecast.snow_in_hr[0] is None


def test_requests_the_needed_variables_and_units(
    provider: OpenMeteoProvider, mocked: respx.MockRouter
) -> None:
    call = mocked.get(FREE_URL).mock(httpx.Response(200, json=[location(), location()]))
    provider.hourly([DENVER, DALLAS])
    params = call.calls.last.request.url.params
    assert params["latitude"] == "39.75,32.8"
    assert params["longitude"] == "-105.0,-96.8"
    assert params["hourly"] == "wind_speed_10m,rain,showers,snowfall"
    assert params["wind_speed_unit"] == "mph"
    assert params["timezone"] == "GMT"
    assert params["forecast_days"] == "16"
    assert params["timeformat"] == "unixtime"
    assert "precipitation_unit" not in params
    assert "apikey" not in params


def test_paid_key_uses_customer_host(mocked: respx.MockRouter) -> None:
    call = mocked.get(PAID_URL).mock(httpx.Response(200, json=location()))
    OpenMeteoProvider(api_key="paid-secret", retry_delay_seconds=0).hourly([DENVER])
    assert call.calls.last.request.url.params["apikey"] == "paid-secret"


def test_no_cells_makes_no_request(provider: OpenMeteoProvider, mocked: respx.MockRouter) -> None:
    assert provider.hourly([]) == {}
    assert not mocked.calls.called


def test_429_raises_rate_limited(provider: OpenMeteoProvider, mocked: respx.MockRouter) -> None:
    mocked.get(FREE_URL).mock(httpx.Response(429))
    with pytest.raises(ProviderRateLimited):
        provider.hourly([DENVER])


def test_minute_limit_says_when_to_retry(
    provider: OpenMeteoProvider, mocked: respx.MockRouter
) -> None:
    # The body is Open-Meteo's real response when its per-minute limit is hit.
    body = {
        "reason": "Minutely API request limit exceeded. Please try again in one minute.",
        "error": True,
    }
    mocked.get(FREE_URL).mock(httpx.Response(429, json=body))
    with pytest.raises(ProviderRateLimited) as error:
        provider.hourly([DENVER])
    assert error.value.retry_after_seconds == 60


def test_daily_limit_has_no_useful_retry_time(
    provider: OpenMeteoProvider, mocked: respx.MockRouter
) -> None:
    body = {"reason": "Daily API request limit exceeded.", "error": True}
    mocked.get(FREE_URL).mock(httpx.Response(429, json=body))
    with pytest.raises(ProviderRateLimited) as error:
        provider.hourly([DENVER])
    assert error.value.retry_after_seconds is None


def test_5xx_is_retried_twice_then_raises_unavailable(
    provider: OpenMeteoProvider, mocked: respx.MockRouter
) -> None:
    call = mocked.get(FREE_URL).mock(httpx.Response(503))
    with pytest.raises(ProviderUnavailable):
        provider.hourly([DENVER])
    assert call.call_count == 3


def test_timeout_raises_unavailable(provider: OpenMeteoProvider, mocked: respx.MockRouter) -> None:
    mocked.get(FREE_URL).mock(side_effect=httpx.ReadTimeout("timed out"))
    with pytest.raises(ProviderUnavailable):
        provider.hourly([DENVER])


def test_400_raises_unavailable(provider: OpenMeteoProvider, mocked: respx.MockRouter) -> None:
    body = {"error": True, "reason": "Latitude must be in range of -90 to 90."}
    mocked.get(FREE_URL).mock(httpx.Response(400, json=body))
    with pytest.raises(ProviderUnavailable):
        provider.hourly([DENVER])


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"hourly": {}}),
        httpx.Response(200, json=[location()]),
    ],
)
def test_malformed_response_raises_unavailable(
    provider: OpenMeteoProvider, mocked: respx.MockRouter, response: httpx.Response
) -> None:
    mocked.get(FREE_URL).mock(response)
    with pytest.raises(ProviderUnavailable):
        provider.hourly([DENVER, DALLAS])


def test_uneven_hourly_arrays_raise_unavailable(
    provider: OpenMeteoProvider, mocked: respx.MockRouter
) -> None:
    mocked.get(FREE_URL).mock(httpx.Response(200, json=location(wind=[1.0])))
    with pytest.raises(ProviderUnavailable):
        provider.hourly([DENVER])


def test_paid_key_absent_from_logs_and_errors(
    mocked: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    mocked.get(PAID_URL).mock(httpx.Response(500))
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ProviderUnavailable) as error:
        OpenMeteoProvider(api_key="paid-secret", retry_delay_seconds=0).hourly([DENVER])
    assert "paid-secret" not in str(error.value)
    assert "paid-secret" not in caplog.text


def test_rain_on_the_no_travel_boundary_is_not_pushed_over_by_float_error(
    provider: OpenMeteoProvider, mocked: respx.MockRouter
) -> None:
    # 0.1 mm + 25.3 mm is 25.4 mm, exactly 1 in/hr, which is Severe rather than No Travel.
    body = location(rain=[0.1, 0.0], showers=[25.3, 0.0])
    mocked.get(FREE_URL).mock(httpx.Response(200, json=body))
    assert provider.hourly([DENVER])[DENVER].rain_in_hr[0] == 1.0


def test_a_base_url_replaces_the_real_host(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get("http://stub:9000/v1/forecast").mock(httpx.Response(500))
    provider = OpenMeteoProvider(retry_delay_seconds=0, base_url="http://stub:9000")
    with pytest.raises(ProviderUnavailable):
        provider.hourly([DENVER])
    assert route.called


def test_the_forecast_length_can_be_chosen(respx_mock: respx.MockRouter) -> None:
    call = respx_mock.get(FREE_URL).mock(httpx.Response(500))
    with pytest.raises(ProviderUnavailable):
        OpenMeteoProvider(retry_delay_seconds=0).hourly([DENVER], forecast_days=7)
    assert call.calls[0].request.url.params["forecast_days"] == "7"
