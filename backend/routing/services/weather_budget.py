import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from django.core.cache import cache

HOUR_SECONDS = 60 * 60
DAY_SECONDS = 24 * HOUR_SECONDS
# Long enough that a counter outlives its window, whichever moment it was created in.
EXPIRY_MARGIN_SECONDS = 60


class Purpose(Enum):
    CHECKPOINTS = "checkpoints"
    HEATMAP = "heatmap"


@dataclass(frozen=True)
class BudgetLimits:
    per_hour: int
    per_day: int
    per_client_hour: int
    # The share of the shared limits heatmaps may use, which keeps the rest for checkpoint risk.
    heatmap_share: float


class WeatherBudgetExceeded(Exception):
    def __init__(self, window: str, purpose: Purpose) -> None:
        super().__init__(f"Weather budget reached: {window}, {purpose.value}")
        self.window = window
        self.purpose = purpose


class WeatherBudget:
    """Count the forecast locations requested, so no one client can use up everyone's quota.

    Counters reset when the app restarts, and live in the cache, where a full cache can evict
    them. Open-Meteo's own rate limit remains the backstop in both cases.
    """

    def __init__(self, limits: BudgetLimits, clock: Callable[[], float] = time.time) -> None:
        self._limits = limits
        self._clock = clock

    def spend(self, locations: int, client: str, purpose: Purpose) -> tuple[str, ...]:
        """Take `locations` from every limit, or raise and take none. Returns a refund receipt."""
        if locations == 0:
            return ()
        now = self._clock()
        share = self._limits.heatmap_share if purpose is Purpose.HEATMAP else 1.0
        hour = int(now // HOUR_SECONDS)
        day = int(now // DAY_SECONDS)
        counters = (
            (
                "client_hour",
                f"weather-budget:client:{client}:{hour}",
                self._limits.per_client_hour,
                HOUR_SECONDS,
            ),
            ("hour", f"weather-budget:hour:{hour}", self._limits.per_hour * share, HOUR_SECONDS),
            ("day", f"weather-budget:day:{day}", self._limits.per_day * share, DAY_SECONDS),
        )
        taken: list[str] = []
        for window, key, limit, seconds in counters:
            cache.add(key, 0, seconds + EXPIRY_MARGIN_SECONDS)
            total = cache.incr(key, locations)
            taken.append(key)
            if total > limit:
                # Adding before checking means two requests at once can't both pass the limit.
                for held in taken:
                    cache.decr(held, locations)
                raise WeatherBudgetExceeded(window, purpose)
        return tuple(taken)

    def refund(self, receipt: tuple[str, ...], locations: int) -> None:
        """Give back locations that were reserved but never fetched."""
        for key in receipt:
            try:
                cache.decr(key, locations)
            except ValueError:  # The counter's window has already ended.
                continue
