from datetime import UTC, datetime

import pytest

from routing.domain import RiskAssessment, RiskLevel
from routing.services.checkpoint_generator import Checkpoint
from routing.services.route_scorer import (
    AssessedCheckpoint,
    RouteScore,
    rank_routes,
    score_route,
)

ETA = datetime(2026, 11, 1, 12, tzinfo=UTC)


def assessed(miles: float, level: RiskLevel | None) -> AssessedCheckpoint:
    checkpoint = Checkpoint(
        mile=0.0, position=(30.0, -100.0), represented_miles=miles, start_mile=0.0, end_mile=miles
    )
    if level is None:
        return AssessedCheckpoint(checkpoint=checkpoint, eta=ETA, sample=None, assessment=None)
    assessment = RiskAssessment(
        level=level,
        wind=level,
        rain=RiskLevel.LOW,
        snow=RiskLevel.LOW,
        load_adjusted=False,
        drivers=(),
    )
    return AssessedCheckpoint(checkpoint=checkpoint, eta=ETA, sample=None, assessment=assessment)


def score(
    severe: float = 0,
    high: float = 0,
    no_travel: float = 0,
    unknown: float = 0,
    average: float | None = 0.0,
    duration: int = 3600,
) -> RouteScore:
    return RouteScore(
        severe_miles=severe,
        high_miles=high,
        no_travel_miles=no_travel,
        moderate_miles=0,
        low_miles=0,
        unknown_miles=unknown,
        average_risk=average,
        duration_seconds=duration,
    )


def test_aggregates_miles_by_level() -> None:
    result = score_route(
        [
            assessed(10, RiskLevel.LOW),
            assessed(20, RiskLevel.MODERATE),
            assessed(30, RiskLevel.HIGH),
            assessed(40, RiskLevel.SEVERE),
            assessed(50, RiskLevel.NO_TRAVEL),
            assessed(60, None),
        ],
        7200,
    )
    assert result.low_miles == 10
    assert result.moderate_miles == 20
    assert result.high_miles == 30
    assert result.severe_miles == 40
    assert result.no_travel_miles == 50
    assert result.unknown_miles == 60
    assert result.duration_seconds == 7200


def test_aggregates_distance_weighted_average() -> None:
    result = score_route(
        [
            assessed(25, RiskLevel.LOW),
            assessed(50, RiskLevel.HIGH),
            assessed(25, RiskLevel.SEVERE),
        ],
        3600,
    )
    assert result.average_risk == 1.75


def test_average_ignores_unknown_miles() -> None:
    result = score_route(
        [assessed(50, RiskLevel.LOW), assessed(50, RiskLevel.HIGH), assessed(100, None)], 3600
    )
    assert result.average_risk == 1.0


def test_all_unknown_average_is_none() -> None:
    assert score_route([assessed(100, None)], 3600).average_risk is None


def test_scoring_no_checkpoints_rejected() -> None:
    with pytest.raises(ValueError):
        score_route([], 3600)


def test_fewer_severe_beats_faster() -> None:
    result = rank_routes(
        {"fast": score(severe=5, duration=7200), "safe": score(severe=0, duration=36000)}
    )
    assert result.ordered_ids == ["safe", "fast"]
    assert result.recommended_id == "safe"


def test_severe_outranks_high_miles() -> None:
    result = rank_routes({"a": score(severe=1, high=0), "b": score(severe=0, high=500)})
    assert result.ordered_ids == ["b", "a"]


def test_high_miles_break_severe_tie() -> None:
    result = rank_routes({"a": score(severe=5, high=20), "b": score(severe=5, high=10)})
    assert result.ordered_ids == ["b", "a"]


def test_high_miles_outrank_average_risk() -> None:
    result = rank_routes({"a": score(high=1, average=0.1), "b": score(high=0, average=3.0)})
    assert result.ordered_ids == ["b", "a"]


def test_average_risk_breaks_high_tie() -> None:
    result = rank_routes(
        {"a": score(average=2.0, duration=10), "b": score(average=1.0, duration=99)}
    )
    assert result.ordered_ids == ["b", "a"]


def test_duration_only_breaks_full_tie() -> None:
    result = rank_routes({"a": score(duration=7200), "b": score(duration=3600)})
    assert result.ordered_ids == ["b", "a"]


def test_float_noise_does_not_override_priority() -> None:
    result = rank_routes(
        {"a": score(severe=10.000001, duration=3600), "b": score(severe=10.0, duration=7200)}
    )
    assert result.ordered_ids == ["a", "b"]


def test_no_travel_route_never_recommended() -> None:
    result = rank_routes({"a": score(no_travel=1, severe=0), "b": score(severe=50)})
    assert result.ordered_ids == ["b", "a"]
    assert result.recommended_id == "b"
    assert not result.no_safe_route


def test_all_no_travel_returns_no_recommendation() -> None:
    result = rank_routes(
        {
            "a": score(no_travel=30),
            "b": score(no_travel=10),
            "c": score(no_travel=20),
        }
    )
    assert result.recommended_id is None
    assert result.no_safe_route
    assert result.ordered_ids == ["b", "c", "a"]


def test_unknown_ranks_after_complete() -> None:
    result = rank_routes({"a": score(unknown=1, severe=0), "b": score(severe=50)})
    assert result.ordered_ids == ["b", "a"]
    assert result.recommended_id == "b"


def test_no_travel_ranks_after_unknown() -> None:
    result = rank_routes({"a": score(no_travel=1), "b": score(unknown=100)})
    assert result.ordered_ids == ["b", "a"]


def test_partly_unknown_route_can_be_recommended_when_no_complete_route_exists() -> None:
    result = rank_routes({"a": score(unknown=10, severe=1), "b": score(no_travel=5)})
    assert result.recommended_id == "a"


def test_route_with_no_known_weather_is_not_recommended() -> None:
    result = rank_routes({"a": score(unknown=100, average=None), "b": score(no_travel=5)})
    assert result.ordered_ids == ["a", "b"]
    assert result.recommended_id is None
    assert not result.no_safe_route


def test_ranking_no_routes_rejected() -> None:
    with pytest.raises(ValueError):
        rank_routes({})
