import logging
import time
from collections.abc import Callable, Mapping

import httpx

from routing.providers.errors import ProviderRateLimited, ProviderUnavailable

# Providers take API keys in the query string, and httpx logs full request URLs at INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

REQUEST_TIMEOUT_SECONDS = 30
SERVER_ERROR_RETRIES = 2
DEFAULT_RETRY_DELAY_SECONDS = 0.5


def get_with_retries(
    client: httpx.Client,
    url: str,
    params: Mapping[str, str | int],
    provider_name: str,
    retry_delay_seconds: float,
    read_retry_after: Callable[[httpx.Response], float | None] | None = None,
) -> httpx.Response:
    """Send a GET, retrying server errors only. Other client errors are for the caller to read.

    Errors raised here never chain the httpx exception or include the URL, which holds the key.
    """
    for attempt in range(SERVER_ERROR_RETRIES + 1):
        if attempt:
            time.sleep(retry_delay_seconds)
        try:
            response = client.get(url, params=params)
        except httpx.HTTPError:
            raise ProviderUnavailable(f"{provider_name} could not be reached") from None
        if response.status_code < 500:
            break
    if response.status_code == 429:
        raise ProviderRateLimited(
            f"{provider_name} rate limit reached",
            retry_after_seconds=read_retry_after(response) if read_retry_after else None,
        )
    if response.status_code >= 500:
        raise ProviderUnavailable(f"{provider_name} returned HTTP {response.status_code}")
    return response
