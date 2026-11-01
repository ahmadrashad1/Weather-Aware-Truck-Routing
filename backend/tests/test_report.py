import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPORT = Path(__file__).resolve().parents[2] / "deploy" / "report.py"
NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)


def line(event: str, age_hours: float = 0, **fields: object) -> str:
    when = NOW - timedelta(hours=age_hours)
    return json.dumps({"time": when.isoformat(), "event": event, **fields})


def run(*lines: str) -> str:
    return subprocess.run(
        [sys.executable, str(REPORT), "--now", NOW.isoformat()],
        input="\n".join(lines),
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_latency_percentiles_by_endpoint() -> None:
    output = run(
        *[
            line("request", path="/api/v1/trips/plan", status=200, duration_ms=ms)
            for ms in range(1, 101)
        ]
    )
    row = next(text for text in output.splitlines() if "/api/v1/trips/plan" in text)
    assert row.split()[1:5] == ["100", "50", "95", "99"]


def test_status_codes_are_counted() -> None:
    output = run(
        line("request", path="/a", status=200, duration_ms=1),
        line("request", path="/a", status=503, duration_ms=1),
        line("request", path="/a", status=503, duration_ms=1),
    )
    assert "200: 1" in output
    assert "503: 2" in output


def test_cache_hit_rate_and_locations_used() -> None:
    output = run(
        line(
            "request",
            path="/a",
            status=200,
            duration_ms=1,
            weather_cells_cached=30,
            weather_cells_fetched=10,
        ),
    )
    assert "Weather cache hit rate: 75%" in output
    assert "last hour 10" in output
    assert "last 24 hours 10" in output


def test_only_recent_locations_count_as_the_last_hour() -> None:
    output = run(
        line("request", 2, path="/a", status=200, duration_ms=1, weather_cells_fetched=7),
        line("request", 0.5, path="/a", status=200, duration_ms=1, weather_cells_fetched=3),
        line("request", 30, path="/a", status=200, duration_ms=1, weather_cells_fetched=100),
    )
    assert "last hour 3" in output
    assert "last 24 hours 10" in output


def test_provider_calls_refusals_and_vitals() -> None:
    output = run(
        line("provider_call", provider="TomTom", status=200, duration_ms=800),
        line("weather_budget_refused", window="client_hour", purpose="heatmap"),
        line("circuit_opened", provider="Open-Meteo"),
        line("web_vital", name="LCP", value=3000.0, rating="good"),
    )
    assert "TomTom" in output
    assert "client_hour" in output
    assert "Open-Meteo" in output
    assert "LCP" in output


def test_other_log_lines_are_ignored() -> None:
    output = run("[2026-11-02] [INFO] Booting worker", "not json", '["a list"]')
    assert "No requests" in output
