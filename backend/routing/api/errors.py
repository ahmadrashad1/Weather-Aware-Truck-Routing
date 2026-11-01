import logging
from typing import Any

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from routing.api.capacity import ServerBusy
from routing.providers.errors import NoRouteFound, ProviderRateLimited, ProviderUnavailable
from routing.services.weather_budget import Purpose, WeatherBudgetExceeded

logger = logging.getLogger(__name__)

RATE_LIMIT_MESSAGE = "Too many requests right now. Please try again in a minute."
BUSY_MESSAGE = "The server is busy with other trips. Please try again in a moment."
BUSY_RETRY_SECONDS = 15
HEATMAP_QUOTA_MESSAGE = (
    "Forecast shading is unavailable right now because the weather data limit is close. "
    "Route risks are not affected."
)
CLIENT_QUOTA_MESSAGE = "You've reached the hourly limit for weather checks. Please try again later."
SHARED_QUOTA_MESSAGE = "The app has reached its limit for weather checks. Please try again later."


def error_body(code: str, message: str, fields: Any = None) -> dict[str, Any]:
    body = {"code": code, "message": message}
    if fields is not None:
        body["fields"] = fields
    return body


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    """Give every error one JSON shape, with fixed messages that cannot leak provider details."""
    if isinstance(exc, NoRouteFound):
        return Response(
            error_body("no_route", "No truck route connects these locations."),
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    if isinstance(exc, ServerBusy):
        return Response(
            error_body("busy", BUSY_MESSAGE),
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": str(BUSY_RETRY_SECONDS)},
        )
    if isinstance(exc, WeatherBudgetExceeded):
        return Response(
            error_body("quota_exhausted", _quota_message(exc)),
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    if isinstance(exc, ProviderRateLimited):
        return Response(
            error_body("rate_limited", RATE_LIMIT_MESSAGE),
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    if isinstance(exc, ProviderUnavailable):
        return Response(
            error_body(
                "provider_unavailable",
                "The routing or weather service is unavailable. Please try again shortly.",
            ),
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(exc, exceptions.ValidationError):
        detail = exc.detail
        fields = detail if isinstance(detail, dict) else {"non_field_errors": detail}
        return Response(
            error_body("validation_error", "Please check the highlighted fields.", fields),
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, exceptions.Throttled):
        throttled = Response(
            error_body("rate_limited", RATE_LIMIT_MESSAGE),
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        wait = getattr(exc, "wait", None)
        if wait is not None:
            throttled["Retry-After"] = str(int(wait))
        return throttled

    handled = drf_exception_handler(exc, context)
    if handled is not None:
        handled.data = error_body(_code_for(exc), str(exc))
        return handled

    logger.error("Unexpected error while handling a request", exc_info=exc)
    return Response(
        error_body("server_error", "Something went wrong. Please try again."),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _quota_message(exc: WeatherBudgetExceeded) -> str:
    if exc.purpose is Purpose.HEATMAP:
        return HEATMAP_QUOTA_MESSAGE
    return CLIENT_QUOTA_MESSAGE if exc.window == "client_hour" else SHARED_QUOTA_MESSAGE


def _code_for(exc: Exception) -> str:
    if isinstance(exc, exceptions.ParseError):
        return "validation_error"
    if isinstance(exc, exceptions.APIException):
        return str(exc.default_code)
    return "not_found"
