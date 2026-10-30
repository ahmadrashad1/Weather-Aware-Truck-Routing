import importlib
from collections.abc import Iterator
from types import ModuleType

import pytest
from django.core.exceptions import ImproperlyConfigured


@pytest.fixture(autouse=True)
def _restore_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    yield
    monkeypatch.undo()
    import config.settings

    importlib.reload(config.settings)


def load_settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> ModuleType:
    for name in ("DJANGO_SECRET_KEY", "DJANGO_DEBUG", "ALLOWED_HOSTS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    import config.settings

    return importlib.reload(config.settings)


def test_missing_secret_key_without_debug_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        load_settings(monkeypatch)


def test_secret_key_without_debug_works(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings(monkeypatch, DJANGO_SECRET_KEY="s3cret")
    assert settings.SECRET_KEY == "s3cret"
    assert settings.DEBUG is False
    assert "*" not in settings.ALLOWED_HOSTS


def test_debug_without_secret_key_works(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings(monkeypatch, DJANGO_DEBUG="true")
    assert settings.SECRET_KEY
    assert settings.ALLOWED_HOSTS == ["*"]
