"""The transition service (spec section 4): the only place a notification status changes."""

import itertools
import logging
import uuid
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.applications.tests.test_reference_numbers import run_concurrently
from apps.notifications import services
from apps.notifications.factories import NotificationFactory
from apps.notifications.models import Notification
from apps.notifications.services import apply_transition
from apps.notifications.tests.test_models import make_dues
from apps.reference.constants import NotificationStatus

ALLOWED = [
    ("PENDING", "EXPIRED"),
    ("PENDING", "SUPERSEDED"),
    ("PENDING", "SUPPRESSED"),
    ("PENDING", "FAILED"),
    ("PENDING", "SENDING"),
    ("SENDING", "SENT"),
    ("SENDING", "PENDING"),
    ("SENDING", "FAILED"),
    ("SENT", "DELIVERED"),
    ("SENT", "FAILED"),
    ("FAILED", "DELIVERED"),
]
REFUSED = [p for p in itertools.product(NotificationStatus.values, repeat=2) if p not in ALLOWED]
WHATSAPP_ONLY = [
    ("PENDING", "FAILED"),
    ("SENT", "DELIVERED"),
    ("SENT", "FAILED"),
    ("FAILED", "DELIVERED"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("start,target", ALLOWED)
def test_allowed_change_applies(start, target):
    row = NotificationFactory(status=start, channel="WHATSAPP", attempts=1)
    result = apply_transition(row.pk, to_status=target)
    assert result is not None and result.status == target
    row.refresh_from_db()
    assert row.status == target


@pytest.mark.django_db
@pytest.mark.parametrize("start,target", REFUSED)
def test_every_other_change_is_refused_and_leaves_the_row(start, target):
    row = NotificationFactory(status=start)
    assert apply_transition(row.pk, to_status=target) is None
    row.refresh_from_db()
    assert row.status == start


@pytest.mark.django_db
@pytest.mark.parametrize("start,target", WHATSAPP_ONLY)
def test_whatsapp_only_changes_are_refused_for_email(start, target):
    row = NotificationFactory(status=start, channel="EMAIL")
    assert apply_transition(row.pk, to_status=target) is None
    row.refresh_from_db()
    assert row.status == start


@pytest.mark.django_db
def test_whatsapp_failure_creates_the_email_in_the_same_transaction():
    row = NotificationFactory(status="SENT", channel="WHATSAPP")
    apply_transition(row.pk, to_status="FAILED", error_code="131026")
    email = Notification.objects.get(fallback_of=row)
    assert email.channel == "EMAIL" and email.status == "PENDING"
    assert email.expires_at == row.expires_at and email.event == row.event
    assert email.application_id == row.application_id
    assert email.dues_request_id == row.dues_request_id


@pytest.mark.django_db
def test_fallback_of_a_dues_notification_keeps_the_dues_request():
    dues = make_dues()
    row = NotificationFactory(
        status="SENT",
        channel="WHATSAPP",
        event="DUES_REQUESTED",
        application=dues.application,
        dues_request=dues,
    )
    apply_transition(row.pk, to_status="FAILED", error_code="x")
    assert Notification.objects.get(fallback_of=row).dues_request_id == dues.pk


@pytest.mark.django_db
def test_email_failure_creates_no_further_row():
    row = NotificationFactory(status="SENDING", channel="EMAIL", attempts=1)
    apply_transition(row.pk, to_status="FAILED", error_code="x")
    assert Notification.objects.count() == 1


@pytest.mark.django_db
def test_crash_while_creating_the_fallback_rolls_back_the_failure(monkeypatch):
    row = NotificationFactory(status="SENT", channel="WHATSAPP")
    monkeypatch.setattr(services, "_create_fallback", mock.Mock(side_effect=RuntimeError))
    with pytest.raises(RuntimeError):
        apply_transition(row.pk, to_status="FAILED", error_code="x")
    row.refresh_from_db()
    assert row.status == "SENT"


@pytest.mark.django_db
def test_stale_reader_cannot_turn_delivered_into_failed():
    row = NotificationFactory(status="SENT")
    apply_transition(row.pk, to_status="DELIVERED")
    assert apply_transition(row.pk, to_status="FAILED", error_code="NO_DELIVERY_RECEIPT") is None
    assert not Notification.objects.filter(fallback_of=row).exists()


@pytest.mark.django_db
def test_late_delivered_keeps_the_email_already_created():
    row = NotificationFactory(status="SENT", channel="WHATSAPP")
    apply_transition(row.pk, to_status="FAILED", error_code="NO_DELIVERY_RECEIPT")
    result = apply_transition(row.pk, to_status="DELIVERED")
    assert result is not None and result.status == "DELIVERED"
    assert Notification.objects.filter(fallback_of=row, status="PENDING").count() == 1


@pytest.mark.django_db
def test_stale_send_result_does_not_overwrite_recovery():
    row = NotificationFactory(status="SENDING", attempts=1)
    apply_transition(row.pk, to_status="FAILED", error_code="SEND_INTERRUPTED")
    assert apply_transition(row.pk, to_status="SENT", expected_attempts=1) is None


@pytest.mark.django_db
def test_wrong_attempt_number_is_refused():
    row = NotificationFactory(status="SENDING", attempts=2)
    assert apply_transition(row.pk, to_status="SENT", expected_attempts=1) is None
    row.refresh_from_db()
    assert row.status == "SENDING"


@pytest.mark.django_db
@pytest.mark.parametrize("target", ["SENT", "PENDING", "FAILED"])
def test_leaving_sending_clears_sending_started_at(target):
    row = NotificationFactory(
        status="SENDING", attempts=1, sending_started_at=timezone.now(), channel="EMAIL"
    )
    result = apply_transition(row.pk, to_status=target, expected_attempts=1)
    assert result is not None and result.sending_started_at is None
    row.refresh_from_db()
    assert row.sending_started_at is None


@pytest.mark.django_db
def test_claiming_increments_attempts_and_sets_started_at():
    now = timezone.now()
    row = NotificationFactory(status="PENDING", attempts=0)
    result = apply_transition(row.pk, to_status="SENDING", attempts_delta=1, now=now)
    assert result.attempts == 1 and result.sending_started_at == now


@pytest.mark.django_db
def test_sent_records_provider_id_recipient_and_sent_at():
    now = timezone.now()
    row = NotificationFactory(status="SENDING", attempts=1, sending_started_at=now)
    result = apply_transition(
        row.pk,
        to_status="SENT",
        provider_message_id="wamid.1",
        recipient_masked="010•••••678",
        now=now,
    )
    assert result.provider_message_id == "wamid.1"
    assert result.recipient_masked == "010•••••678" and result.sent_at == now


@pytest.mark.django_db
def test_retry_records_error_and_next_attempt():
    later = timezone.now() + timedelta(minutes=5)
    row = NotificationFactory(status="SENDING", attempts=1)
    result = apply_transition(row.pk, to_status="PENDING", error_code="TEMP", next_attempt_at=later)
    assert result.error_code == "TEMP" and result.next_attempt_at == later


@pytest.mark.django_db
def test_delivered_sets_delivered_at():
    now = timezone.now()
    row = NotificationFactory(status="SENT")
    assert apply_transition(row.pk, to_status="DELIVERED", now=now).delivered_at == now


@pytest.mark.django_db
def test_missing_row_is_refused():
    assert apply_transition(uuid.uuid4(), to_status="SENDING") is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "start,target,message",
    [("SENT", "FAILED", "notification_failed"), ("PENDING", "EXPIRED", "notification_expired")],
)
def test_failed_and_expired_log_a_warning_with_allowlisted_fields_only(
    caplog, start, target, message
):
    row = NotificationFactory(status=start, channel="WHATSAPP")
    with caplog.at_level(logging.WARNING, logger="apps.notifications"):
        apply_transition(row.pk, to_status=target, error_code="131026")
    records = [r for r in caplog.records if r.name == "apps.notifications"]
    assert [r.getMessage() for r in records] == [message]
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.notification_id == str(row.pk)
    assert record.event == row.event and record.channel == "WHATSAPP"
    assert record.status == target and record.error_code == "131026"


@pytest.mark.django_db
def test_a_refused_change_logs_nothing(caplog):
    row = NotificationFactory(status="DELIVERED")
    with caplog.at_level(logging.DEBUG, logger="apps.notifications"):
        assert apply_transition(row.pk, to_status="FAILED") is None
    assert not [r for r in caplog.records if r.name == "apps.notifications"]


@pytest.mark.django_db
def test_a_rolled_back_failure_logs_nothing(caplog, monkeypatch):
    row = NotificationFactory(status="SENT", channel="WHATSAPP")
    monkeypatch.setattr(services, "_create_fallback", mock.Mock(side_effect=RuntimeError))
    with caplog.at_level(logging.DEBUG, logger="apps.notifications"), pytest.raises(RuntimeError):
        apply_transition(row.pk, to_status="FAILED", error_code="x")
    assert not [r for r in caplog.records if r.name == "apps.notifications"]


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_webhook_and_job_race_make_one_email():
    row = NotificationFactory(status="SENT", channel="WHATSAPP")
    results = run_concurrently(
        lambda: apply_transition(row.pk, to_status="FAILED", error_code="a"),
        lambda: apply_transition(row.pk, to_status="FAILED", error_code="b"),
    )
    assert not [r for r in results if isinstance(r, Exception)]
    assert sum(r is not None for r in results) == 1
    assert Notification.objects.filter(fallback_of=row).count() == 1
