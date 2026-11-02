"""The scheduled job: sweeps, then sends (spec section 6)."""

import inspect
import logging
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.applications.factories import ApplicationFactory
from apps.applications.tests.test_reference_numbers import run_concurrently
from apps.dues import services as dues_services
from apps.notifications import sender, services
from apps.notifications.factories import NotificationFactory
from apps.notifications.management.commands import send_notifications as command
from apps.notifications.models import Notification
from apps.notifications.providers import (
    PermanentProviderError,
    TemporaryProviderError,
    UnknownResultError,
    get_email_client,
    get_whatsapp_client,
)
from apps.notifications.tests.test_claim import opted_in_dues
from apps.reference.constants import NotificationEvent

pytestmark = pytest.mark.django_db

PHONE = "01012345678"


def make_row(**kwargs):
    kwargs.setdefault("application__doctor__whatsapp_opt_in", True)
    return NotificationFactory(**kwargs)


def email_row(**kwargs):
    return make_row(channel="EMAIL", **kwargs)


def reload(row):
    row.refresh_from_db()
    return row


def run(**kwargs):
    return sender.run_once(now=kwargs.pop("now", timezone.now()), **kwargs)


# ---- sweeps ----


def test_order_of_a_run_expire_recover_timeout_send(monkeypatch):
    calls = []
    for name in ("expire_overdue", "recover_stuck", "apply_delivery_timeout"):
        monkeypatch.setattr(services, name, lambda *a, _n=name, **k: calls.append(_n) or 0)
    monkeypatch.setattr(
        sender, "_send_channel", lambda channel, **k: calls.append(f"send:{channel}") or None
    )
    run()
    assert calls == [
        "expire_overdue",
        "recover_stuck",
        "apply_delivery_timeout",
        "send:EMAIL",
        "send:WHATSAPP",
    ]


def test_off_mode_only_expires_and_summarises(settings, caplog):
    settings.NOTIFICATIONS_MODE = "off"
    now = timezone.now()
    stale = make_row(expires_at=now - timedelta(minutes=1))
    due = make_row()
    stuck = make_row(status="SENDING", sending_started_at=now - timedelta(minutes=30), attempts=1)
    old_sent = make_row(status="SENT", sent_at=now - timedelta(hours=2), attempts=1)
    with caplog.at_level(logging.INFO, logger="apps.notifications"):
        summary = run(now=now)
    assert reload(stale).status == "EXPIRED"
    assert (reload(due).status, reload(due).attempts) == ("PENDING", 0)
    assert reload(stuck).status == "SENDING"
    assert reload(old_sent).status == "SENT"
    assert get_whatsapp_client().sent == [] and get_email_client().sent == []
    assert summary.expired == 1
    assert [r.getMessage() for r in caplog.records if r.getMessage() == "notify_run"]


def test_stuck_whatsapp_after_10_minutes_fails_with_send_interrupted_and_email():
    now = timezone.now()
    row = make_row(status="SENDING", sending_started_at=now - timedelta(minutes=10), attempts=1)
    assert services.recover_stuck(now=now) == 1
    reload(row)
    assert (row.status, row.error_code, row.sending_started_at) == (
        "FAILED",
        "SEND_INTERRUPTED",
        None,
    )
    assert Notification.objects.get(fallback_of=row).channel == "EMAIL"


def test_stuck_email_fails_with_no_fallback():
    now = timezone.now()
    row = email_row(status="SENDING", sending_started_at=now - timedelta(minutes=11), attempts=1)
    assert services.recover_stuck(now=now) == 1
    assert (reload(row).status, row.error_code) == ("FAILED", "SEND_INTERRUPTED")
    assert not Notification.objects.filter(fallback_of=row).exists()


def test_row_sending_for_9_minutes_is_left_alone():
    now = timezone.now()
    row = make_row(status="SENDING", sending_started_at=now - timedelta(minutes=9), attempts=1)
    assert services.recover_stuck(now=now) == 0
    assert reload(row).status == "SENDING"


def test_sent_whatsapp_after_30_minutes_fails_with_no_delivery_receipt():
    now = timezone.now()
    late = make_row(status="SENT", sent_at=now - timedelta(minutes=30), attempts=1)
    fresh = make_row(status="SENT", sent_at=now - timedelta(minutes=29), attempts=1)
    assert services.apply_delivery_timeout(now=now) == 1
    assert (reload(late).status, late.error_code) == ("FAILED", "NO_DELIVERY_RECEIPT")
    assert Notification.objects.filter(fallback_of=late, channel="EMAIL").exists()
    assert reload(fresh).status == "SENT"


def test_sent_email_is_never_timed_out():
    now = timezone.now()
    row = email_row(status="SENT", sent_at=now - timedelta(days=3), attempts=1)
    assert services.apply_delivery_timeout(now=now) == 0
    assert reload(row).status == "SENT"


def test_sweeps_stop_at_500_rows():
    now = timezone.now()
    for _ in range(3):
        make_row(expires_at=now - timedelta(minutes=1))
    assert services.expire_overdue(now=now, limit=2) == 2
    assert services.expire_overdue(now=now, limit=2) == 1
    for fn in (services.expire_overdue, services.recover_stuck, services.apply_delivery_timeout):
        assert inspect.signature(fn).parameters["limit"].default == 500


# ---- sending ----


def test_email_rows_are_sent_before_whatsapp():
    wa_row = make_row()
    em_row = email_row()
    order = []
    get_email_client().send = lambda **k: order.append("email") or "e-1"
    get_whatsapp_client().send_template = lambda **k: order.append("wa") or "w-1"
    summary = run()
    assert order == ["email", "wa"]
    assert (reload(wa_row).status, reload(em_row).status) == ("SENT", "SENT")
    assert summary.sent == 2


def test_at_most_200_rows_per_run(monkeypatch):
    assert sender.MAX_ROWS == 200
    monkeypatch.setattr(sender, "MAX_ROWS", 3)
    for _ in range(5):
        email_row()
    summary = run()
    assert len(get_email_client().sent) == 3 and summary.attempted == 3
    assert Notification.objects.filter(status="PENDING", attempts=0).count() == 2


def test_stops_claiming_with_under_15_seconds_left():
    for _ in range(3):
        make_row()
    clock = {"t": 1000.0}
    wa = get_whatsapp_client()
    original = wa.send_template

    def slow(**kwargs):
        clock["t"] += 226  # 14 of the 240 seconds remain
        return original(**kwargs)

    wa.send_template = slow
    summary = run(clock=lambda: clock["t"])
    assert len(wa.sent) == 1 and summary.attempted == 1
    assert Notification.objects.filter(status="PENDING", attempts=0).count() == 2


def test_five_consecutive_errors_skip_that_provider_only():
    get_whatsapp_client().errors = [TemporaryProviderError("HTTP_500")] * 5
    wa_rows = [make_row() for _ in range(8)]
    em_rows = [email_row() for _ in range(2)]
    run()
    states = [(reload(r).status, r.attempts) for r in wa_rows]
    assert sum(1 for s in states if s == ("PENDING", 1)) == 5
    assert sum(1 for s in states if s == ("PENDING", 0)) == 3
    assert all(reload(r).status == "SENT" for r in em_rows)
    assert len(get_email_client().sent) == 2


def test_permanent_email_errors_stop_the_channel_after_five_in_a_row():
    get_email_client().errors = [PermanentProviderError("MessageRejected")] * 12
    rows = [email_row() for _ in range(12)]
    run()
    states = [(reload(r).status, r.attempts) for r in rows]
    assert sum(1 for s in states if s == ("FAILED", 1)) == 5
    assert sum(1 for s in states if s == ("PENDING", 0)) == 7


def test_bad_recipient_errors_do_not_stop_the_email_channel():
    """BadRequestException is about one address: the row fails, the streak neither moves nor resets."""
    get_email_client().errors = [PermanentProviderError("BadRequestException")] * 5
    rows = [email_row() for _ in range(6)]
    run()
    states = [reload(r).status for r in rows]
    assert states.count("FAILED") == 5 and states.count("SENT") == 1
    assert len(get_email_client().sent) == 1


def test_bad_recipient_errors_leave_the_streak_where_it_was():
    """Four outage errors, a bad address, then one more outage error: five, so the channel stops."""
    errors = [TemporaryProviderError("HTTP_500")] * 4 + [
        PermanentProviderError("BadRequestException"),
        TemporaryProviderError("HTTP_500"),
    ]
    get_email_client().errors = errors
    rows = [email_row() for _ in range(8)]
    run()
    assert sorted(reload(r).attempts for r in rows) == [0, 0, 1, 1, 1, 1, 1, 1]


def test_permanent_whatsapp_errors_keep_resetting_the_streak():
    get_whatsapp_client().errors = [PermanentProviderError("131026")] * 7
    rows = [make_row() for _ in range(7)]
    run()
    assert all(reload(r).attempts == 1 for r in rows)


def test_unknown_results_count_towards_the_streak():
    get_email_client().errors = [UnknownResultError("UNKNOWN_RESULT")] * 5
    rows = [email_row() for _ in range(7)]
    run()
    assert sorted(reload(r).attempts for r in rows) == [0, 0, 1, 1, 1, 1, 1]
    assert get_email_client().sent == []


def test_a_success_resets_the_streak():
    """Four errors, a success, four more errors: never five in a row, so every row is tried."""
    rows = [email_row() for _ in range(9)]
    failing = TemporaryProviderError("HTTP_500")
    outcomes = [failing] * 4 + [None] + [failing] * 4
    calls = []

    def scripted(**kwargs):
        outcome = outcomes[len(calls)]
        calls.append(outcome)
        if outcome is not None:
            raise outcome
        return "ok-id"

    get_email_client().send = scripted
    run()
    assert len(calls) == 9
    assert all(reload(r).attempts == 1 for r in rows)


def test_each_attempt_is_one_row_in_the_database():
    get_whatsapp_client().errors = [TemporaryProviderError("HTTP_500")]
    row = make_row()
    now = timezone.now()
    run(now=now)
    assert Notification.objects.count() == 1
    assert (reload(row).status, row.attempts, row.error_code) == ("PENDING", 1, "HTTP_500")
    assert row.next_attempt_at == now + timedelta(minutes=5)
    run(now=now + timedelta(minutes=5))
    assert (reload(row).status, row.attempts) == ("SENT", 2)
    assert Notification.objects.count() == 1


def test_whatsapp_send_uses_e164_template_and_parameters():
    dues = opted_in_dues()
    make_row(
        event=NotificationEvent.DUES_REQUESTED, dues_request=dues, application=dues.application
    )
    run()
    (sent,) = get_whatsapp_client().sent
    assert sent["to"] == "+201012345678"
    assert sent["template"] == "med_dues_requested"
    assert sent["parameters"] == [dues.application.reference_number or "", "250 ج.م"]


def test_email_row_without_address_fails_visibly():
    first = email_row()
    type(first.application.doctor.user).objects.filter(pk=first.application.doctor.user_id).update(
        email=""
    )
    second = email_row()
    summary = run()
    assert (reload(first).status, first.error_code) == ("FAILED", "NO_ADDRESS")
    assert reload(second).status == "SENT"
    assert len(get_email_client().sent) == 1
    assert summary.failed == 1


def test_a_row_that_raises_unexpectedly_does_not_stop_the_run(monkeypatch, caplog):
    first = email_row()
    second = email_row()
    real = sender.render_email
    state = {"n": 0}

    def flaky(*args, **kwargs):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("boom 01012345678")
        return real(*args, **kwargs)

    monkeypatch.setattr(sender, "render_email", flaky)
    with caplog.at_level(logging.INFO, logger="apps.notifications"):
        run()
    statuses = {reload(first).status, reload(second).status}
    assert statuses == {"FAILED", "SENT"}
    failed = first if first.status == "FAILED" else second
    assert failed.error_code == "SEND_ERROR"
    assert [
        r.notification_id for r in caplog.records if r.getMessage() == "notification_send_error"
    ] == [str(failed.pk)]
    assert "01012345678" not in caplog.text
    assert all(r.exc_info is None for r in caplog.records)


def test_permanent_error_fails_the_row_and_whatsapp_gets_an_email():
    get_whatsapp_client().errors = [PermanentProviderError("131026")]
    row = make_row()
    run()
    assert (reload(row).status, row.error_code) == ("FAILED", "131026")
    assert Notification.objects.filter(fallback_of=row).exists()


# ---- logging ----


def test_summary_logs_counts_and_oldest_age_only(caplog, django_capture_on_commit_callbacks):
    now = timezone.now()
    make_row(next_attempt_at=now - timedelta(minutes=20))
    get_whatsapp_client().errors = [TemporaryProviderError("HTTP_500")] * 5
    # Left due because the provider is skipped after the streak.
    for _ in range(5):
        make_row(next_attempt_at=now - timedelta(minutes=20))
    with caplog.at_level(logging.INFO, logger="apps.notifications"):
        run(now=now)
    (record,) = [r for r in caplog.records if r.getMessage() == "notify_run"]
    assert record.levelno == logging.INFO
    assert record.oldest_due_age_seconds == 20 * 60
    for key in ("expired", "recovered", "timed_out", "attempted", "sent"):
        assert isinstance(getattr(record, key), int)


def test_no_phone_address_or_message_text_in_any_log(caplog, django_capture_on_commit_callbacks):
    make_row()
    email_row()
    with (
        caplog.at_level(logging.DEBUG),
        django_capture_on_commit_callbacks(execute=True),
    ):
        run()
    text = caplog.text
    assert PHONE not in text and "@example.test" not in text
    assert "تم استلام" not in text


def test_command_logs_notify_run_failed_and_reraises(monkeypatch, caplog):
    def boom(**kwargs):
        raise RuntimeError("db gone")

    monkeypatch.setattr(command, "run_once", boom)
    monkeypatch.setattr(command, "_flush_telemetry", lambda: None)
    with (
        caplog.at_level(logging.INFO, logger="apps.notifications"),
        pytest.raises(RuntimeError),
    ):
        call_command("send_notifications")
    (record,) = [r for r in caplog.records if r.getMessage() == "notify_run_failed"]
    assert record.levelno == logging.ERROR


def test_command_flushes_telemetry_on_exit(monkeypatch):
    flushed = []

    class Provider:
        def force_flush(self):
            flushed.append(True)

    monkeypatch.setattr(command, "get_logger_provider", lambda: Provider())
    call_command("send_notifications")
    assert flushed == [True]


def test_command_tolerates_a_provider_without_force_flush(monkeypatch):
    monkeypatch.setattr(command, "get_logger_provider", lambda: object())
    call_command("send_notifications")


def test_command_flush_never_raises(monkeypatch):
    class Provider:
        def force_flush(self):
            raise RuntimeError("exporter down")

    monkeypatch.setattr(command, "get_logger_provider", lambda: Provider())
    call_command("send_notifications")


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_overlapping_runs_send_one_row_once():
    email_row()
    run_concurrently(sender.run_once, sender.run_once)
    assert len(get_email_client().sent) == 1
    assert Notification.objects.get().status == "SENT"


# ---- relevance across the job ----


def active_application():
    return ApplicationFactory(
        status="UNDER_REVIEW",
        reference_number="MED-2026-000777",
        doctor__whatsapp_opt_in=True,
    )


def test_cancelled_dues_never_send_the_payment_request():
    admin = AdminUserFactory()
    app = active_application()
    dues = dues_services.create_dues_request(app, amount=Decimal("1000"), reason="x", actor=admin)
    get_whatsapp_client().errors = [TemporaryProviderError("HTTP_500")]
    now = timezone.now()
    run(now=now)
    dues_services.cancel_dues_request(dues, reason="خطأ", actor=admin)
    run(now=now + timedelta(minutes=6))
    run(now=now + timedelta(minutes=30))
    sent = get_whatsapp_client().sent + get_email_client().sent
    assert not [s for s in sent if s.get("template") == "med_dues_requested"]
    assert not [s for s in sent if "مطلوب سداد" in s.get("text", "")]
    assert [s for s in sent if s.get("template") == "med_dues_cancelled"]


@pytest.mark.parametrize("mode", ["on", "", "LIVE", "disabled"])
def test_unknown_mode_does_only_what_off_does(settings, mode):
    settings.NOTIFICATIONS_MODE = mode
    stale = make_row(expires_at=timezone.now() - timedelta(minutes=1))
    due = make_row(event=NotificationEvent.APPLICATION_RECEIVED)
    run()
    assert reload(stale).status == "EXPIRED"
    assert (reload(due).status, reload(due).attempts) == ("PENDING", 0)
    assert get_whatsapp_client().sent == [] and get_email_client().sent == []


def test_rows_held_through_off_mode_pass_the_relevance_check_on_resuming(settings):
    row = make_row(event=NotificationEvent.APPLICATION_RECEIVED)
    settings.NOTIFICATIONS_MODE = "off"
    run()
    assert (reload(row).status, row.attempts) == ("PENDING", 0)
    settings.NOTIFICATIONS_MODE = "live"
    run()
    assert reload(row).status == "SENT"


def test_fallback_created_after_expiry_is_expired_on_the_next_run():
    now = timezone.now()
    row = make_row(
        status="SENT",
        attempts=1,
        sent_at=now - timedelta(minutes=45),
        expires_at=now - timedelta(minutes=5),
    )
    run(
        now=now
    )  # the timeout creates a fallback that is already overdue; the email pass expires it
    fallback = Notification.objects.get(fallback_of=row)
    assert reload(row).error_code == "NO_DELIVERY_RECEIPT"
    assert fallback.expires_at == row.expires_at and fallback.status == "EXPIRED"
    run(now=now + timedelta(minutes=5))
    assert reload(fallback).status == "EXPIRED"
    assert get_email_client().sent == []


def test_four_temporary_errors_a_no_address_row_and_one_more_stop_the_channel():
    failing = TemporaryProviderError("HTTP_500")
    get_email_client().errors = [failing] * 5
    base = timezone.now() - timedelta(hours=1)
    rows = []
    for i in range(4):
        rows.append(email_row(next_attempt_at=base + timedelta(seconds=i)))
    blank = email_row(next_attempt_at=base + timedelta(seconds=4))
    type(blank.application.doctor.user).objects.filter(pk=blank.application.doctor.user_id).update(
        email=""
    )
    rows.append(email_row(next_attempt_at=base + timedelta(seconds=5)))
    later = [email_row(next_attempt_at=base + timedelta(seconds=6 + i)) for i in range(2)]
    run()
    assert reload(blank).error_code == "NO_ADDRESS"
    assert all(reload(r).attempts == 1 for r in rows)
    assert all((reload(r).status, r.attempts) == ("PENDING", 0) for r in later)


def test_five_unexpected_errors_stop_the_channel(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("render fault")

    monkeypatch.setattr(sender, "render_email", broken)
    rows = [email_row() for _ in range(8)]
    run()
    states = [(reload(r).status, r.attempts, r.error_code) for r in rows]
    assert states.count(("FAILED", 1, "SEND_ERROR")) == 5
    assert states.count(("PENDING", 0, "")) == 3


def test_two_dues_requests_each_name_their_own_amount_on_both_channels():
    admin = AdminUserFactory()
    app = active_application()
    one = dues_services.create_dues_request(app, amount=Decimal("1000"), reason="a", actor=admin)
    dues_services.create_dues_request(app, amount=Decimal("2500"), reason="b", actor=admin)
    Notification.objects.all().delete()
    dues_services.cancel_dues_request(one, reason="خطأ", actor=admin)
    # Same news on both channels: the WhatsApp row and an email row for the same cancellation.
    cancelled = Notification.objects.get(event=NotificationEvent.DUES_CANCELLED)
    NotificationFactory(
        application=app,
        dues_request=one,
        event=NotificationEvent.DUES_CANCELLED,
        channel="EMAIL",
    )
    run()
    (wa,) = get_whatsapp_client().sent
    (em,) = get_email_client().sent
    assert cancelled.channel == "WHATSAPP"
    assert wa["parameters"][1] == "1٬000 ج.م"
    assert "1٬000 ج.م" in em["text"] and "1٬000 ج.م" in em["html"]
    assert "2٬500" not in em["text"] + em["html"] + "".join(wa["parameters"])
    assert "لا حاجة" not in em["text"] + em["html"] + em["subject"] + "".join(wa["parameters"])
    assert "لا حاجة" not in wa["template"]
