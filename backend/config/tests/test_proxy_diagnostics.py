"""Forwarded-chain diagnostic for PROXY-1 / Q-T13 (PROXY_DIAGNOSTICS_ENABLED, off by default).

The production burst got no 429 although every request carried a made-up X-Forwarded-For. Which
entry the throttle keys on depends on how many entries the SWA linked backend and the Container
Apps ingress really append, and on whether those entries carry a port. Neither can be observed
locally, so one log line per request reports the shape of the chain: entry counts and a short
keyed hash of the derived client address (the throttle key), never an address.
"""

import json
import logging

import pytest
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient

from config.logging import JsonFormatter

pytestmark = pytest.mark.django_db
CALLBACK = "/api/v1/auth/callback/"
LOGGER = "apps.proxy"
SPOOFED, CLIENT, CLIENT_PORT, SWA = "203.0.113.1", "198.51.100.77", "50123", "20.46.1.2"


def diagnostics(enabled: bool = True, proxies: int = 2):
    return override_settings(
        PROXY_DIAGNOSTICS_ENABLED=enabled,
        REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": proxies},
    )


def records(caplog):
    return [r for r in caplog.records if r.name == LOGGER]


def call(caplog, xff: str | None = None, **flags):
    caplog.clear()
    caplog.set_level(logging.INFO, logger=LOGGER)
    extra = {"HTTP_X_FORWARDED_FOR": xff} if xff is not None else {}
    with diagnostics(**flags):
        APIClient().get(CALLBACK, **extra)
    return records(caplog)


def test_off_by_default(caplog):
    assert settings.PROXY_DIAGNOSTICS_ENABLED is False
    caplog.set_level(logging.INFO, logger=LOGGER)
    APIClient().get(CALLBACK, HTTP_X_FORWARDED_FOR=SPOOFED)
    assert records(caplog) == []


def test_reports_the_shape_of_the_chain(caplog):
    (record,) = call(caplog, f"{SPOOFED}, {CLIENT}:{CLIENT_PORT}, {SWA}")
    assert record.levelno == logging.INFO
    assert record.xff_entries == 3
    assert record.xff_entries_with_port == 1
    assert record.trusted_proxies == 2
    assert record.cache_backend == "LocMemCache"
    assert record.path == CALLBACK
    assert len(record.client_key) == 12


def test_never_logs_an_address_or_port(caplog):
    (record,) = call(caplog, f"{SPOOFED}, {CLIENT}:{CLIENT_PORT}, {SWA}")
    line = JsonFormatter().format(record)
    assert json.loads(line)["xff_entries"] == 3  # one structured line carrying the counts
    for value in (SPOOFED, CLIENT, CLIENT_PORT, SWA, "127.0.0.1"):
        assert value not in line


def test_without_a_forwarded_header(caplog):
    (record,) = call(caplog)
    assert (record.xff_entries, record.xff_entries_with_port) == (0, 0)


def test_the_client_key_is_the_throttle_key(caplog):
    # Same derived entry behind different spoofed ones: one key (the throttle would count them).
    first = call(caplog, f"{SPOOFED}, {CLIENT}, {SWA}")[0].client_key
    second = call(caplog, f"203.0.113.2, {CLIENT}, {SWA}")[0].client_key
    # Only one entry appended: the spoofed entry is derived, so every request gets a new key.
    third = call(caplog, f"203.0.113.3, {SWA}")[0].client_key
    fourth = call(caplog, f"203.0.113.4, {SWA}")[0].client_key
    assert first == second
    assert third != fourth


@pytest.mark.parametrize(
    ("xff", "with_port"),
    [
        ("[2001:db8::1]:443, 2001:db8::2", 1),  # bracketed IPv6 with a port
        ("2001:db8::1, 2001:db8::2", 0),  # bare IPv6 addresses carry no port
        (f"{CLIENT}:{CLIENT_PORT}, {SWA}:443", 2),
    ],
)
def test_counts_entries_that_carry_a_port(caplog, xff, with_port):
    (record,) = call(caplog, xff)
    assert record.xff_entries_with_port == with_port
