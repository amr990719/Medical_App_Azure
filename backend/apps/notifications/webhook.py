"""WhatsApp webhook (spec section 7). The signature check is the endpoint's only protection.

Nothing from a payload is logged or stored: it holds phone numbers and message text. Only a
status's provider ID, the status word and an error code (made safe) are read from it.
"""

import hashlib
import hmac
import json
from collections.abc import Iterator, Mapping
from typing import Any

from django.conf import settings

from apps.reference.constants import NotificationChannel, NotificationStatus

from . import services
from .formatting import safe_code
from .models import Notification

WEBHOOK_ERROR = "WHATSAPP_ERROR"
SIGNATURE_PREFIX = "sha256="

# Webhook status word -> the status a row moves to (spec section 7). `sent` changes nothing.
_STATUS_TARGETS = {
    "delivered": NotificationStatus.DELIVERED,
    "read": NotificationStatus.DELIVERED,
    "failed": NotificationStatus.FAILED,
}


class InvalidSignature(Exception):
    """The body was not signed with our app secret."""


def verify_signature(raw_body: bytes, header: str | None) -> bool:
    """HMAC-SHA256 of the raw bytes, constant-time. A blank secret refuses everything."""
    secret = settings.WHATSAPP_APP_SECRET
    if not secret or not header:
        return False
    expected = SIGNATURE_PREFIX + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), header.encode())


def verify_subscription(params: Mapping[str, str]) -> str | None:
    """Meta's handshake: the challenge when mode and token match, otherwise None."""
    token = settings.WHATSAPP_VERIFY_TOKEN
    if not token or params.get("hub.mode") != "subscribe":
        return None
    if not hmac.compare_digest(params.get("hub.verify_token", "").encode(), token.encode()):
        return None
    return params.get("hub.challenge", "")


def process_webhook(raw_body: bytes, signature_header: str | None) -> None:
    """Verify, then apply every status in the payload. Database errors propagate (Meta retries)."""
    if not verify_signature(raw_body, signature_header):
        raise InvalidSignature
    try:
        payload = json.loads(raw_body)
    except ValueError:
        return  # signed but not JSON: acknowledge so Meta does not retry it for days
    for value in _values(payload):
        _apply_statuses(value)
        # Task 11 adds `_apply_messages(value)` here.


def _dicts(items: Any) -> Iterator[dict]:
    if isinstance(items, list):
        yield from (item for item in items if isinstance(item, dict))


def _values(payload: Any) -> Iterator[dict]:
    """Each `entry[].changes[].value` that is ours (its `metadata.phone_number_id` matches)."""
    ours = settings.WHATSAPP_PHONE_NUMBER_ID
    if not ours or not isinstance(payload, dict):
        return
    for entry in _dicts(payload.get("entry")):
        for change in _dicts(entry.get("changes")):
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata")
            if isinstance(metadata, dict) and metadata.get("phone_number_id") == ours:
                yield value


def _apply_statuses(value: dict) -> None:
    for item in _dicts(value.get("statuses")):
        message_id, word = item.get("id"), item.get("status")
        target = _STATUS_TARGETS.get(word) if isinstance(word, str) else None
        if target is None or not isinstance(message_id, str) or not message_id:
            continue
        row_id = (
            Notification.objects.filter(
                channel=NotificationChannel.WHATSAPP, provider_message_id=message_id
            )
            .values_list("pk", flat=True)
            .first()
        )
        if row_id is None:
            continue
        error_code = _error_code(item) if target == NotificationStatus.FAILED else ""
        services.apply_transition(row_id, to_status=target, error_code=error_code)


def _error_code(item: dict) -> str:
    """Meta's `errors[0].code` (an integer) as a safe identifier; anything else is fixed."""
    first = next(_dicts(item.get("errors")), {})
    code = first.get("code")
    if isinstance(code, bool) or not isinstance(code, (int, str)):
        return WEBHOOK_ERROR
    return safe_code(str(code), fallback=WEBHOOK_ERROR)
