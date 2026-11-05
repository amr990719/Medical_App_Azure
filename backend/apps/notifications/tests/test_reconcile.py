"""`manage.py reconcile_notifications`: after a database restore the outbox rows of the restored
copy may already have been sent, so they must not send a second time."""

import logging
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.notifications import sender, services
from apps.notifications.factories import NotificationFactory
from apps.notifications.models import Notification
from apps.notifications.providers import get_email_client

pytestmark = pytest.mark.django_db

RESTORED_TO = "2026-11-05T08:00:00+00:00"


@pytest.fixture(autouse=True)
def _sending_is_paused(settings):
    settings.NOTIFICATIONS_MODE = "off"


def run(*args) -> str:
    out = StringIO()
    call_command("reconcile_notifications", "--restored-to", RESTORED_TO, *args, stdout=out)
    return out.getvalue()


def in_flight_rows():
    pending = NotificationFactory(status="PENDING", channel="EMAIL")
    sending = NotificationFactory(
        status="SENDING", channel="EMAIL", attempts=1, sending_started_at=timezone.now()
    )
    return pending, sending


def statuses(*rows) -> list[str]:
    return [Notification.objects.get(pk=row.pk).status for row in rows]


def test_the_default_is_a_dry_run_that_changes_nothing():
    pending, sending = in_flight_rows()
    output = run()
    assert statuses(pending, sending) == ["PENDING", "SENDING"]
    assert "mode=dry-run" in output
    assert f"restored_to={RESTORED_TO}" in output
    assert "total=2" in output


def test_apply_ends_every_in_flight_row_in_superseded_with_the_code():
    pending, sending = in_flight_rows()
    output = run("--apply")
    assert "mode=apply" in output
    assert "total=2" in output
    for row in Notification.objects.filter(pk__in=[pending.pk, sending.pk]):
        assert row.status == "SUPERSEDED"
        assert row.error_code == "RESTORE_RECONCILED"
        assert row.sending_started_at is None


def test_finished_rows_are_left_alone():
    sent = NotificationFactory(status="SENT", channel="EMAIL")
    failed = NotificationFactory(status="FAILED", channel="EMAIL", error_code="MessageRejected")
    run("--apply")
    assert statuses(sent, failed) == ["SENT", "FAILED"]
    assert Notification.objects.get(pk=failed.pk).error_code == "MessageRejected"


def test_a_whatsapp_row_awaiting_a_receipt_cannot_later_fall_back_to_email():
    # Its timeout would make it FAILED and create an email the doctor may already have had.
    row = NotificationFactory(
        status="SENT", channel="WHATSAPP", sent_at=timezone.now() - timedelta(days=2)
    )
    run("--apply")
    assert statuses(row) == ["SUPERSEDED"]
    assert services.apply_delivery_timeout(now=timezone.now()) == 0
    assert not Notification.objects.filter(fallback_of=row).exists()


def test_no_email_fallback_is_created_for_a_whatsapp_row():
    row = NotificationFactory(status="PENDING", channel="WHATSAPP")
    run("--apply")
    assert statuses(row) == ["SUPERSEDED"]
    assert not Notification.objects.filter(fallback_of=row).exists()


@pytest.mark.parametrize("mode", ["allowlist", "live"])
@pytest.mark.parametrize("extra", [(), ("--apply",)])
def test_it_refuses_while_a_mode_can_send(settings, mode, extra):
    settings.NOTIFICATIONS_MODE = mode
    row = NotificationFactory(status="PENDING", channel="EMAIL")
    with pytest.raises(CommandError, match="NOTIFICATIONS_MODE"):
        run(*extra)
    assert statuses(row) == ["PENDING"]


@pytest.mark.parametrize("value", ["yesterday", "2026-11-05T08:00:00"])
def test_it_requires_a_restore_point_with_a_timezone(value):
    with pytest.raises(CommandError, match="restored-to"):
        call_command("reconcile_notifications", "--restored-to", value, stdout=StringIO())


def test_the_restore_point_argument_is_required():
    with pytest.raises(CommandError, match="restored-to"):
        call_command("reconcile_notifications", stdout=StringIO())


def test_apply_is_idempotent():
    in_flight_rows()
    assert "total=2" in run("--apply")
    assert "total=0" in run("--apply")


def test_a_later_run_of_the_sender_sends_nothing(settings):
    row = NotificationFactory(status="PENDING", channel="EMAIL")
    run("--apply")
    settings.NOTIFICATIONS_MODE = "live"
    summary = sender.run_once()
    assert summary.attempted == 0
    assert get_email_client().sent == []
    assert statuses(row) == ["SUPERSEDED"]


def test_an_admin_can_still_resend_a_reconciled_row_deliberately():
    row = NotificationFactory(status="PENDING", channel="EMAIL")
    run("--apply")
    new = services.resend(Notification.objects.get(pk=row.pk), actor=AdminUserFactory())
    assert new.status == "PENDING"
    assert new.pk != row.pk


def test_output_and_logs_hold_counts_only(caplog, django_capture_on_commit_callbacks):
    row = NotificationFactory(status="PENDING", channel="EMAIL", recipient_masked="a•••@x.test")
    with (
        caplog.at_level(logging.INFO, logger="apps.notifications"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        output = run("--apply")
    assert "status=PENDING event=APPLICATION_RECEIVED count=1" in output
    assert str(row.pk) not in output
    assert "a•••" not in output
    (record,) = [r for r in caplog.records if r.getMessage() == "notification_restore_reconciled"]
    assert record.reconciled == 1


def test_it_never_uses_the_messages_that_fire_alerts(caplog, django_capture_on_commit_callbacks):
    NotificationFactory(status="PENDING", channel="EMAIL")
    NotificationFactory(status="SENT", channel="WHATSAPP")
    with (
        caplog.at_level(logging.INFO, logger="apps.notifications"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        run("--apply")
    messages = {r.getMessage() for r in caplog.records}
    assert not messages & {"notification_failed", "notification_expired"}


def test_a_dry_run_logs_nothing(caplog, django_capture_on_commit_callbacks):
    NotificationFactory(status="PENDING", channel="EMAIL")
    with (
        caplog.at_level(logging.INFO, logger="apps.notifications"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        run()
    assert "notification_restore_reconciled" not in caplog.text
