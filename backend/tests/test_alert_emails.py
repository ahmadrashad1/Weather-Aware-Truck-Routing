"""Runs the alert scripts for real, with `aws` and `curl` replaced by recording stubs."""

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
KEY = "re_test_secret_value"
CURL = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$STUB_DIR/curl_args"
cat > "$STUB_DIR/body"
[ -f "$STUB_DIR/curl_fails" ] && exit 22
exit 0
"""
AWS = """#!/usr/bin/env bash
cat "$STUB_DIR/alarms"
"""


@pytest.fixture
def stubs(tmp_path: Path) -> Path:
    for name, source in (("curl", CURL), ("aws", AWS)):
        path = tmp_path / name
        path.write_text(source)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return tmp_path


def environment(stubs: Path, **extra: str) -> dict[str, str]:
    return {
        **os.environ,
        "PATH": f"{stubs}:{os.environ['PATH']}",
        "STUB_DIR": str(stubs),
        "RESEND_API_KEY": KEY,
        "ALERT_EMAIL": "owner@example.com",
        **extra,
    }


def send(stubs: Path, **extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(DEPLOY / "send-alert.sh"), "Site down", 'It said "no"'],
        env=environment(stubs, **extra),
        capture_output=True,
        text=True,
    )


def check_alarms(stubs: Path, alarms: str, state: Path) -> subprocess.CompletedProcess[str]:
    (stubs / "alarms").write_text(alarms)
    return subprocess.run(
        ["bash", str(DEPLOY / "check-alarms.sh"), str(state)],
        env=environment(stubs, INSTANCE="truck-routing"),
        capture_output=True,
        text=True,
    )


def body(stubs: Path) -> dict[str, object]:
    return json.loads((stubs / "body").read_text())  # type: ignore[no-any-return]


def test_an_alert_goes_to_resend_with_safely_quoted_text(stubs: Path) -> None:
    result = send(stubs)
    assert result.returncode == 0
    assert "https://api.resend.com/emails" in (stubs / "curl_args").read_text()
    assert body(stubs)["to"] == ["owner@example.com"]
    assert body(stubs)["subject"] == "Site down"
    assert body(stubs)["text"] == 'It said "no"'


def test_the_free_sender_is_used_unless_another_is_set(stubs: Path) -> None:
    send(stubs)
    assert "onboarding@resend.dev" in str(body(stubs)["from"])
    send(stubs, ALERT_FROM="Alerts <alerts@example.com>")
    assert body(stubs)["from"] == "Alerts <alerts@example.com>"


def test_the_key_is_never_on_the_command_line_or_in_the_output(stubs: Path) -> None:
    result = send(stubs)
    assert KEY not in (stubs / "curl_args").read_text()
    assert KEY not in result.stdout + result.stderr


def test_a_failed_send_is_a_failure(stubs: Path) -> None:
    (stubs / "curl_fails").touch()
    assert send(stubs).returncode != 0


def test_missing_settings_are_a_clear_failure(stubs: Path) -> None:
    result = send(stubs, ALERT_EMAIL="")
    assert result.returncode != 0
    assert "ALERT_EMAIL" in result.stderr
    assert not (stubs / "body").exists()


OK = "high-cpu\tOK\nlow-burst\tOK\n"
FIRING = "high-cpu\tALARM\nlow-burst\tOK\n"


def test_a_new_alarm_sends_an_email(stubs: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    check_alarms(stubs, OK, state)
    check_alarms(stubs, FIRING, state)
    assert "high-cpu" in str(body(stubs)["subject"])
    assert "ALARM" in str(body(stubs)["text"])


def test_an_alarm_that_stays_on_emails_only_once(stubs: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    check_alarms(stubs, FIRING, state)
    (stubs / "body").unlink()
    check_alarms(stubs, FIRING, state)
    assert not (stubs / "body").exists()


def test_recovery_sends_an_email(stubs: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    check_alarms(stubs, FIRING, state)
    check_alarms(stubs, OK, state)
    assert "recovered" in str(body(stubs)["subject"]).lower()


def test_quiet_alarms_send_nothing_even_on_the_first_run(stubs: Path, tmp_path: Path) -> None:
    check_alarms(stubs, "high-cpu\tINSUFFICIENT_DATA\nlow-burst\tOK\n", tmp_path / "state")
    assert not (stubs / "body").exists()


def test_a_failed_send_keeps_the_old_state_so_it_tries_again(stubs: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    check_alarms(stubs, OK, state)
    (stubs / "curl_fails").touch()
    assert check_alarms(stubs, FIRING, state).returncode != 0
    assert state.read_text() == OK
