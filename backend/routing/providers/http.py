import logging
import random
import time
from collections.abc import Callable, Mapping

import httpx

from config.observability import log_event
from routing.providers.breaker import breaker_for
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
    A rate limit shows the provider is up, so only outages count towards its circuit breaker.
    """
    breaker = breaker_for(provider_name)
    if not breaker.allow():
        raise ProviderUnavailable(f"{provider_name} is paused after repeated failures")
    for attempt in range(SERVER_ERROR_RETRIES + 1):
        if attempt:
            # Varied, so requests that failed together don't all retry together.
            time.sleep(retry_delay_seconds * random.uniform(0.5, 1.5))
        started = time.perf_counter()
        try:
            response = client.get(url, params=params)
        except httpx.HTTPError as error:
            log_event(
                "provider_call",
                provider=provider_name,
                error=type(error).__name__,
                duration_ms=_elapsed_ms(started),
            )
            breaker.record_failure()
            raise ProviderUnavailable(f"{provider_name} could not be reached") from None
        log_event(
            "provider_call",
            provider=provider_name,
            status=response.status_code,
            duration_ms=_elapsed_ms(started),
        )
        if response.status_code < 500:
            break
    if response.status_code >= 500:
        breaker.record_failure()
    else:
        breaker.record_success()
    if response.status_code == 429:
        raise ProviderRateLimited(
            f"{provider_name} rate limit reached",
            retry_after_seconds=read_retry_after(response) if read_retry_after else None,
        )
    if response.status_code >= 500:
        raise ProviderUnavailable(f"{provider_name} returned HTTP {response.status_code}")
    return response


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
