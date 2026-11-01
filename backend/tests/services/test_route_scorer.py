from datetime import UTC, datetime

import pytest

from routing.domain import RiskAssessment, RiskLevel
from routing.services.checkpoint_generator import Checkpoint
from routing.services.route_scorer import (
    AssessedCheckpoint,
    RouteScore,
    explain_rank,
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


def test_fewer_unknown_miles_outrank_a_cleaner_looking_partial_route() -> None:
    # Nearly all of A is unknown, so its zero Severe miles say almost nothing.
    result = rank_routes(
        {
            "a": score(unknown=95, average=0.0),
            "b": score(unknown=5, severe=50, average=1.5),
        }
    )
    assert result.ordered_ids == ["b", "a"]
    assert result.recommended_id == "b"


def test_a_route_with_no_known_weather_ranks_after_a_partly_known_one() -> None:
    result = rank_routes(
        {
            "none": score(unknown=100, average=None),
            "some": score(unknown=90, severe=10, average=3.0),
        }
    )
    assert result.ordered_ids == ["some", "none"]
    assert result.recommended_id == "some"


def test_average_risk_ties_at_the_precision_people_see() -> None:
    # 0.0251 and 0.0254 both show as 0.025, so travel time must decide.
    result = rank_routes(
        {"a": score(average=0.0251, duration=7200), "b": score(average=0.0254, duration=3600)}
    )
    assert result.ordered_ids == ["b", "a"]


def test_rationale_against_a_no_travel_route_names_no_travel() -> None:
    text = explain_rank(score(), score(no_travel=200), recommended=True)
    assert "No Travel" in text
    assert "missing" not in text


def test_rationale_against_a_route_with_missing_weather_names_it() -> None:
    text = explain_rank(score(), score(unknown=40), recommended=True)
    assert "complete weather" in text
    assert "40 mi" in text


def test_rationale_shows_average_risks_that_actually_differ() -> None:
    text = explain_rank(score(average=0.025), score(average=0.031), recommended=True)
    assert "0.025 vs 0.031" in text


def test_rationale_for_a_lower_route_against_a_cleaner_one() -> None:
    text = explain_rank(score(severe=5), score(severe=0), recommended=False)
    assert text == "Ranks lower for more Severe miles (5.0 vs 0.0)."


def test_rationale_for_the_most_complete_of_two_partial_routes() -> None:
    text = explain_rank(score(unknown=5, severe=50), score(unknown=95), recommended=True)
    assert "complete" in text
    assert "5 mi" in text and "95 mi" in text
