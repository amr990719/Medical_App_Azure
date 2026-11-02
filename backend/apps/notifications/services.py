"""Notification status changes (spec section 4). Every change goes through `apply_transition`."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.applications.models import InsuranceApplication
from apps.common.arabic import is_valid_mobile, normalize_mobile
from apps.dues.models import SyndicateDuesRequest
from apps.reference.constants import (
    ApplicationStatus,
    DuesRequestStatus,
    NotificationChannel,
    NotificationEvent,
    NotificationStatus,
    PaymentStatus,
)

from .formatting import mask_email, mask_phone
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
    expected_status: str | None = None,
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
        if expected_status is not None and row.status != expected_status:
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


MAX_ATTEMPTS = 3
RETRY_DELAYS = {1: timedelta(minutes=5), 2: timedelta(minutes=15)}
OPTED_OUT = "OPTED_OUT"
UNKNOWN_RESULT = "UNKNOWN_RESULT"


@dataclass(frozen=True)
class Claim:
    """One row this sender owns until it records an outcome. Holds the full address in memory."""

    notification_id: UUID
    attempts: int
    channel: str
    event: str
    reference_number: str
    amount: Decimal | None
    recipient: str = field(repr=False)  # full address, in memory only, never logged
    recipient_masked: str


def _recipient(row: Notification) -> str:
    """The address as it is now: the doctor's current phone (local `01...` form) or email."""
    doctor = row.application.doctor
    if row.channel == NotificationChannel.WHATSAPP:
        return normalize_mobile(doctor.phone_number) or ""
    return (doctor.email or "").strip()


def _allowlisted(row: Notification, recipient: str) -> bool:
    entries = [str(entry).strip() for entry in settings.NOTIFICATIONS_ALLOWLIST]
    if row.channel == NotificationChannel.WHATSAPP:
        return bool(recipient) and recipient in {normalize_mobile(e) for e in entries}
    return bool(recipient) and recipient.lower() in {e.lower() for e in entries if "@" in e}


def _claim_one(channel: str, now: datetime) -> tuple[bool, Claim | None]:
    """One short transaction. Returns (keep_looking, claim)."""
    with transaction.atomic():
        row = (
            Notification.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("application__doctor__user", "dues_request")
            .filter(status=S.PENDING, channel=channel, next_attempt_at__lte=now)
            .order_by("next_attempt_at", "created_at")
            .first()
        )
        if row is None:
            return False, None

        def refuse(to_status: str, **kwargs) -> tuple[bool, Claim | None]:
            apply_transition(
                row.pk, to_status=to_status, expected_attempts=row.attempts, now=now, **kwargs
            )
            return True, None

        if row.expires_at <= now:
            return refuse(S.EXPIRED)
        if not still_relevant(row):
            return refuse(S.SUPERSEDED)
        recipient = _recipient(row)
        if settings.NOTIFICATIONS_MODE == "allowlist" and not _allowlisted(row, recipient):
            return refuse(S.SUPPRESSED)
        if channel == NotificationChannel.WHATSAPP and (
            not row.application.doctor.whatsapp_opt_in or not recipient
        ):
            return refuse(S.FAILED, error_code=OPTED_OUT)

        masked = ""
        if recipient:
            masked = mask_phone(recipient) if channel == "WHATSAPP" else mask_email(recipient)
        claimed = apply_transition(
            row.pk,
            to_status=S.SENDING,
            expected_attempts=row.attempts,
            attempts_delta=1,
            now=now,
        )
        if claimed is None:
            return True, None
        return False, Claim(
            notification_id=row.pk,
            attempts=claimed.attempts,
            channel=channel,
            event=row.event,
            reference_number=row.application.reference_number or "",
            amount=row.dues_request.amount if row.dues_request_id else None,
            recipient=recipient,
            recipient_masked=masked,
        )


def claim_next(channel: str, *, now: datetime) -> Claim | None:
    """Claim the oldest due row for `channel`, settling rows that fail a check on the way.

    A row that fails a check uses no attempt and the loop moves to the next due row.
    """
    while True:
        keep_looking, claim = _claim_one(channel, now)
        if claim is not None or not keep_looking:
            return claim


def _recorded(claim: Claim, row: Notification | None) -> None:
    if row is None:
        logger.info(
            "notification_result_dropped", extra={"notification_id": str(claim.notification_id)}
        )


def record_accepted(claim: Claim, *, provider_message_id: str) -> None:
    _recorded(
        claim,
        apply_transition(
            claim.notification_id,
            to_status=S.SENT,
            expected_attempts=claim.attempts,
            expected_status=S.SENDING,
            provider_message_id=provider_message_id,
            recipient_masked=claim.recipient_masked,
        ),
    )


def record_temporary(claim: Claim, *, error_code: str, now: datetime) -> None:
    """Not accepted and worth retrying: back to PENDING while attempts are left, else FAILED."""
    delay = RETRY_DELAYS.get(claim.attempts)
    if claim.attempts >= MAX_ATTEMPTS or delay is None:
        row = apply_transition(
            claim.notification_id,
            to_status=S.FAILED,
            expected_attempts=claim.attempts,
            expected_status=S.SENDING,
            error_code=error_code,
            recipient_masked=claim.recipient_masked,
            now=now,
        )
    else:
        row = apply_transition(
            claim.notification_id,
            to_status=S.PENDING,
            expected_attempts=claim.attempts,
            expected_status=S.SENDING,
            error_code=error_code,
            recipient_masked=claim.recipient_masked,
            next_attempt_at=now + delay,
            now=now,
        )
    _recorded(claim, row)


def record_unknown(claim: Claim, *, now: datetime) -> None:
    """The request may have reached the provider. WhatsApp goes to email, email retries."""
    if claim.channel == NotificationChannel.WHATSAPP:
        row = apply_transition(
            claim.notification_id,
            to_status=S.FAILED,
            expected_attempts=claim.attempts,
            expected_status=S.SENDING,
            error_code=UNKNOWN_RESULT,
            recipient_masked=claim.recipient_masked,
            now=now,
        )
        _recorded(claim, row)
    else:
        record_temporary(claim, error_code=UNKNOWN_RESULT, now=now)


def record_permanent(claim: Claim, *, error_code: str) -> None:
    _recorded(
        claim,
        apply_transition(
            claim.notification_id,
            to_status=S.FAILED,
            expected_attempts=claim.attempts,
            expected_status=S.SENDING,
            error_code=error_code,
            recipient_masked=claim.recipient_masked,
        ),
    )
