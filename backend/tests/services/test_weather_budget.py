import pytest
from django.core.cache import cache

from routing.services.weather_budget import (
    BudgetLimits,
    Purpose,
    WeatherBudget,
    WeatherBudgetExceeded,
)

LIMITS = BudgetLimits(per_hour=100, per_day=150, per_client_hour=60, heatmap_share=0.8)
HOUR = 3600
DAY = 24 * HOUR


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0 * DAY

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def budget(clock: Clock) -> WeatherBudget:
    return WeatherBudget(LIMITS, clock)


def test_spending_up_to_a_clients_limit_is_allowed(budget: WeatherBudget) -> None:
    budget.spend(60, "a", Purpose.CHECKPOINTS)


def test_one_location_over_a_clients_limit_is_refused(budget: WeatherBudget) -> None:
    budget.spend(60, "a", Purpose.CHECKPOINTS)
    with pytest.raises(WeatherBudgetExceeded) as refused:
        budget.spend(1, "a", Purpose.CHECKPOINTS)
    assert refused.value.window == "client_hour"
    assert refused.value.purpose is Purpose.CHECKPOINTS


def test_one_client_at_its_limit_does_not_block_another(budget: WeatherBudget) -> None:
    budget.spend(60, "a", Purpose.CHECKPOINTS)
    budget.spend(10, "b", Purpose.CHECKPOINTS)


def test_the_hourly_limit_is_shared_by_all_clients(budget: WeatherBudget) -> None:
    budget.spend(60, "a", Purpose.CHECKPOINTS)
    budget.spend(40, "b", Purpose.CHECKPOINTS)
    with pytest.raises(WeatherBudgetExceeded) as refused:
        budget.spend(1, "c", Purpose.CHECKPOINTS)
    assert refused.value.window == "hour"


def test_the_daily_limit_outlasts_the_hour(budget: WeatherBudget, clock: Clock) -> None:
    budget.spend(60, "a", Purpose.CHECKPOINTS)
    budget.spend(40, "b", Purpose.CHECKPOINTS)
    clock.now += HOUR
    budget.spend(50, "c", Purpose.CHECKPOINTS)
    with pytest.raises(WeatherBudgetExceeded) as refused:
        budget.spend(1, "d", Purpose.CHECKPOINTS)
    assert refused.value.window == "day"


def test_limits_reset_in_the_next_window(budget: WeatherBudget, clock: Clock) -> None:
    budget.spend(60, "a", Purpose.CHECKPOINTS)
    clock.now += HOUR
    budget.spend(60, "a", Purpose.CHECKPOINTS)


def test_a_refused_spend_uses_none_of_any_budget(budget: WeatherBudget) -> None:
    budget.spend(50, "a", Purpose.CHECKPOINTS)
    with pytest.raises(WeatherBudgetExceeded):
        budget.spend(11, "a", Purpose.CHECKPOINTS)
    # All 10 remaining still work, so the refused 11 was given back to the client and global counts.
    budget.spend(10, "a", Purpose.CHECKPOINTS)
    budget.spend(40, "b", Purpose.CHECKPOINTS)


def test_heatmaps_stop_early_to_keep_quota_for_safety_checks(budget: WeatherBudget) -> None:
    budget.spend(60, "a", Purpose.CHECKPOINTS)
    budget.spend(20, "b", Purpose.HEATMAP)
    with pytest.raises(WeatherBudgetExceeded) as refused:
        budget.spend(1, "c", Purpose.HEATMAP)
    assert refused.value.purpose is Purpose.HEATMAP
    budget.spend(20, "c", Purpose.CHECKPOINTS)


def test_nothing_to_fetch_costs_nothing(budget: WeatherBudget) -> None:
    budget.spend(60, "a", Purpose.CHECKPOINTS)
    budget.spend(0, "a", Purpose.CHECKPOINTS)


def test_refunding_gives_back_every_limit(budget: WeatherBudget) -> None:
    receipt = budget.spend(60, "a", Purpose.CHECKPOINTS)
    budget.refund(receipt, 60)
    budget.spend(60, "a", Purpose.CHECKPOINTS)
    budget.spend(40, "b", Purpose.CHECKPOINTS)


def test_refunding_after_the_counters_expired_is_harmless(budget: WeatherBudget) -> None:
    receipt = budget.spend(10, "a", Purpose.CHECKPOINTS)
    cache.clear()
    budget.refund(receipt, 10)
