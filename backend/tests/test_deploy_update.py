"""Runs the server's update script for real, with `docker` and `git` replaced by recording stubs."""

import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

UPDATE_SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "update.sh"
OLD = "1111111"
NEW = "2222222"

DOCKER_STUB = """#!/usr/bin/env bash
echo "docker IMAGE_TAG=${IMAGE_TAG:-} $*" >> "$STUB_DIR/calls"
case "$*" in
  *"image inspect"*) cat "$STUB_DIR/published" ;;
  *" up "*)
    [ -f "$STUB_DIR/up_fails_for_$IMAGE_TAG" ] && exit 1
    echo "$IMAGE_TAG" > "$STUB_DIR/running"
    ;;
  *"exec"*) [ -f "$STUB_DIR/wrong_version" ] && echo '{"version": "stale"}' \
      || echo "{\\"status\\": \\"ok\\", \\"version\\": \\"$(cat "$STUB_DIR/running")\\"}" ;;
esac
exit 0
"""
GIT_STUB = """#!/usr/bin/env bash
echo "git $*" >> "$STUB_DIR/calls"
exit 0
"""


@dataclass
class Server:
    root: Path
    stubs: Path
    environment: dict[str, str]

    def publish(self, revision: str) -> None:
        (self.stubs / "published").write_text(f"{revision}\n")

    def run_update(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(UPDATE_SCRIPT)], env=self.environment, capture_output=True, text=True
        )

    def calls(self) -> list[str]:
        path = self.stubs / "calls"
        return path.read_text().splitlines() if path.exists() else []

    def clear_calls(self) -> None:
        (self.stubs / "calls").unlink(missing_ok=True)

    def state(self, name: str) -> str | None:
        path = self.root / "state" / name
        return path.read_text().strip() if path.exists() else None

    def fail_up_for(self, revision: str) -> None:
        (self.stubs / f"up_fails_for_{revision}").touch()

    def deployed_tags(self) -> list[str]:
        return [
            call.split()[1].removeprefix("IMAGE_TAG=") for call in self.calls() if " up " in call
        ]


@pytest.fixture
def server(tmp_path: Path) -> Server:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in (("docker", DOCKER_STUB), ("git", GIT_STUB)):
        path = stubs / name
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    root = tmp_path / "opt"
    (root / "state").mkdir(parents=True)
    (root / ".env").write_text("TOMTOM_API_KEY=x\n")
    return Server(
        root=root,
        stubs=stubs,
        environment={
            **os.environ,
            "PATH": f"{stubs}:{os.environ['PATH']}",
            "STUB_DIR": str(stubs),
            "TRUCK_ROOT": str(root),
        },
    )


def running(server: Server, revision: str) -> None:
    (server.root / "state" / "current").write_text(f"{revision}\n")
    (server.stubs / "running").write_text(revision)


def test_a_new_revision_is_deployed_and_recorded(server: Server) -> None:
    running(server, OLD)
    server.publish(NEW)
    result = server.run_update()
    assert result.returncode == 0, result.stderr
    assert server.state("current") == NEW
    assert server.deployed_tags() == [NEW]
    assert f"git -C {server.root}/repo checkout --detach {NEW}" in server.calls()


def test_compose_files_match_the_images_being_deployed(server: Server) -> None:
    running(server, OLD)
    server.publish(NEW)
    server.run_update()
    calls = server.calls()
    checkout = calls.index(f"git -C {server.root}/repo checkout --detach {NEW}")
    first_up = next(index for index, call in enumerate(calls) if " up " in call)
    assert checkout < first_up


def test_an_unchanged_revision_does_nothing(server: Server) -> None:
    running(server, NEW)
    server.publish(NEW)
    assert server.run_update().returncode == 0
    assert server.deployed_tags() == []


def test_a_failed_deploy_rolls_back_and_reports_failure(server: Server) -> None:
    running(server, OLD)
    server.publish(NEW)
    server.fail_up_for(NEW)
    result = server.run_update()
    assert result.returncode != 0
    assert server.deployed_tags() == [NEW, OLD]
    assert server.state("current") == OLD
    assert server.state("failed") == NEW
    assert f"git -C {server.root}/repo checkout --detach {OLD}" in server.calls()


def test_a_deploy_running_the_wrong_version_rolls_back(server: Server) -> None:
    running(server, OLD)
    server.publish(NEW)
    (server.stubs / "wrong_version").touch()
    assert server.run_update().returncode != 0
    assert server.state("failed") == NEW
    assert server.state("current") == OLD


def test_a_failed_revision_is_not_retried_every_run(server: Server) -> None:
    running(server, OLD)
    server.publish(NEW)
    server.fail_up_for(NEW)
    server.run_update()
    server.clear_calls()
    assert server.run_update().returncode == 0
    assert server.deployed_tags() == []


def test_a_fixed_revision_deploys_after_a_failed_one(server: Server) -> None:
    running(server, OLD)
    server.publish(NEW)
    server.fail_up_for(NEW)
    server.run_update()
    server.clear_calls()
    server.publish("3333333")
    assert server.run_update().returncode == 0
    assert server.state("current") == "3333333"


def test_the_first_deploy_failing_has_nothing_to_roll_back_to(server: Server) -> None:
    server.publish(NEW)
    server.fail_up_for(NEW)
    assert server.run_update().returncode != 0
    assert server.state("current") is None
    assert server.deployed_tags() == [NEW]


def test_an_image_without_a_revision_is_refused(server: Server) -> None:
    running(server, OLD)
    server.publish("")
    assert server.run_update().returncode != 0
    assert server.deployed_tags() == []
