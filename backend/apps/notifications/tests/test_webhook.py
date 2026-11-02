"""WhatsApp webhook (spec section 7): handshake, signature, delivery statuses."""

import hmac
import json
import logging
from hashlib import sha256

import pytest
from django.db import OperationalError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.notifications import services
from apps.notifications.factories import NotificationFactory
from apps.notifications.models import Notification
from apps.notifications.webhook import verify_signature, verify_subscription
from apps.reference.constants import NotificationChannel

SECRET = "test-app-secret"  # pinned in config/settings/test.py
PHONE_ID = "111"
pytestmark = pytest.mark.django_db


def url():
    return reverse("whatsapp-webhook")


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, sha256).hexdigest()


def status_entry(wamid, status, code=None):
    entry = {"id": wamid, "status": status}
    if code is not None:
        entry["errors"] = [{"code": code, "title": "free text with +201012345678"}]
    return entry


def payload(statuses, phone_id=PHONE_ID):
    value = {"metadata": {"phone_number_id": phone_id}, "statuses": statuses}
    return json.dumps({"entry": [{"changes": [{"value": value}]}]}).encode()


def post(body: bytes, signature="auto", client=None):
    client = client or APIClient()
    extra = {}
    if signature == "auto":
        extra["HTTP_X_HUB_SIGNATURE_256"] = sign(body)
    elif signature is not None:
        extra["HTTP_X_HUB_SIGNATURE_256"] = signature
    return client.generic("POST", url(), body, content_type="application/json", **extra)


def wa_row(wamid, status="SENT"):
    return NotificationFactory(
        channel=NotificationChannel.WHATSAPP, status=status, provider_message_id=wamid
    )


def reload(row):
    row.refresh_from_db()
    return row


def test_handshake_returns_challenge():
    response = APIClient().get(
        url(),
        {"hub.mode": "subscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "42"},
    )
    assert response.status_code == 200
    assert response.content == b"42"
    assert response["Content-Type"].startswith("text/plain")


def test_handshake_wrong_token_is_403():
    response = APIClient().get(
        url(), {"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"}
    )
    assert response.status_code == 403
    assert b"42" not in response.content


def test_handshake_wrong_mode_is_403():
    response = APIClient().get(
        url(),
        {"hub.mode": "other", "hub.verify_token": "test-verify-token", "hub.challenge": "42"},
    )
    assert response.status_code == 403


def test_handshake_with_blank_verify_token_refuses(settings):
    settings.WHATSAPP_VERIFY_TOKEN = ""
    params = {"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "42"}
    assert verify_subscription(params) is None


def test_bad_signature_is_403_and_changes_nothing():
    row = wa_row("wamid.1")
    body = payload([status_entry("wamid.1", "delivered")])
    response = post(body, signature=sign(body, "wrong-secret"))
    assert response.status_code == 403
    assert reload(row).status == "SENT"


def test_missing_signature_is_403():
    row = wa_row("wamid.1")
    response = post(payload([status_entry("wamid.1", "delivered")]), signature=None)
    assert response.status_code == 403
    assert reload(row).status == "SENT"


def test_empty_app_secret_refuses_everything(settings):
    settings.WHATSAPP_APP_SECRET = ""
    row = wa_row("wamid.1")
    body = payload([status_entry("wamid.1", "delivered")])
    assert post(body, signature=sign(body, "")).status_code == 403
    assert verify_signature(body, sign(body, "")) is False
    assert reload(row).status == "SENT"


def test_signature_covers_the_raw_bytes():
    row = wa_row("wamid.1")
    body = payload([status_entry("wamid.1", "delivered")])
    respaced = json.dumps(json.loads(body), indent=2).encode()
    assert post(respaced, signature=sign(body)).status_code == 403
    assert reload(row).status == "SENT"
    assert post(respaced).status_code == 200
    assert reload(row).status == "DELIVERED"


@pytest.mark.parametrize(
    "start,webhook_status,expected",
    [
        ("SENT", "sent", "SENT"),
        ("SENT", "delivered", "DELIVERED"),
        ("SENT", "read", "DELIVERED"),
        ("SENT", "failed", "FAILED"),
        ("DELIVERED", "sent", "DELIVERED"),
        ("DELIVERED", "delivered", "DELIVERED"),
        ("DELIVERED", "read", "DELIVERED"),
        ("DELIVERED", "failed", "DELIVERED"),
        ("FAILED", "sent", "FAILED"),
        ("FAILED", "delivered", "DELIVERED"),
        ("FAILED", "read", "DELIVERED"),
        ("FAILED", "failed", "FAILED"),
    ],
)
def test_status_table(start, webhook_status, expected):
    row = wa_row("wamid.1", status=start)
    response = post(payload([status_entry("wamid.1", webhook_status)]))
    assert response.status_code == 200
    assert response.content == b""
    assert reload(row).status == expected


def test_failed_records_metas_code_and_creates_email():
    row = wa_row("wamid.1")
    post(payload([status_entry("wamid.1", "failed", code=131026)]))
    row = reload(row)
    assert row.status == "FAILED"
    assert row.error_code == "131026"
    email = Notification.objects.get(fallback_of=row)
    assert email.channel == NotificationChannel.EMAIL
    assert email.status == "PENDING"


def test_free_text_error_code_is_replaced_by_a_fixed_code():
    row = wa_row("wamid.1")
    post(payload([status_entry("wamid.1", "failed", code="call me on 01012345678")]))
    assert reload(row).error_code == "WHATSAPP_ERROR"


def test_failed_without_a_code_still_fails_the_row():
    row = wa_row("wamid.1")
    post(payload([status_entry("wamid.1", "failed")]))
    row = reload(row)
    assert row.status == "FAILED"
    assert row.error_code == "WHATSAPP_ERROR"


def test_repeating_a_failed_status_creates_one_email():
    row = wa_row("wamid.1")
    body = payload([status_entry("wamid.1", "failed", code=131026)])
    assert post(body).status_code == 200
    assert post(body).status_code == 200
    assert Notification.objects.filter(fallback_of=row).count() == 1


def test_webhook_only_finds_whatsapp_rows():
    email = NotificationFactory(
        channel=NotificationChannel.EMAIL, status="SENT", provider_message_id="same-id"
    )
    wa = wa_row("same-id")
    post(payload([status_entry("same-id", "delivered")]))
    assert reload(email).status == "SENT"
    assert reload(wa).status == "DELIVERED"


def test_other_phone_number_id_is_ignored():
    row = wa_row("wamid.1")
    post(payload([status_entry("wamid.1", "delivered")], phone_id="999"))
    assert reload(row).status == "SENT"


def test_missing_metadata_is_ignored():
    row = wa_row("wamid.1")
    value = {"statuses": [status_entry("wamid.1", "delivered")]}
    body = json.dumps({"entry": [{"changes": [{"value": value}]}]}).encode()
    assert post(body).status_code == 200
    assert reload(row).status == "SENT"


MALFORMED = [
    b"not json",
    b"[]",
    b'{"entry": "x"}',
    b'{"entry": [{"changes": [{"value": {"statuses": ["x"]}}]}]}',
    b'{"entry": [null, 1, {"changes": "x"}, {"changes": [null, {"value": []}]}]}',
    json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": PHONE_ID},
                                "statuses": [
                                    {"id": 5, "status": ["x"]},
                                    {"id": "a"},
                                    {"status": "read"},
                                ],
                            }
                        }
                    ]
                }
            ]
        }
    ).encode(),
]


@pytest.mark.parametrize("body", MALFORMED)
def test_signed_but_malformed_body_returns_200_and_changes_nothing(body):
    row = wa_row("wamid.1")
    assert post(body).status_code == 200
    assert reload(row).status == "SENT"


def test_batch_with_known_unknown_and_repeated_ids_handles_each():
    first = wa_row("wamid.1")
    second = wa_row("wamid.2")
    body = payload(
        [
            status_entry("wamid.1", "delivered"),
            status_entry("wamid.unknown", "delivered"),
            status_entry("wamid.2", "failed", code=131026),
            status_entry("wamid.2", "failed", code=131026),
        ]
    )
    assert post(body).status_code == 200
    assert reload(first).status == "DELIVERED"
    assert reload(second).status == "FAILED"
    assert Notification.objects.filter(fallback_of=second).count() == 1


def test_database_failure_returns_500_so_meta_retries(monkeypatch):
    wa_row("wamid.1")

    def boom(*args, **kwargs):
        raise OperationalError("connection lost")

    monkeypatch.setattr(services, "apply_transition", boom)
    client = APIClient(raise_request_exception=False)
    response = post(payload([status_entry("wamid.1", "delivered")]), client=client)
    assert response.status_code == 500


def test_payload_is_never_logged(caplog):
    wa_row("wamid.1")
    body = payload([status_entry("wamid.1", "failed", code="call me on 01012345678")])
    with caplog.at_level(logging.DEBUG):
        post(body)
        post(b"not json")
        post(body, signature="sha256=bad")
    text = caplog.text
    assert "01012345678" not in text
    assert "free text" not in text
    assert "wamid.1" not in text


def test_webhook_needs_no_session_and_no_csrf():
    client = APIClient(enforce_csrf_checks=True)
    wa_row("wamid.1")
    assert post(payload([status_entry("wamid.1", "delivered")]), client=client).status_code == 200


def test_oversized_body_is_413_without_an_error_log(settings, caplog):
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 100
    row = wa_row("wamid.1")
    body = payload([status_entry("wamid.1", "delivered")]) + b" " * 200
    client = APIClient(raise_request_exception=False)
    with caplog.at_level(logging.DEBUG):
        response = post(body, client=client)
    assert response.status_code == 413
    assert response.content == b""
    assert reload(row).status == "SENT"
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
