"""Email-first operation: with `WHATSAPP_ENABLED` off, email is the only channel in use."""

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory
from apps.applications import services as app_services
from apps.common.exceptions import ValidationFailed
from apps.doctors.factories import DoctorFactory
from apps.doctors.models import Doctor
from apps.doctors.services import set_whatsapp_opt_in, whatsapp_available
from apps.notifications import providers, sender
from apps.notifications.factories import NotificationFactory
from apps.notifications.models import Notification
from apps.notifications.services import claim_next, first_channel
from apps.notifications.tests.test_enqueue import app_in
from apps.reference.constants import ApplicationStatus as S
from apps.reference.constants import NotificationChannel as C
from apps.reference.constants import NotificationEvent as E

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def whatsapp_off(settings):
    settings.WHATSAPP_ENABLED = False


def pending_whatsapp_row():
    return NotificationFactory(channel=C.WHATSAPP, application__doctor__whatsapp_opt_in=True)


def forbid_whatsapp_client(monkeypatch):
    """Tests run on the fakes, so building the fake is the same event as building a real client."""

    def boom(self):
        raise AssertionError("a WhatsApp client was built")

    monkeypatch.setattr(providers.FakeWhatsAppClient, "__init__", boom)


def test_first_channel_is_email_whatever_the_opt_in():
    doctor = DoctorFactory(phone_number="01012345678", whatsapp_opt_in=True)
    assert first_channel(doctor) == C.EMAIL


def test_an_event_for_an_opted_in_doctor_creates_an_email_row():
    app = app_in(S.UNDER_REVIEW)
    Doctor.objects.filter(pk=app.doctor_id).update(whatsapp_opt_in=True, phone_number="01012345678")
    app_services.transition(app, to_status=S.APPROVED, actor=AdminUserFactory())
    assert Notification.objects.get(event=E.APPROVED).channel == C.EMAIL


def test_whatsapp_is_unavailable_in_live_mode(settings):
    settings.NOTIFICATIONS_MODE = "live"
    assert whatsapp_available() is False


def test_opting_in_is_refused_but_opting_out_works(settings):
    settings.NOTIFICATIONS_MODE = "live"
    doctor = DoctorFactory()
    with pytest.raises(ValidationFailed):
        set_whatsapp_opt_in(doctor, enabled=True, actor=doctor.user)
    Doctor.objects.filter(pk=doctor.pk).update(whatsapp_opt_in=True)
    doctor.refresh_from_db()
    assert set_whatsapp_opt_in(doctor, enabled=False, actor=doctor.user).whatsapp_opt_in is False


def test_the_notifications_endpoint_reports_unavailable(settings):
    settings.NOTIFICATIONS_MODE = "live"
    doctor = DoctorFactory()
    client = APIClient()
    client.force_authenticate(doctor.user)
    assert client.get("/api/v1/profile/notifications/").json()["whatsapp_available"] is False


def test_a_pending_whatsapp_row_is_failed_with_no_attempt_and_falls_back(monkeypatch):
    forbid_whatsapp_client(monkeypatch)
    row = pending_whatsapp_row()
    assert claim_next(C.WHATSAPP, now=timezone.now()) is None
    row.refresh_from_db()
    assert (row.status, row.error_code, row.attempts) == ("FAILED", "WHATSAPP_DISABLED", 0)
    assert Notification.objects.filter(fallback_of=row, channel=C.EMAIL, status="PENDING").exists()


def test_run_once_sends_the_fallback_email_and_never_touches_whatsapp(monkeypatch):
    forbid_whatsapp_client(monkeypatch)
    row = pending_whatsapp_row()
    summary = sender.run_once(now=timezone.now())
    fallback = Notification.objects.get(fallback_of=row)
    assert fallback.status == "SENT" and summary.sent == 1
    assert providers.get_email_client().sent[0]["to"] == row.application.doctor.email


def test_live_run_sends_an_email_without_a_whatsapp_call(monkeypatch, settings):
    settings.NOTIFICATIONS_MODE = "live"
    forbid_whatsapp_client(monkeypatch)
    row = NotificationFactory(channel=C.EMAIL)
    sender.run_once(now=timezone.now())
    row.refresh_from_db()
    assert row.status == "SENT"
    assert len(providers.get_email_client().sent) == 1


def test_allowlist_suppresses_an_unlisted_fallback_and_sends_a_listed_one(monkeypatch, settings):
    settings.NOTIFICATIONS_MODE = "allowlist"
    forbid_whatsapp_client(monkeypatch)
    unlisted = pending_whatsapp_row()
    settings.NOTIFICATIONS_ALLOWLIST = ["nobody@example.test"]
    sender.run_once(now=timezone.now())
    unlisted.refresh_from_db()
    assert unlisted.status == "FAILED"
    assert Notification.objects.get(fallback_of=unlisted).status == "SUPPRESSED"

    listed = pending_whatsapp_row()
    settings.NOTIFICATIONS_ALLOWLIST = [listed.application.doctor.email]
    sender.run_once(now=timezone.now())
    assert Notification.objects.get(fallback_of=listed).status == "SENT"
