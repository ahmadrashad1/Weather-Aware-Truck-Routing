import json
import logging
import uuid

import pytest
from django.test import Client

from config.observability import JsonFormatter, count, log_event


def format_record(message: str = "hello", **fields: object) -> dict[str, object]:
    record = logging.LogRecord("app", logging.INFO, __file__, 1, message, None, None)
    record.fields = fields
    return json.loads(JsonFormatter().format(record))  # type: ignore[no-any-return]


def events(caplog: pytest.LogCaptureFixture, name: str) -> list[dict[str, object]]:
    return [
        getattr(record, "fields", {}) for record in caplog.records if record.getMessage() == name
    ]


def test_formatter_writes_one_json_object_with_the_fields() -> None:
    line = format_record("request", status=200)
    assert line["event"] == "request"
    assert line["status"] == 200
    assert line["level"] == "INFO"
    assert "time" in line


def test_formatter_keeps_the_traceback_but_not_the_exception_message() -> None:
    message = "?key=" + "secret"
    try:
        raise ValueError(message)
    except ValueError as error:
        record = logging.LogRecord(
            "app",
            logging.ERROR,
            __file__,
            1,
            "boom",
            None,
            (ValueError, error, error.__traceback__),
        )
    line = JsonFormatter().format(record)
    assert "ValueError" in line
    assert "test_observability" in line
    assert "secret" not in line


def test_each_response_gets_a_new_request_id(client: Client) -> None:
    first = client.get("/api/v1/geocode")["X-Request-ID"]
    second = client.get("/api/v1/geocode")["X-Request-ID"]
    assert uuid.UUID(first) != uuid.UUID(second)


def test_a_client_cannot_choose_its_request_id(client: Client) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "forged"})
    assert response["X-Request-ID"] != "forged"


def test_requests_are_logged_with_timing_and_status(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    response = client.get("/api/v1/geocode")
    [event] = events(caplog, "request")
    assert event["request_id"] == response["X-Request-ID"]
    assert event["method"] == "GET"
    assert event["path"] == "/api/v1/geocode"
    assert event["status"] == 400
    assert isinstance(event["duration_ms"], int | float)


def test_search_text_is_not_logged(client: Client, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    client.get("/api/v1/geocode", {"q": "x" * 300})
    assert "xxx" not in json.dumps(events(caplog, "request"))


def test_health_checks_are_not_logged(client: Client, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    client.get("/api/v1/health")
    assert events(caplog, "request") == []


def test_counters_outside_a_request_are_ignored() -> None:
    count("weather_cells_cached", 5)


def test_events_outside_a_request_have_no_request_id(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    log_event("startup", ok=True)
    assert events(caplog, "startup") == [{"request_id": None, "ok": True}]
