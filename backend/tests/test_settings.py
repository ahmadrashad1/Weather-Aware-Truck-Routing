import ast
import importlib
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from django.core.exceptions import ImproperlyConfigured

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_NAMES = (
    "DJANGO_SECRET_KEY",
    "DJANGO_DEBUG",
    "ALLOWED_HOSTS",
    "TOMTOM_API_KEY",
    "REDIS_URL",
    "NUM_PROXIES",
    "DJANGO_SECURE_SSL_REDIRECT",
)
PRODUCTION = {
    "DJANGO_SECRET_KEY": "a-long-random-production-secret-key-that-is-at-least-fifty-characters",
    "ALLOWED_HOSTS": "app.example.com",
    "TOMTOM_API_KEY": "tomtom-key",
    "REDIS_URL": "redis://127.0.0.1:6379/0",
}


@pytest.fixture(autouse=True)
def _restore_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    yield
    monkeypatch.undo()
    import config.settings

    importlib.reload(config.settings)


def load_settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> ModuleType:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    import config.settings

    return importlib.reload(config.settings)


@pytest.mark.parametrize("missing", list(PRODUCTION))
def test_production_refuses_to_start_without_a_required_setting(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    env = {name: value for name, value in PRODUCTION.items() if name != missing}
    with pytest.raises(ImproperlyConfigured, match=missing):
        load_settings(monkeypatch, **env)


def test_production_starts_with_every_required_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings(monkeypatch, **PRODUCTION)
    assert settings.DEBUG is False
    assert settings.ALLOWED_HOSTS == ["app.example.com"]
    assert settings.CACHES["default"]["BACKEND"] == "config.cache.ResilientRedisCache"


def test_production_is_https_only(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings(monkeypatch, **PRODUCTION)
    assert settings.SECURE_SSL_REDIRECT is True
    assert settings.SESSION_COOKIE_SECURE is True
    assert settings.CSRF_COOKIE_SECURE is True
    assert settings.SECURE_HSTS_SECONDS >= 31_536_000


def test_a_load_balancer_can_reach_health_over_http(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings(monkeypatch, **PRODUCTION)
    assert any("health" in pattern for pattern in settings.SECURE_REDIRECT_EXEMPT)


def test_https_redirect_can_be_turned_off_for_a_local_stack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(monkeypatch, **PRODUCTION, DJANGO_SECURE_SSL_REDIRECT="false")
    assert settings.SECURE_SSL_REDIRECT is False


def test_forwarded_headers_are_ignored_unless_a_proxy_is_declared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(monkeypatch, **PRODUCTION)
    assert settings.REST_FRAMEWORK["NUM_PROXIES"] is None
    assert settings.SECURE_PROXY_SSL_HEADER is None


def test_a_declared_proxy_is_trusted_for_client_ip_and_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(monkeypatch, **PRODUCTION, NUM_PROXIES="2")
    assert settings.REST_FRAMEWORK["NUM_PROXIES"] == 2
    assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")


def test_debug_needs_no_production_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings(monkeypatch, DJANGO_DEBUG="true")
    assert settings.SECRET_KEY
    assert settings.ALLOWED_HOSTS == ["*"]
    assert settings.SECURE_SSL_REDIRECT is False
    assert "locmem" in settings.CACHES["default"]["BACKEND"]


def test_django_deployment_check_finds_nothing() -> None:
    environment = {
        **{name: value for name, value in os.environ.items() if name not in ENV_NAMES},
        **PRODUCTION,
    }
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_production_code_never_imports_from_tests() -> None:
    offenders = []
    for path in (BACKEND_DIR / "routing").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(name == "tests" or name.startswith("tests.") for name in names):
                offenders.append(str(path))
    assert offenders == []
