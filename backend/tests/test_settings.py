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
from django.test import override_settings
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework.throttling import BaseThrottle

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_NAMES = (
    "DJANGO_SECRET_KEY",
    "DJANGO_DEBUG",
    "ALLOWED_HOSTS",
    "TOMTOM_API_KEY",
    "REDIS_URL",
    "NUM_PROXIES",
    "DJANGO_SECURE_SSL_REDIRECT",
    "APP_VERSION",
    "PROVIDER_STUB_URL",
)
PRODUCTION = {
    "DJANGO_SECRET_KEY": "a-long-random-production-secret-key-that-is-at-least-fifty-characters",
    "ALLOWED_HOSTS": "app.example.com",
    "TOMTOM_API_KEY": "tomtom-key",
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


def test_production_caches_in_process_without_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rate limits read the cache, so production needs one even with no Redis.
    settings = load_settings(monkeypatch, **PRODUCTION)
    assert "locmem" in settings.CACHES["default"]["BACKEND"]


def test_the_in_process_cache_is_bounded_for_a_small_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # About 20 KB a forecast, and Open-Meteo's hourly limit is 5,000 locations.
    settings = load_settings(monkeypatch, **PRODUCTION)
    assert settings.CACHES["default"]["OPTIONS"]["MAX_ENTRIES"] <= 5_000


def test_redis_is_used_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings(monkeypatch, **PRODUCTION, REDIS_URL="redis://127.0.0.1:6379/0")
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


def test_no_proxy_is_trusted_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings(monkeypatch, **PRODUCTION)
    assert settings.REST_FRAMEWORK["NUM_PROXIES"] == 0
    assert settings.SECURE_PROXY_SSL_HEADER is None


def client_identity(forwarded_for: str) -> str:
    request = APIRequestFactory().get(
        "/", HTTP_X_FORWARDED_FOR=forwarded_for, REMOTE_ADDR="10.0.0.9"
    )
    return str(BaseThrottle().get_ident(Request(request)))


def test_a_forged_header_cannot_dodge_rate_limits_by_default() -> None:
    assert client_identity("1.1.1.1") == "10.0.0.9"
    assert client_identity("2.2.2.2") == "10.0.0.9"


@override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1})
def test_behind_one_proxy_the_client_is_what_the_proxy_appended() -> None:
    assert client_identity("9.9.9.9, 203.0.113.7") == "203.0.113.7"


def test_a_declared_proxy_is_trusted_for_client_ip_and_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(monkeypatch, **PRODUCTION, NUM_PROXIES="2")
    assert settings.REST_FRAMEWORK["NUM_PROXIES"] == 2
    assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")


def test_version_comes_from_the_image(monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_settings(monkeypatch, **PRODUCTION).APP_VERSION == "dev"
    settings = load_settings(monkeypatch, **PRODUCTION, APP_VERSION="abc123")
    assert settings.APP_VERSION == "abc123"


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


def test_the_budget_stays_under_open_meteos_free_limits() -> None:
    from django.conf import settings

    limits = settings.WEATHER_BUDGET_LIMITS
    assert limits["per_hour"] < 5_000
    assert limits["per_day"] < 10_000


STUB = {"PROVIDER_STUB_URL": "http://stub:9000", "DJANGO_SECURE_SSL_REDIRECT": "false"}


def test_production_has_no_provider_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_settings(monkeypatch, **PRODUCTION).PROVIDER_STUB_URL == ""


def test_a_stub_refuses_to_start_on_an_https_stack(monkeypatch: pytest.MonkeyPatch) -> None:
    # The production overlay turns HTTPS redirects on, so a stub there stops the app from starting.
    with pytest.raises(ImproperlyConfigured, match="PROVIDER_STUB_URL"):
        load_settings(monkeypatch, **PRODUCTION, PROVIDER_STUB_URL="http://stub:9000")


def test_a_stub_lifts_limits_so_they_do_not_hide_the_servers_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(monkeypatch, **PRODUCTION, **STUB)
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["trip_plan"] == "1000000/hour"
    assert settings.WEATHER_BUDGET_LIMITS["per_client_hour"] > 1_000_000


def test_limits_stay_in_place_without_a_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings(monkeypatch, **PRODUCTION)
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["trip_plan"] == "30/hour"
    assert settings.WEATHER_BUDGET_LIMITS["per_client_hour"] == 1_500
