"""Client IP behind trusted proxies (SWA linked backend -> Container Apps ingress -> Django).

X-Forwarded-For is client-controlled except for the entries the trusted proxies append at its
end, so only the configured number of proxies is ever trusted (never the whole header).
"""

import pytest
from django.test import RequestFactory, override_settings
from rest_framework.test import APIClient

from apps.common.client_ip import client_ip

pytestmark = pytest.mark.django_db
CALLBACK = "/api/v1/auth/callback/"


def proxies(n: int):
    from django.conf import settings

    return override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": n})


def req(xff: str | None = None, remote: str = "10.0.0.5"):
    extra = {"HTTP_X_FORWARDED_FOR": xff} if xff is not None else {}
    return RequestFactory().get("/", REMOTE_ADDR=remote, **extra)


def test_without_forwarded_header_the_peer_address_is_used():
    with proxies(2):
        assert client_ip(req()) == "10.0.0.5"


def test_no_trusted_proxy_ignores_the_header():
    with proxies(0):
        assert client_ip(req("198.51.100.9")) == "10.0.0.5"


@pytest.mark.parametrize(
    ("count", "xff", "expected"),
    [
        (1, "198.51.100.9, 203.0.113.7", "203.0.113.7"),  # spoofed entry first, ingress last
        (2, "198.51.100.9, 203.0.113.7, 20.0.0.1", "203.0.113.7"),  # SWA then ingress
        (2, "20.0.0.1", "20.0.0.1"),  # fewer entries than proxies: the oldest one
    ],
)
def test_only_the_entries_appended_by_trusted_proxies_count(count, xff, expected):
    with proxies(count):
        assert client_ip(req(xff)) == expected


def test_a_spoofed_header_does_not_bypass_the_callback_throttle():
    from unittest import mock

    from rest_framework.throttling import ScopedRateThrottle

    # The shipped settings (no override): DRF must never key on the whole client header.
    with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"auth_callback": "2/min"}):
        spoofed = [f"198.51.100.{n}, 203.0.113.7" for n in range(3)]
        statuses = [
            APIClient().get(CALLBACK, HTTP_X_FORWARDED_FOR=xff).status_code for xff in spoofed
        ]
    assert statuses == [302, 302, 429]


# --- PROXY-1: the derived entry can carry the client's source port ---------------------------
# Production, 2026-11-06: 25 callbacks on new connections got no 429, the same 25 on one keep-alive
# connection got 429 from request 21. The key changed with every source port (`ip:port`).

SWA = "20.46.1.2"


@pytest.mark.parametrize(
    ("xff", "expected"),
    [
        (f"198.51.100.77:50123, {SWA}", "198.51.100.77"),  # IPv4 with a port
        (f"  198.51.100.77  , {SWA}", "198.51.100.77"),  # whitespace
        (f"[2001:db8::1]:443, {SWA}", "2001:db8::1"),  # bracketed IPv6 with a port
        (f"[2001:db8::1], {SWA}", "2001:db8::1"),  # bracketed IPv6 without a port
        (f"2001:db8::1, {SWA}", "2001:db8::1"),  # bare IPv6: its colons are not a port
        (f"2001:DB8:0:0:0:0:0:1, {SWA}", "2001:db8::1"),  # one spelling per address
    ],
)
def test_the_client_address_never_includes_a_port(xff, expected):
    with proxies(2):
        assert client_ip(req(xff)) == expected


@pytest.mark.parametrize(
    "entry",
    [
        "not-an-ip",
        "unknown",
        "999.1.1.1:80",
        "198.51.100.77:abc",
        "198.51.100.77:",
        ":80",
        "[2001:db8::1:443",
        "[2001:db8::1]443",
        "[198.51.100.77:80",
    ],
)
def test_an_unparseable_entry_falls_back_to_the_peer_address(entry):
    with proxies(2):
        assert client_ip(req(f"{entry}, {SWA}")) == "10.0.0.5"


def test_a_new_source_port_per_request_does_not_bypass_the_callback_throttle():
    from unittest import mock

    from rest_framework.throttling import SimpleRateThrottle

    with (
        proxies(2),
        mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"auth_callback": "20/min"}),
    ):
        statuses = [
            APIClient()
            .get(CALLBACK, HTTP_X_FORWARDED_FOR=f"198.51.100.77:{50000 + n}, {SWA}")
            .status_code
            for n in range(25)
        ]
    assert statuses == [302] * 20 + [429] * 5


def test_every_throttle_in_use_keys_on_the_normalised_client_address():
    from django.urls import get_resolver

    from apps.common.throttling import ClientAddressThrottleMixin

    def views(patterns):
        for pattern in patterns:
            if hasattr(pattern, "url_patterns"):
                yield from views(pattern.url_patterns)
            else:
                callback = pattern.callback
                yield getattr(callback, "cls", None) or getattr(callback, "view_class", None)

    throttled = {
        (view, throttle)
        for view in views(get_resolver().url_patterns)
        if view is not None
        for throttle in getattr(view, "throttle_classes", [])
    }
    # callback, dev login, two upload views, OCR, notification resend
    assert len({view for view, _ in throttled}) >= 6
    plain = {(v, t) for v, t in throttled if not issubclass(t, ClientAddressThrottleMixin)}
    assert plain == set()


def test_the_audit_hash_is_the_same_whatever_the_source_port():
    from apps.accounts.factories import UserFactory
    from apps.applications.factories import ApplicationFactory
    from apps.audit.models import AuditAction
    from apps.audit.services import record

    app, user = ApplicationFactory(), UserFactory()
    with proxies(2):
        hashes = {
            record(
                actor=user,
                action=AuditAction.APPLICATION_CREATED,
                obj=app,
                request=req(f"198.51.100.77:{port}, {SWA}"),
            ).ip_hash
            for port in (50001, 50002)
        }
    assert len(hashes) == 1


def test_the_audit_hash_follows_the_trusted_client_address():
    from apps.accounts.factories import UserFactory
    from apps.applications.factories import ApplicationFactory
    from apps.audit.models import AuditAction
    from apps.audit.services import record

    app, user = ApplicationFactory(), UserFactory()
    with proxies(1):
        hashes = {
            record(
                actor=user,
                action=AuditAction.APPLICATION_CREATED,
                obj=app,
                request=req(f"{spoofed}, 203.0.113.7"),
            ).ip_hash
            for spoofed in ("198.51.100.1", "198.51.100.2")
        }
    assert len(hashes) == 1
