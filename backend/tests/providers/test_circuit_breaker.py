import httpx
import pytest
import respx

from routing.providers.breaker import CircuitBreaker, breaker_for
from routing.providers.errors import ProviderRateLimited, ProviderUnavailable
from routing.providers.http import get_with_retries

URL = "https://provider.example/data"


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def tripped(clock: Clock) -> CircuitBreaker:
    breaker = CircuitBreaker("test", clock=clock)
    for _ in range(3):
        breaker.record_failure()
    return breaker


def test_two_failures_leave_it_closed() -> None:
    breaker = CircuitBreaker("test", clock=Clock())
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.allow()


def test_three_failures_in_a_row_open_it() -> None:
    assert not tripped(Clock()).allow()


def test_a_success_clears_earlier_failures() -> None:
    breaker = CircuitBreaker("test", clock=Clock())
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    assert breaker.allow()


def test_after_the_pause_only_one_request_tries_the_provider() -> None:
    clock = Clock()
    breaker = tripped(clock)
    clock.now += 30
    assert breaker.allow()
    assert not breaker.allow()


def test_a_successful_trial_closes_it() -> None:
    clock = Clock()
    breaker = tripped(clock)
    clock.now += 30
    breaker.allow()
    breaker.record_success()
    assert breaker.allow()
    assert breaker.allow()


def test_a_failed_trial_opens_it_for_another_pause() -> None:
    clock = Clock()
    breaker = tripped(clock)
    clock.now += 30
    breaker.allow()
    breaker.record_failure()
    clock.now += 29
    assert not breaker.allow()
    clock.now += 1
    assert breaker.allow()


def test_a_trial_that_never_reports_back_does_not_block_forever() -> None:
    clock = Clock()
    breaker = tripped(clock)
    clock.now += 30
    assert breaker.allow()
    clock.now += 30
    assert breaker.allow()


def call(client: httpx.Client, name: str = "Provider") -> httpx.Response:
    return get_with_retries(client, URL, {}, name, 0)


@respx.mock
def test_repeated_outages_stop_reaching_the_provider() -> None:
    route = respx.get(URL).mock(side_effect=httpx.ConnectTimeout("hang"))
    with httpx.Client() as client:
        for _ in range(3):
            with pytest.raises(ProviderUnavailable):
                call(client)
        assert route.call_count == 3
        with pytest.raises(ProviderUnavailable):
            call(client)
    assert route.call_count == 3


@respx.mock
def test_each_failed_request_counts_once_despite_its_retries() -> None:
    respx.get(URL).mock(return_value=httpx.Response(503))
    with httpx.Client() as client:
        with pytest.raises(ProviderUnavailable):
            call(client)
        with pytest.raises(ProviderUnavailable):
            call(client)
    assert breaker_for("Provider").allow()


@respx.mock
def test_a_rate_limit_means_the_provider_is_up() -> None:
    respx.get(URL).mock(return_value=httpx.Response(429))
    with httpx.Client() as client:
        for _ in range(4):
            with pytest.raises(ProviderRateLimited):
                call(client)
    assert breaker_for("Provider").allow()


@respx.mock
def test_one_providers_outage_does_not_block_another() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectTimeout("hang"))
    with httpx.Client() as client:
        for _ in range(3):
            with pytest.raises(ProviderUnavailable):
                call(client, "Down")
    assert breaker_for("Up").allow()


@respx.mock
def test_provider_calls_are_logged_without_the_url_or_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    respx.get(URL).mock(return_value=httpx.Response(200, json={}))
    with httpx.Client() as client:
        get_with_retries(client, URL, {"key": "secret"}, "Provider", 0)
    [event] = [r.fields for r in caplog.records if r.getMessage() == "provider_call"]  # type: ignore[attr-defined]
    assert event["provider"] == "Provider"
    assert event["status"] == 200
    assert "secret" not in str(event)
    assert "provider.example" not in str(event)
