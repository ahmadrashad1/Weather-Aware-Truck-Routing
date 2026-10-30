import math
from collections.abc import Callable

import pytest

from routing.domain import RiskLevel, WeatherSample
from routing.services.risk_engine import (
    apply_load_rules,
    assess,
    classify_rain,
    classify_snow,
    classify_wind,
)

LOW = RiskLevel.LOW
MODERATE = RiskLevel.MODERATE
HIGH = RiskLevel.HIGH
SEVERE = RiskLevel.SEVERE
NO_TRAVEL = RiskLevel.NO_TRAVEL


@pytest.mark.parametrize(
    "mph,expected",
    [
        (0, LOW),
        (24.99, LOW),
        (25, MODERATE),
        (34.99, MODERATE),
        (35, HIGH),
        (44.99, HIGH),
        (45, SEVERE),
        (54.99, SEVERE),
        (55, NO_TRAVEL),
        (90, NO_TRAVEL),
    ],
)
def test_wind_bands(mph: float, expected: RiskLevel) -> None:
    assert classify_wind(mph) == expected


@pytest.mark.parametrize(
    "rate,expected",
    [
        (0, LOW),
        (0.099, LOW),
        (0.10, MODERATE),
        (0.249, MODERATE),
        (0.25, HIGH),
        (0.499, HIGH),
        (0.50, SEVERE),
        (1.00, SEVERE),
        (1.001, NO_TRAVEL),
    ],
)
def test_rain_bands(rate: float, expected: RiskLevel) -> None:
    assert classify_rain(rate) == expected


@pytest.mark.parametrize(
    "rate,expected",
    [
        (0, LOW),
        (0.49, LOW),
        (0.5, MODERATE),
        (0.99, MODERATE),
        (1.0, HIGH),
        (1.99, HIGH),
        (2.0, SEVERE),
        (3.0, SEVERE),
        (3.01, NO_TRAVEL),
    ],
)
def test_snow_bands(rate: float, expected: RiskLevel) -> None:
    assert classify_snow(rate) == expected


@pytest.mark.parametrize(
    "mph,load,expected",
    [
        (35, 40_000, HIGH),
        (35, 40_001, SEVERE),
        (44.99, 40_001, SEVERE),
        (45, 30_000, SEVERE),
        (45, 30_001, NO_TRAVEL),
        (54.99, 30_001, NO_TRAVEL),
        (55, 0, NO_TRAVEL),
        (34.99, 80_000, MODERATE),
        (45, 40_001, NO_TRAVEL),
    ],
)
def test_load_rules(mph: float, load: float, expected: RiskLevel) -> None:
    assert apply_load_rules(mph, load) == expected


def test_final_is_worst_condition() -> None:
    assert assess(WeatherSample(10, 0.3, 0.6), 1000).level == HIGH
    assert assess(WeatherSample(35, 1.5, 0), 40_001).level == NO_TRAVEL


def test_each_condition_is_classified_independently() -> None:
    result = assess(WeatherSample(26, 0.3, 2.5), 1000)
    assert (result.wind, result.rain, result.snow) == (MODERATE, HIGH, SEVERE)
    assert result.level == SEVERE


def test_load_adjustment_is_reported() -> None:
    result = assess(WeatherSample(35, 0, 0), 40_001)
    assert result.load_adjusted and result.wind == SEVERE


def test_load_at_exact_limit_is_not_adjusted() -> None:
    result = assess(WeatherSample(35, 0, 0), 40_000)
    assert not result.load_adjusted and result.wind == HIGH


def test_load_rules_do_not_change_rain_or_snow() -> None:
    result = assess(WeatherSample(0, 0.3, 1.0), 80_000)
    assert (result.rain, result.snow) == (HIGH, HIGH)
    assert not result.load_adjusted


def test_drivers_name_every_condition_at_the_final_level() -> None:
    assert assess(WeatherSample(35, 0.3, 0), 1000).drivers == ("wind", "rain")
    assert assess(WeatherSample(0, 0, 3.5), 1000).drivers == ("snow",)


def test_low_risk_has_no_drivers() -> None:
    assert assess(WeatherSample(10, 0.01, 0), 1000).drivers == ()


@pytest.mark.parametrize("classify", [classify_wind, classify_rain, classify_snow])
@pytest.mark.parametrize("bad", [-0.01, math.nan, math.inf])
def test_invalid_reading_raises(classify: Callable[[float], RiskLevel], bad: float) -> None:
    with pytest.raises(ValueError):
        classify(bad)


@pytest.mark.parametrize("bad", [-1, math.nan, math.inf])
def test_invalid_load_raises(bad: float) -> None:
    with pytest.raises(ValueError):
        apply_load_rules(10, bad)
