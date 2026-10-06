"""Gunicorn settings of the production image (PROMPT.md §31, §38)."""

import importlib


def load(monkeypatch, **env):
    for key in ("PORT", "GUNICORN_WORKERS", "GUNICORN_THREADS", "GUNICORN_TIMEOUT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import config.gunicorn

    return importlib.reload(config.gunicorn)


def test_defaults(monkeypatch):
    conf = load(monkeypatch)
    assert conf.bind == "0.0.0.0:8000"
    assert conf.workers == 3
    assert conf.timeout == 60


def test_environment_overrides(monkeypatch):
    conf = load(monkeypatch, PORT="9000", GUNICORN_WORKERS="5", GUNICORN_TIMEOUT="90")
    assert (conf.bind, conf.workers, conf.timeout) == ("0.0.0.0:9000", 5, 90)


def test_no_unmasked_access_log_and_no_preload(monkeypatch):
    conf = load(monkeypatch)
    assert conf.accesslog is None  # query strings could carry national IDs
    assert conf.preload_app is False  # telemetry exporters start in each worker


def test_control_socket_disabled(monkeypatch):
    assert load(monkeypatch).control_socket_disable is True
