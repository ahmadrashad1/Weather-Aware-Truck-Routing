import logging
from typing import Any

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from routing.providers.errors import NoRouteFound, ProviderRateLimited, ProviderUnavailable

logger = logging.getLogger(__name__)

RATE_LIMIT_MESSAGE = "Too many requests right now. Please try again in a minute."


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


def _code_for(exc: Exception) -> str:
    if isinstance(exc, exceptions.ParseError):
        return "validation_error"
    if isinstance(exc, exceptions.APIException):
        return str(exc.default_code)
    return "not_found"
