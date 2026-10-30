from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from math import inf

from routing.domain import RiskAssessment, RiskLevel, WeatherSample
from routing.services.checkpoint_generator import Checkpoint

MILES_DECIMALS = 2
AVERAGE_RISK_DECIMALS = 4

RankKey = tuple[bool, bool, float, float, float, float, int]


@dataclass(frozen=True)
class AssessedCheckpoint:
    checkpoint: Checkpoint
    eta: datetime
    sample: WeatherSample | None
    assessment: RiskAssessment | None


@dataclass(frozen=True)
class RouteScore:
    severe_miles: float
    high_miles: float
    no_travel_miles: float
    moderate_miles: float
    low_miles: float
    unknown_miles: float
    average_risk: float | None
    duration_seconds: int


@dataclass(frozen=True)
class RankingResult:
    ordered_ids: list[str]
    recommended_id: str | None
    no_safe_route: bool


def score_route(checkpoints: Sequence[AssessedCheckpoint], duration_seconds: int) -> RouteScore:
    if not checkpoints:
        raise ValueError("A route needs at least one checkpoint to score")

    miles_by_level = dict.fromkeys(RiskLevel, 0.0)
    unknown_miles = 0.0
    for item in checkpoints:
        if item.assessment is None:
            unknown_miles += item.checkpoint.represented_miles
        else:
            miles_by_level[item.assessment.level] += item.checkpoint.represented_miles

    known_miles = sum(miles_by_level.values())
    weighted_risk = sum(level * miles for level, miles in miles_by_level.items())
    return RouteScore(
        severe_miles=miles_by_level[RiskLevel.SEVERE],
        high_miles=miles_by_level[RiskLevel.HIGH],
        no_travel_miles=miles_by_level[RiskLevel.NO_TRAVEL],
        moderate_miles=miles_by_level[RiskLevel.MODERATE],
        low_miles=miles_by_level[RiskLevel.LOW],
        unknown_miles=unknown_miles,
        average_risk=weighted_risk / known_miles if known_miles else None,
        duration_seconds=duration_seconds,
    )


def rank_key(score: RouteScore) -> RankKey:
    """Order routes strictly: never a weighted score.

    Routes with No Travel or unknown miles go last, then the assessment's order applies. Rounding
    stops floating-point noise from deciding a tie that a lower priority should break.
    """
    return (
        score.no_travel_miles > 0,
        score.unknown_miles > 0,
        round(score.no_travel_miles, MILES_DECIMALS),
        round(score.severe_miles, MILES_DECIMALS),
        round(score.high_miles, MILES_DECIMALS),
        round(score.average_risk, AVERAGE_RISK_DECIMALS) if score.average_risk is not None else inf,
        score.duration_seconds,
    )


def rank_routes(scores: Mapping[str, RouteScore]) -> RankingResult:
    if not scores:
        raise ValueError("At least one route is needed to rank")

    ordered_ids = sorted(scores, key=lambda route_id: rank_key(scores[route_id]))
    recommended_id = next(
        (route_id for route_id in ordered_ids if _can_recommend(scores[route_id])), None
    )
    return RankingResult(
        ordered_ids=ordered_ids,
        recommended_id=recommended_id,
        no_safe_route=all(score.no_travel_miles > 0 for score in scores.values()),
    )


def explain_rank(score: RouteScore, neighbour: RouteScore | None, recommended: bool) -> str:
    """Say why a route sits where it does, naming the criterion that decided it.

    `neighbour` is the next route down for the recommended route, otherwise the route above.
    """
    if score.no_travel_miles > 0:
        return f"Has {score.no_travel_miles:.0f} No Travel miles, so it cannot be recommended."
    if score.average_risk is None:
        return "No weather data is available, so it cannot be recommended."
    if neighbour is None:
        return "The only route available."
    deciding = _deciding_criterion(score, neighbour)
    if deciding is None:
        return "Tied with the next route on every criterion."
    fewest, most, formatter = deciding
    comparison = f"{formatter(score)} vs {formatter(neighbour)}"
    if recommended:
        return f"Recommended for {fewest} ({comparison})."
    if score.unknown_miles > 0:
        return f"Weather is missing for {score.unknown_miles:.0f} miles, so it ranks lower."
    return f"Ranks lower for {most} ({comparison})."


def _deciding_criterion(
    score: RouteScore, neighbour: RouteScore
) -> tuple[str, str, Callable[[RouteScore], str]] | None:
    first_key = rank_key(score)
    second_key = rank_key(neighbour)
    if first_key[:2] != second_key[:2]:
        return (
            "complete weather",
            "missing weather",
            lambda s: f"{s.unknown_miles:.0f} mi missing",
        )
    criteria = {
        2: ("fewest No Travel miles", "more No Travel miles", lambda s: f"{s.no_travel_miles:.1f}"),
        3: ("fewest Severe miles", "more Severe miles", lambda s: f"{s.severe_miles:.1f}"),
        4: ("fewest High miles", "more High miles", lambda s: f"{s.high_miles:.1f}"),
        5: ("lowest average risk", "higher average risk", lambda s: f"{s.average_risk:.2f}"),
        6: ("shortest travel time", "longer travel time", lambda s: _hours(s.duration_seconds)),
    }
    for index, criterion in criteria.items():
        if first_key[index] != second_key[index]:
            return criterion
    return None


def _hours(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    return f"{hours}h {remainder // 60:02d}m"


def _can_recommend(score: RouteScore) -> bool:
    return score.no_travel_miles == 0 and score.average_risk is not None
