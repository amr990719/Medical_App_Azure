"""Production settings must refuse to start when misconfigured (PROMPT.md §27, §30)."""

import importlib
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured

VALID_ENV = {
    "DJANGO_SECRET_KEY": "x" * 60,
    "ALLOWED_HOSTS": "api.example.test",
    "CSRF_TRUSTED_ORIGINS": "https://app.example.test",
    "DATABASE_URL": "postgres://u:p@db.example.test:5432/medical",
}


def load_production(monkeypatch, **overrides):
    for key in ("DJANGO_SECRET_KEY", "ALLOWED_HOSTS", "DATABASE_URL", "DEV_AUTH_ENABLED", "DEBUG"):
        monkeypatch.delenv(key, raising=False)
    for key, value in {**VALID_ENV, **overrides}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    for name in ("config.settings.production", "config.settings.base"):
        sys.modules.pop(name, None)
    return importlib.import_module("config.settings.production")


@pytest.fixture(autouse=True)
def _restore_modules():
    yield
    for name in ("config.settings.production", "config.settings.base"):
        sys.modules.pop(name, None)


def test_valid_production_environment_loads(monkeypatch):
    prod = load_production(monkeypatch)
    assert prod.DEBUG is False
    assert prod.DEV_AUTH_ENABLED is False
    assert prod.ALLOWED_HOSTS == ["api.example.test"]
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.CSRF_COOKIE_SECURE is True
    assert prod.SESSION_COOKIE_HTTPONLY is True
    assert prod.SESSION_COOKIE_SAMESITE == "Lax"
    assert prod.SECURE_HSTS_SECONDS >= 31536000
    assert prod.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert prod.DATABASES["default"]["OPTIONS"]["sslmode"] == "require"


def test_production_refuses_dev_auth(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="DEV_AUTH_ENABLED"):
        load_production(monkeypatch, DEV_AUTH_ENABLED="true")


def test_production_refuses_debug(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="DEBUG"):
        load_production(monkeypatch, DEBUG="true")


@pytest.mark.parametrize("missing", ["DJANGO_SECRET_KEY", "ALLOWED_HOSTS", "DATABASE_URL"])
def test_production_requires_setting(monkeypatch, missing):
    with pytest.raises(ImproperlyConfigured, match=missing):
        load_production(monkeypatch, **{missing: None})


def test_production_refuses_wildcard_hosts(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="ALLOWED_HOSTS"):
        load_production(monkeypatch, ALLOWED_HOSTS="*")


def test_production_refuses_short_secret_key(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        load_production(monkeypatch, DJANGO_SECRET_KEY="short")
