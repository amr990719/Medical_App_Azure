import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.factories import AdminUserFactory
from apps.applications.factories import ApplicationFactory
from apps.audit.models import AuditAction, AuditLog
from apps.dues.models import SyndicateDuesRequest
from apps.notifications.factories import NotificationFactory
from apps.notifications.models import Notification
from apps.reference.constants import ApplicationStatus as AS
from apps.reference.constants import DuesRequestStatus, PaymentStatus
from apps.reference.constants import NotificationChannel as C
from apps.reference.constants import NotificationEvent as E
from apps.reference.constants import NotificationStatus as S

pytestmark = pytest.mark.django_db

HISTORY_KEYS = {
    "id",
    "event",
    "channel",
    "status",
    "recipient_masked",
    "error_code",
    "attempts",
    "fallback_of",
    "created_by_email",
    "created_at",
    "sent_at",
    "delivered_at",
}


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def admin():
    return AdminUserFactory()


@pytest.fixture
def app():
    return ApplicationFactory(status=AS.SUBMITTED, reference_number="MED-2026-000123")


def history_url(app):
    return f"/api/v1/admin/applications/{app.pk}/notifications/"


def resend_url(app, notification):
    return f"/api/v1/admin/applications/{app.pk}/notifications/{notification.pk}/resend/"


def failed(app, **kwargs):
    defaults = {
        "application": app,
        "event": E.APPLICATION_RECEIVED,
        "channel": C.EMAIL,
        "status": S.FAILED,
        "error_code": "X",
    }
    return NotificationFactory(**{**defaults, **kwargs})


def test_history_lists_newest_first_with_safe_fields_only(admin, app):
    old = failed(app, provider_message_id="wamid.secret")
    new = failed(app, event=E.CORRECTION_NEEDED)
    Notification.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))
    response = client_for(admin).get(history_url(app))
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert [row["id"] for row in body] == [str(new.pk), str(old.pk)]
    assert set(body[0]) == HISTORY_KEYS


def test_history_never_exposes_provider_message_id(admin, app):
    failed(app, provider_message_id="wamid.secret")
    text = client_for(admin).get(history_url(app)).content.decode()
    assert "wamid.secret" not in text
    assert "provider_message_id" not in text


def test_history_shows_creator_and_fallback_link(admin, app):
    parent = failed(app, channel=C.WHATSAPP)
    child = failed(app, fallback_of=parent, created_by=admin)
    rows = {r["id"]: r for r in client_for(admin).get(history_url(app)).json()}
    assert rows[str(child.pk)]["fallback_of"] == str(parent.pk)
    assert rows[str(child.pk)]["created_by_email"] == admin.email
    assert rows[str(parent.pk)]["created_by_email"] is None


def test_doctor_cannot_read_or_resend(app):
    row = failed(app)
    client = client_for(app.doctor.user)
    assert client.get(history_url(app)).status_code == 403
    assert client.post(resend_url(app, row)).status_code == 403


def test_anonymous_is_refused(app):
    row = failed(app)
    client = APIClient()
    assert client.get(history_url(app)).status_code in (401, 403)
    assert client.post(resend_url(app, row)).status_code in (401, 403)


def test_foreign_application_is_404(admin):
    url = f"/api/v1/admin/applications/{uuid.uuid4()}/notifications/"
    assert client_for(admin).get(url).status_code == 404


def test_draft_application_is_404(admin):
    draft = ApplicationFactory(status=AS.DRAFT)
    row = failed(draft)
    client = client_for(admin)
    assert client.get(history_url(draft)).status_code == 404
    assert client.post(resend_url(draft, row)).status_code == 404


def test_notification_of_another_application_is_404(admin, app):
    other = ApplicationFactory(status=AS.SUBMITTED, reference_number="MED-2026-000124")
    row = failed(other)
    assert client_for(admin).post(resend_url(app, row)).status_code == 404
    assert Notification.objects.count() == 1


def test_resend_creates_a_row_with_new_expiry_creator_and_audit(admin, app):
    old = failed(app, expires_at=timezone.now() - timedelta(hours=1))
    response = client_for(admin).post(resend_url(app, old))
    assert response.status_code == 201, response.json()
    body = response.json()
    assert set(body) == HISTORY_KEYS
    new = Notification.objects.get(pk=body["id"])
    assert new.pk != old.pk
    assert (new.event, new.status, new.created_by) == (old.event, S.PENDING, admin)
    assert abs(new.expires_at - (timezone.now() + timedelta(hours=72))) < timedelta(minutes=1)
    entry = AuditLog.objects.get(action=AuditAction.NOTIFICATION_RESENT)
    assert entry.user == admin
    assert entry.object_id == new.pk
    assert entry.metadata == {
        "application_id": str(app.pk),
        "source_notification_id": str(old.pk),
    }


def test_resend_reruns_routing(admin, app):
    old = failed(app, channel=C.WHATSAPP)
    assert app.doctor.whatsapp_opt_in is False  # opted out since
    response = client_for(admin).post(resend_url(app, old))
    assert response.status_code == 201
    assert response.json()["channel"] == C.EMAIL


@pytest.mark.parametrize("blocking", ["PENDING", "SENDING"])
def test_resend_conflicts_with_an_active_row(admin, app, blocking):
    old = failed(app)
    NotificationFactory(application=app, event=old.event, channel=C.EMAIL, status=blocking)
    response = client_for(admin).post(resend_url(app, old))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOTIFICATION_CONFLICT"
    assert Notification.objects.count() == 2
    assert not AuditLog.objects.filter(action=AuditAction.NOTIFICATION_RESENT).exists()


def test_resend_conflicts_with_whatsapp_sent_inside_the_timeout(admin, app):
    old = failed(app)
    NotificationFactory(
        application=app,
        event=old.event,
        channel=C.WHATSAPP,
        status=S.SENT,
        sent_at=timezone.now() - timedelta(minutes=5),
    )
    response = client_for(admin).post(resend_url(app, old))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOTIFICATION_CONFLICT"


def test_resend_allowed_after_the_timeout(admin, app):
    old = failed(app)
    NotificationFactory(
        application=app,
        event=old.event,
        channel=C.WHATSAPP,
        status=S.SENT,
        sent_at=timezone.now() - timedelta(minutes=31),
    )
    assert client_for(admin).post(resend_url(app, old)).status_code == 201


def test_resend_allowed_for_delivered_rows(admin, app):
    delivered = failed(app, channel=C.WHATSAPP, status=S.DELIVERED, error_code="")
    assert client_for(admin).post(resend_url(app, delivered)).status_code == 201


def test_dues_requests_do_not_block_each_other(admin, app):
    def rejected_dues():
        return SyndicateDuesRequest.objects.create(
            application=app,
            amount=Decimal("250"),
            reason="سبب",
            created_by=admin,
            status=DuesRequestStatus.REJECTED,
        )

    a, b = rejected_dues(), rejected_dues()
    old = failed(app, event=E.DUES_RECEIPT_REJECTED, dues_request=a)
    NotificationFactory(
        application=app,
        event=E.DUES_RECEIPT_REJECTED,
        dues_request=b,
        channel=C.EMAIL,
        status=S.PENDING,
    )
    response = client_for(admin).post(resend_url(app, old))
    assert response.status_code == 201
    assert Notification.objects.get(pk=response.json()["id"]).dues_request_id == a.pk


def test_resend_of_obsolete_action_is_409_not_relevant(admin, app):
    old = failed(app, event=E.PAYMENT_CONFIRMED)  # payment is not confirmed any more
    assert app.payment_status != PaymentStatus.CONFIRMED
    response = client_for(admin).post(resend_url(app, old))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOTIFICATION_NOT_RELEVANT"
    assert Notification.objects.count() == 1


def test_resend_is_throttled_per_admin(admin, app):
    cache.clear()
    old = failed(app)
    client = client_for(admin)
    try:
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"notification_resend": "1/min"}):
            first = client.post(resend_url(app, old)).status_code
            second = client.post(resend_url(app, old)).status_code
    finally:
        cache.clear()
    assert first == 201
    assert second == 429
