"""Notification status changes (spec section 4). Every change goes through `apply_transition`."""

import logging
from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.reference.constants import NotificationChannel, NotificationStatus

from .models import Notification

logger = logging.getLogger("apps.notifications")

S = NotificationStatus

ALLOWED_TRANSITIONS = frozenset(
    {
        (S.PENDING, S.EXPIRED),
        (S.PENDING, S.SUPERSEDED),
        (S.PENDING, S.SUPPRESSED),
        (S.PENDING, S.FAILED),
        (S.PENDING, S.SENDING),
        (S.SENDING, S.SENT),
        (S.SENDING, S.PENDING),
        (S.SENDING, S.FAILED),
        (S.SENT, S.DELIVERED),
        (S.SENT, S.FAILED),
        (S.FAILED, S.DELIVERED),
    }
)
# Receipts and opt-out only exist for WhatsApp; an email row can never make these changes.
WHATSAPP_ONLY_TRANSITIONS = frozenset(
    {
        (S.PENDING, S.FAILED),
        (S.SENT, S.DELIVERED),
        (S.SENT, S.FAILED),
        (S.FAILED, S.DELIVERED),
    }
)
_LOGGED = {S.FAILED: "notification_failed", S.EXPIRED: "notification_expired"}


def _create_fallback(parent: Notification, *, now: datetime) -> Notification:
    """Create the email row that replaces a failed WhatsApp row, once."""
    try:
        with transaction.atomic():
            fallback, _ = Notification.objects.get_or_create(
                fallback_of=parent,
                defaults={
                    "application_id": parent.application_id,
                    "dues_request_id": parent.dues_request_id,
                    "event": parent.event,
                    "channel": NotificationChannel.EMAIL,
                    "status": NotificationStatus.PENDING,
                    "next_attempt_at": now,
                    "expires_at": parent.expires_at,
                },
            )
    except IntegrityError:
        fallback = Notification.objects.filter(fallback_of=parent).first()
        if fallback is None:
            raise
    return fallback


def apply_transition(
    notification_id,
    *,
    to_status: str,
    expected_attempts: int | None = None,
    error_code: str = "",
    provider_message_id: str | None = None,
    recipient_masked: str = "",
    next_attempt_at: datetime | None = None,
    attempts_delta: int = 0,
    now: datetime | None = None,
) -> Notification | None:
    """Lock the row, check the change is allowed, apply it and create any fallback email.

    Returns the updated row, or None when the change is refused (a lost race, not an error).
    """
    now = now or timezone.now()
    with transaction.atomic():
        row = Notification.objects.select_for_update().filter(pk=notification_id).first()
        if row is None:
            return None
        pair = (row.status, to_status)
        if pair not in ALLOWED_TRANSITIONS:
            return None
        if pair in WHATSAPP_ONLY_TRANSITIONS and row.channel != NotificationChannel.WHATSAPP:
            return None
        if expected_attempts is not None and row.attempts != expected_attempts:
            return None

        row.status = to_status
        row.attempts += attempts_delta
        if error_code:
            row.error_code = error_code
        if provider_message_id is not None:
            row.provider_message_id = provider_message_id
        if recipient_masked:
            row.recipient_masked = recipient_masked
        if next_attempt_at is not None:
            row.next_attempt_at = next_attempt_at
        if to_status == S.SENDING:
            row.sending_started_at = now
        elif pair[0] == S.SENDING:
            row.sending_started_at = None
        if to_status == S.SENT:
            row.sent_at = now
        elif to_status == S.DELIVERED:
            row.delivered_at = now
        row.save()
        if to_status == S.FAILED and row.channel == NotificationChannel.WHATSAPP:
            _create_fallback(row, now=now)

    if to_status in _LOGGED:
        logger.warning(
            _LOGGED[to_status],
            extra={
                "notification_id": str(row.pk),
                "event": row.event,
                "channel": row.channel,
                "status": row.status,
                "error_code": row.error_code,
            },
        )
    return row
