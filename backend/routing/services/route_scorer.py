from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from math import inf

from routing.domain import RiskAssessment, RiskLevel, WeatherSample
from routing.services.checkpoint_generator import Checkpoint

MILES_DECIMALS = 2
# The same precision the API shows, so two routes that look tied are treated as tied.
AVERAGE_RISK_DECIMALS = 3

RankKey = tuple[bool, bool, bool, float, float, float, float, float, int]


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

    Routes with No Travel miles go last, then routes with no known weather, then routes with some
    unknown miles, most complete first, because a route's unknown miles can hide anything. After
    that the assessment's order applies. Rounding stops floating-point noise from deciding a tie
    that a lower priority should break.
    """
    return (
        score.no_travel_miles > 0,
        score.average_risk is None,
        score.unknown_miles > 0,
        round(score.no_travel_miles, MILES_DECIMALS),
        round(score.unknown_miles, MILES_DECIMALS),
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
    return f"Ranks lower for {most} ({comparison})."


def _deciding_criterion(
    score: RouteScore, neighbour: RouteScore
) -> tuple[str, str, Callable[[RouteScore], str]] | None:
    for index, criterion in enumerate(_RANK_CRITERIA):
        if rank_key(score)[index] != rank_key(neighbour)[index]:
            return criterion
    return None


def _no_travel_text(score: RouteScore) -> str:
    return f"{score.no_travel_miles:.0f} mi"


def _missing_text(score: RouteScore) -> str:
    return f"{score.unknown_miles:.0f} mi missing"


# One entry per position in rank_key: what to call it when a route wins or loses on it.
_RANK_CRITERIA: tuple[tuple[str, str, Callable[[RouteScore], str]], ...] = (
    ("avoiding No Travel", "having No Travel miles", _no_travel_text),
    ("having weather data", "having no weather data", _missing_text),
    ("complete weather", "missing weather", _missing_text),
    ("fewest No Travel miles", "more No Travel miles", lambda s: f"{s.no_travel_miles:.1f}"),
    ("the most complete weather", "more missing weather", _missing_text),
    ("fewest Severe miles", "more Severe miles", lambda s: f"{s.severe_miles:.1f}"),
    ("fewest High miles", "more High miles", lambda s: f"{s.high_miles:.1f}"),
    ("lowest average risk", "higher average risk", lambda s: f"{s.average_risk:.3f}"),
    ("shortest travel time", "longer travel time", lambda s: _hours(s.duration_seconds)),
)


def _hours(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    return f"{hours}h {remainder // 60:02d}m"


def _can_recommend(score: RouteScore) -> bool:
    return score.no_travel_miles == 0 and score.average_risk is not None
