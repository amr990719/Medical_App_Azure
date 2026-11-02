"""Claiming one row at a time and recording what the provider said (spec sections 4 and 5)."""

import logging
import threading
import time
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection, transaction
from django.utils import timezone

from apps.applications.tests.test_reference_numbers import run_concurrently
from apps.notifications.factories import NotificationFactory
from apps.notifications.models import Notification
from apps.notifications.services import (
    Claim,
    claim_next,
    record_accepted,
    record_permanent,
    record_temporary,
    record_unknown,
)
from apps.notifications.tests.test_models import make_dues
from apps.reference.constants import DuesRequestStatus, NotificationEvent

pytestmark = pytest.mark.django_db

PHONE = "01012345678"


def make_row(**kwargs):
    kwargs.setdefault("application__doctor__whatsapp_opt_in", True)
    return NotificationFactory(**kwargs)


def opted_in_dues():
    dues = make_dues()
    doctor = dues.application.doctor
    doctor.whatsapp_opt_in = True
    doctor.save()
    return dues


def claim(channel="WHATSAPP"):
    return claim_next(channel, now=timezone.now())


def test_claim_sets_sending_and_increments_attempts():
    row = make_row()
    result = claim()
    assert result is not None and result.notification_id == row.pk
    assert (result.attempts, result.channel, result.event) == (1, "WHATSAPP", row.event)
    assert result.recipient == PHONE and result.recipient_masked == "010•••••678"
    assert result.reference_number == (row.application.reference_number or "")
    assert result.amount is None
    row.refresh_from_db()
    assert (row.status, row.attempts) == ("SENDING", 1)
    assert row.sending_started_at is not None


def test_claim_carries_the_dues_amount():
    dues = opted_in_dues()
    row = make_row(
        event=NotificationEvent.DUES_REQUESTED, dues_request=dues, application=dues.application
    )
    result = claim()
    assert result is not None and result.notification_id == row.pk
    assert result.amount == Decimal("250.00")


def test_claim_skips_rows_not_yet_due():
    make_row(next_attempt_at=timezone.now() + timedelta(hours=1))
    assert claim() is None


def test_claim_ignores_the_other_channel():
    make_row(channel="EMAIL")
    assert claim("WHATSAPP") is None


def test_claim_takes_oldest_first():
    now = timezone.now()
    newer = make_row(next_attempt_at=now - timedelta(minutes=1))
    older = make_row(next_attempt_at=now - timedelta(minutes=10))
    assert claim_next("WHATSAPP", now=now).notification_id == older.pk
    assert claim_next("WHATSAPP", now=now).notification_id == newer.pk


def test_claim_reads_the_current_phone_not_the_one_at_enqueue():
    row = make_row()
    doctor = row.application.doctor
    doctor.phone_number = "01112345678"
    doctor.save()
    assert claim().recipient == "01112345678"


def test_email_claim_uses_the_current_doctor_email():
    row = make_row(channel="EMAIL")
    result = claim("EMAIL")
    assert result.recipient == row.application.doctor.email
    assert result.recipient_masked.endswith("@example.test") and "•••" in result.recipient_masked


def test_email_row_with_a_blank_address_is_still_claimed():
    row = make_row(channel="EMAIL")
    user = row.application.doctor.user
    user.email = ""
    user.save()
    result = claim("EMAIL")
    assert result is not None and result.recipient == "" and result.recipient_masked == ""


def test_past_expiry_becomes_expired_and_the_next_row_is_claimed():
    now = timezone.now()
    old = make_row(next_attempt_at=now - timedelta(hours=2), expires_at=now - timedelta(hours=1))
    good = make_row(next_attempt_at=now - timedelta(minutes=1))
    assert claim_next("WHATSAPP", now=now).notification_id == good.pk
    old.refresh_from_db()
    assert (old.status, old.attempts) == ("EXPIRED", 0)


def test_irrelevant_row_becomes_superseded_with_no_fallback():
    row = make_row(event=NotificationEvent.PAYMENT_CONFIRMED)  # payment is not confirmed
    assert claim() is None
    row.refresh_from_db()
    assert (row.status, row.attempts) == ("SUPERSEDED", 0)
    assert not Notification.objects.filter(fallback_of=row).exists()


def test_allowlist_mode_suppresses_unlisted_recipient_with_no_fallback(settings):
    settings.NOTIFICATIONS_MODE = "allowlist"
    settings.NOTIFICATIONS_ALLOWLIST = ["01199999999"]
    row = make_row()
    assert claim() is None
    row.refresh_from_db()
    assert (row.status, row.attempts) == ("SUPPRESSED", 0)
    assert not Notification.objects.filter(fallback_of=row).exists()


@pytest.mark.parametrize("channel", ["WHATSAPP", "EMAIL"])
def test_allowlist_applies_to_each_channel(settings, channel):
    row = make_row(channel=channel)
    listed = "+20 1012345678" if channel == "WHATSAPP" else row.application.doctor.email.upper()
    settings.NOTIFICATIONS_MODE = "allowlist"
    settings.NOTIFICATIONS_ALLOWLIST = [listed]
    assert claim(channel).notification_id == row.pk
    other = make_row(channel=channel)
    settings.NOTIFICATIONS_ALLOWLIST = ["nobody@example.test", "01199999999"]
    assert claim(channel) is None
    other.refresh_from_db()
    assert other.status == "SUPPRESSED"


def test_allowlist_applies_to_a_fallback_email(settings):
    settings.NOTIFICATIONS_MODE = "allowlist"
    settings.NOTIFICATIONS_ALLOWLIST = ["someone-else@example.test"]
    parent = make_row(status="FAILED", error_code="131026")
    fallback = make_row(channel="EMAIL", fallback_of=parent, application=parent.application)
    assert claim("EMAIL") is None
    fallback.refresh_from_db()
    assert fallback.status == "SUPPRESSED"


def test_opt_in_withdrawn_fails_with_opted_out_and_creates_email():
    row = NotificationFactory(channel="WHATSAPP", application__doctor__whatsapp_opt_in=False)
    assert claim_next("WHATSAPP", now=timezone.now()) is None
    row.refresh_from_db()
    assert (row.status, row.error_code, row.attempts) == ("FAILED", "OPTED_OUT", 0)
    assert Notification.objects.filter(fallback_of=row, channel="EMAIL").exists()


def test_invalid_phone_at_claim_is_opted_out():
    row = make_row()
    doctor = row.application.doctor
    doctor.phone_number = "12345"
    doctor.save()
    assert claim() is None
    row.refresh_from_db()
    assert (row.status, row.error_code, row.attempts) == ("FAILED", "OPTED_OUT", 0)
    assert Notification.objects.filter(fallback_of=row, channel="EMAIL").exists()


def test_fallback_email_of_an_obsolete_message_is_superseded():
    dues = make_dues()  # the doctor has not opted in, so the WhatsApp row fails at claim
    row = make_row(
        event=NotificationEvent.DUES_REQUESTED, dues_request=dues, application=dues.application
    )
    assert claim() is None  # OPTED_OUT, email created
    dues.status = DuesRequestStatus.CANCELLED
    dues.cancellation_reason = "خطأ"
    dues.resolved_by = dues.created_by
    dues.resolved_at = timezone.now()
    dues.save()
    assert claim("EMAIL") is None
    email = Notification.objects.get(fallback_of=row)
    assert (email.status, email.attempts) == ("SUPERSEDED", 0)


def test_a_dues_request_of_a_rejected_application_is_superseded_at_claim():
    dues = opted_in_dues()
    row = make_row(
        event=NotificationEvent.DUES_REQUESTED, dues_request=dues, application=dues.application
    )
    type(dues.application).objects.filter(pk=dues.application_id).update(status="REJECTED")
    assert claim() is None
    row.refresh_from_db()
    assert (row.status, row.attempts) == ("SUPERSEDED", 0)


def test_claim_repr_hides_the_recipient():
    make_row()
    assert PHONE not in repr(claim())


# --- recording outcomes ---


def claimed(channel="WHATSAPP", **kwargs):
    row = make_row(channel=channel, **kwargs)
    return row, claim(channel)


def test_accepted_sets_sent_with_provider_id_and_masked_recipient():
    row, c = claimed()
    record_accepted(c, provider_message_id="wamid.1")
    row.refresh_from_db()
    assert (row.status, row.provider_message_id) == ("SENT", "wamid.1")
    assert row.recipient_masked == "010•••••678" and row.sent_at is not None
    assert row.sending_started_at is None


def test_temporary_error_retries_after_5_then_15_minutes():
    row, c1 = claimed()
    now = timezone.now()
    record_temporary(c1, error_code="CONNECT_FAILED", now=now)
    row.refresh_from_db()
    assert (row.status, row.error_code, row.next_attempt_at) == (
        "PENDING",
        "CONNECT_FAILED",
        now + timedelta(minutes=5),
    )
    assert claim_next("WHATSAPP", now=now) is None
    c2 = claim_next("WHATSAPP", now=now + timedelta(minutes=5))
    assert c2.attempts == 2
    record_temporary(c2, error_code="500", now=now)
    row.refresh_from_db()
    assert row.next_attempt_at == now + timedelta(minutes=15)


def test_third_temporary_error_fails_and_creates_email():
    row, c = claimed(attempts=2)
    assert c.attempts == 3
    record_temporary(c, error_code="500", now=timezone.now())
    row.refresh_from_db()
    assert (row.status, row.error_code) == ("FAILED", "500")
    assert Notification.objects.filter(fallback_of=row, channel="EMAIL").exists()


def test_unknown_result_on_whatsapp_goes_to_email_at_once():
    row, c = claimed()
    record_unknown(c, now=timezone.now())
    row.refresh_from_db()
    assert (row.status, row.error_code, row.attempts) == ("FAILED", "UNKNOWN_RESULT", 1)
    assert Notification.objects.filter(fallback_of=row, channel="EMAIL").exists()


def test_unknown_result_on_email_retries_then_fails_with_no_fallback():
    row, c = claimed("EMAIL")
    now = timezone.now()
    record_unknown(c, now=now)
    row.refresh_from_db()
    assert (row.status, row.error_code) == ("PENDING", "UNKNOWN_RESULT")
    assert row.next_attempt_at == now + timedelta(minutes=5)
    Notification.objects.filter(pk=row.pk).update(attempts=2, next_attempt_at=now)
    c3 = claim_next("EMAIL", now=now)
    assert c3.attempts == 3
    record_unknown(c3, now=now)
    row.refresh_from_db()
    assert (row.status, row.error_code) == ("FAILED", "UNKNOWN_RESULT")
    assert not Notification.objects.filter(fallback_of=row).exists()


def test_permanent_error_on_whatsapp_fails_and_creates_email():
    row, c = claimed()
    record_permanent(c, error_code="131026")
    row.refresh_from_db()
    assert (row.status, row.error_code) == ("FAILED", "131026")
    assert Notification.objects.filter(fallback_of=row, channel="EMAIL").exists()


def test_permanent_error_on_email_fails_with_no_fallback():
    row, c = claimed("EMAIL")
    record_permanent(c, error_code="NO_ADDRESS")
    row.refresh_from_db()
    assert (row.status, row.error_code) == ("FAILED", "NO_ADDRESS")
    assert not Notification.objects.filter(fallback_of=row).exists()


@pytest.mark.parametrize(
    "record",
    [
        lambda c: record_accepted(c, provider_message_id="wamid.2"),
        lambda c: record_temporary(c, error_code="500", now=timezone.now()),
        lambda c: record_unknown(c, now=timezone.now()),
        lambda c: record_permanent(c, error_code="x"),
    ],
    ids=["accepted", "temporary", "unknown", "permanent"],
)
@pytest.mark.parametrize("seeded", ["FAILED", "SENT", "PENDING"])
def test_a_stale_result_is_dropped_and_logged_by_id_only(
    caplog, django_capture_on_commit_callbacks, record, seeded
):
    row, c = claimed()
    # The attempts value still matches the claim; only the status says recovery moved on.
    Notification.objects.filter(pk=row.pk).update(status=seeded, error_code="SEND_INTERRUPTED")
    with (
        caplog.at_level(logging.INFO, logger="apps.notifications"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        record(c)
    row.refresh_from_db()
    assert (row.status, row.error_code) == (seeded, "SEND_INTERRUPTED")
    assert not Notification.objects.filter(fallback_of=row).exists()
    records = [r for r in caplog.records if r.name == "apps.notifications"]
    assert [r.getMessage() for r in records] == ["notification_result_dropped"]
    assert records[0].levelno == logging.INFO
    assert records[0].notification_id == str(row.pk)
    assert PHONE not in caplog.text


def test_a_very_long_email_address_still_records_acceptance():
    row = make_row(channel="EMAIL")
    user = row.application.doctor.user
    user.email = "a" * 60 + "@" + "d" * 63 + "." + "e" * 63 + "." + "f" * 57 + ".com"
    user.save()
    c = claim("EMAIL")
    assert len(c.recipient_masked) <= 64
    record_accepted(c, provider_message_id="ses-1")
    row.refresh_from_db()
    assert row.status == "SENT" and row.recipient_masked == c.recipient_masked


def test_a_result_from_an_older_claim_is_dropped():
    row, c = claimed()
    Notification.objects.filter(pk=row.pk).update(attempts=2)
    record_accepted(c, provider_message_id="wamid.3")
    row.refresh_from_db()
    assert row.status == "SENDING"


# --- concurrency ---


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_safety_two_workers_on_one_row_make_one_claim():
    make_row()
    now = timezone.now()
    a, b = run_concurrently(
        lambda: claim_next("WHATSAPP", now=now), lambda: claim_next("WHATSAPP", now=now)
    )
    assert sum(isinstance(c, Claim) for c in (a, b)) == 1, (a, b)
    assert Notification.objects.get().attempts == 1


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_progress_a_locked_row_does_not_block_another():
    now = timezone.now()
    row_a = make_row(next_attempt_at=now - timedelta(minutes=10))
    row_b = make_row(next_attempt_at=now - timedelta(minutes=5))
    locked, release = threading.Event(), threading.Event()

    def hold():
        try:
            with transaction.atomic():
                Notification.objects.select_for_update().get(pk=row_a.pk)
                locked.set()
                release.wait(timeout=6)
        finally:
            connection.close()

    holder = threading.Thread(target=hold)
    holder.start()
    try:
        assert locked.wait(timeout=5)
        started = time.monotonic()
        result = claim_next("WHATSAPP", now=now)
        elapsed = time.monotonic() - started
    finally:
        release.set()
        holder.join(timeout=10)
    assert isinstance(result, Claim) and result.notification_id == row_b.pk
    assert elapsed < 2
