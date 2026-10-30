"""Weather and load risk rules from the assessment.

A value on a shared endpoint takes the higher class, so bands are lower-inclusive. Rain 1.00 and
snow 3.0 stay Severe because No Travel is strictly above them. See "Resolved ambiguities" in
CLAUDE.md.
"""

import math

from routing.domain import RiskAssessment, RiskLevel, WeatherSample

WIND_BANDS_MPH = (
    (55.0, RiskLevel.NO_TRAVEL),
    (45.0, RiskLevel.SEVERE),
    (35.0, RiskLevel.HIGH),
    (25.0, RiskLevel.MODERATE),
)
RAIN_NO_TRAVEL_ABOVE_IN_HR = 1.00
RAIN_BANDS_IN_HR = (
    (0.50, RiskLevel.SEVERE),
    (0.25, RiskLevel.HIGH),
    (0.10, RiskLevel.MODERATE),
)
SNOW_NO_TRAVEL_ABOVE_IN_HR = 3.0
SNOW_BANDS_IN_HR = (
    (2.0, RiskLevel.SEVERE),
    (1.0, RiskLevel.HIGH),
    (0.5, RiskLevel.MODERATE),
)
NO_TRAVEL_WIND_LOAD_LIMIT_LB = 30_000
SEVERE_WIND_LOAD_LIMIT_LB = 40_000


def _require_reading(value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Reading must be finite and non-negative, got {value}")


def _level_from_bands(value: float, bands: tuple[tuple[float, RiskLevel], ...]) -> RiskLevel:
    for lower_bound, level in bands:
        if value >= lower_bound:
            return level
    return RiskLevel.LOW


def classify_wind(mph: float) -> RiskLevel:
    _require_reading(mph)
    return _level_from_bands(mph, WIND_BANDS_MPH)


def classify_rain(in_hr: float) -> RiskLevel:
    _require_reading(in_hr)
    if in_hr > RAIN_NO_TRAVEL_ABOVE_IN_HR:
        return RiskLevel.NO_TRAVEL
    return _level_from_bands(in_hr, RAIN_BANDS_IN_HR)


def classify_snow(in_hr: float) -> RiskLevel:
    _require_reading(in_hr)
    if in_hr > SNOW_NO_TRAVEL_ABOVE_IN_HR:
        return RiskLevel.NO_TRAVEL
    return _level_from_bands(in_hr, SNOW_BANDS_IN_HR)


def apply_load_rules(wind_mph: float, load_lb: float) -> RiskLevel:
    """Return the wind risk after load rules. They apply only to wind."""
    _require_reading(load_lb)
    level = classify_wind(wind_mph)
    if level == RiskLevel.SEVERE and load_lb > NO_TRAVEL_WIND_LOAD_LIMIT_LB:
        return RiskLevel.NO_TRAVEL
    if level == RiskLevel.HIGH and load_lb > SEVERE_WIND_LOAD_LIMIT_LB:
        return RiskLevel.SEVERE
    return level


def assess(sample: WeatherSample, load_lb: float) -> RiskAssessment:
    wind = apply_load_rules(sample.wind_mph, load_lb)
    rain = classify_rain(sample.rain_in_hr)
    snow = classify_snow(sample.snow_in_hr)
    level = max(wind, rain, snow)
    conditions = (("wind", wind), ("rain", rain), ("snow", snow))
    drivers = (
        tuple(name for name, condition in conditions if condition == level)
        if level > RiskLevel.LOW
        else ()
    )
    return RiskAssessment(
        level=level,
        wind=wind,
        rain=rain,
        snow=snow,
        load_adjusted=wind != classify_wind(sample.wind_mph),
        drivers=drivers,
    )
