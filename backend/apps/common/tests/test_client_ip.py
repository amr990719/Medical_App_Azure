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
