"""Notification status changes (spec section 4). Every change goes through `apply_transition`."""

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.applications.models import InsuranceApplication
from apps.common.arabic import is_valid_mobile
from apps.dues.models import SyndicateDuesRequest
from apps.reference.constants import (
    ApplicationStatus,
    DuesRequestStatus,
    NotificationChannel,
    NotificationEvent,
    NotificationStatus,
    PaymentStatus,
)

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

E = NotificationEvent


def first_channel(doctor) -> str:
    """WhatsApp when the doctor opted in and the phone is a valid mobile, otherwise email."""
    if doctor.whatsapp_opt_in and is_valid_mobile(doctor.phone_number):
        return NotificationChannel.WHATSAPP
    return NotificationChannel.EMAIL


def enqueue(
    application: InsuranceApplication,
    event: str,
    *,
    dues_request: SyndicateDuesRequest | None = None,
    created_by=None,
) -> Notification:
    """Write the notification row inside the transaction that made the change.

    Must run inside `transaction.atomic()`: the row commits or rolls back with the change.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("enqueue() must run inside the transaction that changes the source")
    if dues_request is not None and dues_request.application_id != application.pk:
        raise ValueError("dues request does not belong to this application")
    now = timezone.now()
    return Notification.objects.create(
        application=application,
        dues_request=dues_request,
        event=event,
        channel=first_channel(application.doctor),
        status=NotificationStatus.PENDING,
        next_attempt_at=now,
        expires_at=now + timedelta(hours=settings.NOTIFICATION_MAX_AGE_HOURS),
        created_by=created_by,
    )


def still_relevant(row: Notification) -> bool:
    """Re-read the source of the news: False when it no longer holds (spec section 2)."""
    event = row.event
    if event == E.CORRECTION_NEEDED:
        return _app_value(row, "status") == ApplicationStatus.NEEDS_CORRECTION
    if event == E.PAYMENT_CONFIRMED:
        return _app_value(row, "payment_status") == PaymentStatus.CONFIRMED
    if event == E.PAYMENT_RECEIPT_REJECTED:
        return _app_value(row, "payment_status") == PaymentStatus.REJECTED
    if event in (E.DUES_REQUESTED, E.DUES_RECEIPT_REJECTED):
        wanted = (
            DuesRequestStatus.REQUESTED if event == E.DUES_REQUESTED else DuesRequestStatus.REJECTED
        )
        return SyndicateDuesRequest.objects.filter(pk=row.dues_request_id, status=wanted).exists()
    return True


def _app_value(row: Notification, field: str):
    return (
        InsuranceApplication.objects.filter(pk=row.application_id)
        .values_list(field, flat=True)
        .first()
    )


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
            # Runs only if the outermost transaction commits, so a rollback logs nothing.
            extra = {
                "notification_id": str(row.pk),
                "event": row.event,
                "channel": row.channel,
                "status": row.status,
                "error_code": row.error_code,
            }
            transaction.on_commit(lambda: logger.warning(_LOGGED[to_status], extra=extra))
    return row
