"""Notification table constraints (spec section 3). The database is the second line of defence
behind the services built on this model."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.factories import AdminUserFactory
from apps.applications.factories import ApplicationFactory
from apps.doctors.factories import DoctorFactory
from apps.dues.models import SyndicateDuesRequest
from apps.notifications.factories import NotificationFactory
from apps.notifications.models import DUES_EVENTS, Notification
from apps.reference.constants import (
    NotificationChannel,
    NotificationEvent,
    NotificationStatus,
)

pytestmark = pytest.mark.django_db


def make_dues(application=None) -> SyndicateDuesRequest:
    application = application or ApplicationFactory()
    return SyndicateDuesRequest.objects.create(
        application=application,
        amount=Decimal("250.00"),
        reason="اشتراك النقابة",
        created_by=AdminUserFactory(),
    )


def test_dues_events_are_the_last_four():
    assert (
        frozenset(
            {
                NotificationEvent.DUES_REQUESTED,
                NotificationEvent.DUES_CONFIRMED,
                NotificationEvent.DUES_RECEIPT_REJECTED,
                NotificationEvent.DUES_CANCELLED,
            }
        )
        == DUES_EVENTS
    )


def test_factory_defaults_create_a_pending_whatsapp_row():
    n = NotificationFactory()
    assert n.event == NotificationEvent.APPLICATION_RECEIVED
    assert n.channel == NotificationChannel.WHATSAPP
    assert n.status == NotificationStatus.PENDING
    assert n.attempts == 0
    assert n.provider_message_id is None
    assert (n.expires_at - n.next_attempt_at).total_seconds() == pytest.approx(72 * 3600, abs=5)


def test_dues_event_requires_a_dues_request():
    with pytest.raises(IntegrityError), transaction.atomic():
        NotificationFactory(event=NotificationEvent.DUES_REQUESTED, dues_request=None)


def test_dues_event_with_a_dues_request_is_accepted():
    app = ApplicationFactory()
    n = NotificationFactory(
        application=app, event=NotificationEvent.DUES_REQUESTED, dues_request=make_dues(app)
    )
    assert n.dues_request is not None


def test_non_dues_event_refuses_a_dues_request():
    app = ApplicationFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        NotificationFactory(
            application=app, event=NotificationEvent.APPROVED, dues_request=make_dues(app)
        )


def test_fallback_row_must_be_email():
    parent = NotificationFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        NotificationFactory(
            application=parent.application, channel=NotificationChannel.WHATSAPP, fallback_of=parent
        )


def test_email_fallback_row_is_accepted():
    parent = NotificationFactory()
    child = NotificationFactory(
        application=parent.application, channel=NotificationChannel.EMAIL, fallback_of=parent
    )
    assert parent.fallback == child


def test_one_email_per_parent():
    parent = NotificationFactory()
    NotificationFactory(
        application=parent.application, channel=NotificationChannel.EMAIL, fallback_of=parent
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        NotificationFactory(
            application=parent.application, channel=NotificationChannel.EMAIL, fallback_of=parent
        )


def test_provider_id_unique_per_channel():
    NotificationFactory(channel=NotificationChannel.WHATSAPP, provider_message_id="x")
    NotificationFactory(channel=NotificationChannel.EMAIL, provider_message_id="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        NotificationFactory(channel=NotificationChannel.WHATSAPP, provider_message_id="x")


def test_null_provider_ids_do_not_conflict():
    NotificationFactory(provider_message_id=None)
    NotificationFactory(provider_message_id=None)
    assert Notification.objects.filter(provider_message_id__isnull=True).count() == 2


@pytest.mark.parametrize("field", ["event", "channel", "status"])
def test_invalid_choice_refused_by_check_constraint(field):
    with pytest.raises(IntegrityError), transaction.atomic():
        NotificationFactory(**{field: "BOGUS"})


def test_doctor_opt_in_defaults_to_false():
    doctor = DoctorFactory()
    doctor.refresh_from_db()
    assert doctor.whatsapp_opt_in is False
    assert doctor.whatsapp_opt_in_at is None
    assert doctor.whatsapp_help_sent_at is None


def test_audit_actions_exist():
    from apps.audit.models import AuditAction

    assert AuditAction.WHATSAPP_OPT_IN_CHANGED == "WHATSAPP_OPT_IN_CHANGED"
    assert AuditAction.NOTIFICATION_RESENT == "NOTIFICATION_RESENT"
