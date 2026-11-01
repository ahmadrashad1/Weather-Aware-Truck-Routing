import json
import logging
import time
import traceback
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("app")

# Docker checks this every few seconds, which would bury real traffic.
UNLOGGED_PATHS = frozenset({"/api/v1/health"})

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_counters: ContextVar[dict[str, int] | None] = ContextVar("counters", default=None)


class JsonFormatter(logging.Formatter):
    """Write one JSON object per line.

    An exception's message is left out, because a provider error's message can hold a URL with an
    API key in it. Its type and traceback are enough to find the cause.
    """

    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info and record.exc_info[0]:
            line["exception"] = record.exc_info[0].__name__
            line["traceback"] = "".join(traceback.format_tb(record.exc_info[2]))
        return json.dumps(line, default=str)


def log_event(event: str, **fields: Any) -> None:
    """Log a named event. Never pass API keys, URLs, search text, coordinates or IP addresses."""
    logger.info(event, extra={"fields": {"request_id": _request_id.get(), **fields}})


def count(name: str, amount: int = 1) -> None:
    """Add to a total that the current request's log line reports."""
    counters = _counters.get()
    if counters is not None:
        counters[name] = counters.get(name, 0) + amount


class RequestLogMiddleware:
    """Give each request an ID, and log its outcome once it finishes."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = str(uuid.uuid4())
        id_token = _request_id.set(request_id)
        counters: dict[str, int] = {}
        counters_token = _counters.set(counters)
        started = time.perf_counter()
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            if request.path not in UNLOGGED_PATHS:
                log_event(
                    "request",
                    method=request.method,
                    # A matched route only, as the raw path of a bad request can be anything.
                    path=request.path if request.resolver_match else "(no route)",
                    status=response.status_code,
                    duration_ms=round((time.perf_counter() - started) * 1000),
                    **counters,
                )
            return response
        finally:
            _request_id.reset(id_token)
            _counters.reset(counters_token)
