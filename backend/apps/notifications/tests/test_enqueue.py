"""`enqueue` and the ten hooks: a committed change leaves one row, a rolled-back one none."""

import itertools
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import transaction
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory
from apps.applications import services as app_services
from apps.applications.factories import build_submittable_application
from apps.applications.models import InsuranceApplication
from apps.doctors.factories import DoctorFactory
from apps.doctors.models import Doctor
from apps.dues import services as dues_services
from apps.notifications.models import Notification
from apps.notifications.providers import (
    PermanentProviderError,
    get_email_client,
    get_whatsapp_client,
)
from apps.notifications.services import enqueue, first_channel
from apps.reference.constants import ApplicationStatus as S
from apps.reference.constants import DuesRequestStatus as DS
from apps.reference.constants import NotificationChannel as C
from apps.reference.constants import NotificationEvent as E
from apps.reference.constants import NotificationStatus as NS
from apps.reference.constants import PaymentStatus as P
from tests.files import png_upload

pytestmark = pytest.mark.django_db
_seq = itertools.count(700)
SNAPSHOT = {"total": 4835, "tier": 3, "breakdown": [], "admin_fee": 900, "service_fee": 800}


def app_in(status=S.UNDER_REVIEW, payment=P.CONFIRMED):
    app = build_submittable_application()
    InsuranceApplication.objects.filter(pk=app.pk).update(
        status=status,
        payment_status=payment,
        reference_number=None if status == S.DRAFT else f"MED-2026-{next(_seq):06d}",
        submitted_at=None if status == S.DRAFT else timezone.now(),
        fee_snapshot=None if status == S.DRAFT else SNAPSHOT,
    )
    app.refresh_from_db()
    return app


def _dues(app, admin):
    return dues_services.create_dues_request(
        app, amount=Decimal("250"), reason="اشتراك النقابة", actor=admin
    )


def _pending_dues(app, admin):
    dues = _dues(app, admin)
    dues_services.submit_dues_receipt(dues, upload=png_upload(), actor=app.doctor.user)
    dues.refresh_from_db()
    return dues


# Each preparer builds its own state and returns the action under test.
def _received(admin):
    app = app_in(S.DRAFT, P.PENDING_REVIEW)
    return lambda: app_services.transition(app, to_status=S.SUBMITTED, actor=app.doctor.user)


def _correction(admin):
    app = app_in(S.UNDER_REVIEW)
    return lambda: app_services.transition(
        app, to_status=S.NEEDS_CORRECTION, actor=admin, review_notes="ملاحظة"
    )


def _approved(admin):
    app = app_in(S.UNDER_REVIEW, P.CONFIRMED)
    return lambda: app_services.transition(app, to_status=S.APPROVED, actor=admin)


def _rejected(admin):
    app = app_in(S.SUBMITTED)
    return lambda: app_services.transition(
        app, to_status=S.REJECTED, actor=admin, review_notes="ملاحظة"
    )


def _payment_confirmed(admin):
    app = app_in(S.SUBMITTED, P.PENDING_REVIEW)
    return lambda: app_services.set_payment_status(app, status=P.CONFIRMED, actor=admin)


def _payment_rejected(admin):
    app = app_in(S.SUBMITTED, P.PENDING_REVIEW)
    return lambda: app_services.set_payment_status(
        app, status=P.REJECTED, actor=admin, reason="غير واضح"
    )


def _dues_requested(admin):
    app = app_in()
    return lambda: _dues(app, admin)


def _dues_confirmed(admin):
    dues = _pending_dues(app_in(), admin)
    receipt = dues.receipts.get()
    return lambda: dues_services.review_dues_receipt(
        dues, receipt_id=receipt.pk, decision="CONFIRMED", actor=admin
    )


def _dues_receipt_rejected(admin):
    dues = _pending_dues(app_in(), admin)
    receipt = dues.receipts.get()
    return lambda: dues_services.review_dues_receipt(
        dues, receipt_id=receipt.pk, decision="REJECTED", reason="غير واضح", actor=admin
    )


def _dues_cancelled(admin):
    dues = _dues(app_in(), admin)
    return lambda: dues_services.cancel_dues_request(dues, reason="خطأ", actor=admin)


EVENT_ACTIONS = [
    (E.APPLICATION_RECEIVED, _received),
    (E.CORRECTION_NEEDED, _correction),
    (E.APPROVED, _approved),
    (E.REJECTED, _rejected),
    (E.PAYMENT_CONFIRMED, _payment_confirmed),
    (E.PAYMENT_RECEIPT_REJECTED, _payment_rejected),
    (E.DUES_REQUESTED, _dues_requested),
    (E.DUES_CONFIRMED, _dues_confirmed),
    (E.DUES_RECEIPT_REJECTED, _dues_receipt_rejected),
    (E.DUES_CANCELLED, _dues_cancelled),
]


@pytest.fixture
def admin():
    return AdminUserFactory()


# --- first channel --------------------------------------------------------------------------------


def test_opted_in_doctor_with_valid_mobile_starts_on_whatsapp():
    doctor = DoctorFactory(phone_number="01012345678", whatsapp_opt_in=True)
    assert first_channel(doctor) == C.WHATSAPP


def test_not_opted_in_starts_on_email():
    doctor = DoctorFactory(phone_number="01012345678", whatsapp_opt_in=False)
    assert first_channel(doctor) == C.EMAIL


def test_opted_in_with_incomplete_phone_starts_on_email():
    doctor = DoctorFactory(phone_number="0101", whatsapp_opt_in=True)
    assert first_channel(doctor) == C.EMAIL


def test_expires_at_is_72_hours_after_enqueue():
    app = app_in()
    before = timezone.now()
    with transaction.atomic():
        row = enqueue(app, E.APPROVED)
    after = timezone.now()
    assert before + timedelta(hours=72) <= row.expires_at <= after + timedelta(hours=72)
    assert row.status == NS.PENDING
    assert row.created_by is None
    assert row.dues_request_id is None


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_enqueue_outside_a_transaction_is_refused():
    app = app_in()
    with pytest.raises(RuntimeError):
        enqueue(app, E.APPROVED)


def test_enqueue_rejects_a_dues_request_of_another_application(admin):
    dues = _dues(app_in(), admin)
    other = app_in()
    with pytest.raises(ValueError), transaction.atomic():
        enqueue(other, E.DUES_CANCELLED, dues_request=dues)


# --- the ten hooks --------------------------------------------------------------------------------


@pytest.mark.parametrize("event,prepare", EVENT_ACTIONS)
def test_committed_change_leaves_one_row(event, prepare, admin):
    action = prepare(admin)
    action()
    rows = Notification.objects.filter(event=event)
    assert rows.count() == 1
    assert rows.get().status == NS.PENDING


@pytest.mark.parametrize("event,prepare", EVENT_ACTIONS)
def test_rolled_back_change_leaves_no_row(event, prepare, admin):
    action = prepare(admin)
    with pytest.raises(RuntimeError), transaction.atomic():
        action()
        raise RuntimeError
    assert not Notification.objects.filter(event=event).exists()


def test_second_correction_on_one_application_sends_again(admin):
    app = app_in(S.UNDER_REVIEW)
    app_services.transition(app, to_status=S.NEEDS_CORRECTION, actor=admin, review_notes="1")
    app_services.transition(app, to_status=S.SUBMITTED, actor=app.doctor.user)
    InsuranceApplication.objects.filter(pk=app.pk).update(status=S.UNDER_REVIEW)
    app_services.transition(app, to_status=S.NEEDS_CORRECTION, actor=admin, review_notes="2")
    assert Notification.objects.filter(event=E.CORRECTION_NEEDED).count() == 2
    assert Notification.objects.filter(event=E.APPLICATION_RECEIVED).count() == 1


def test_under_review_sends_nothing(admin):
    app = app_in(S.SUBMITTED)
    app_services.transition(app, to_status=S.UNDER_REVIEW, actor=admin)
    assert not Notification.objects.exists()


def test_setting_the_same_payment_status_again_sends_nothing(admin):
    app = app_in(S.SUBMITTED, P.CONFIRMED)
    app_services.set_payment_status(app, status=P.CONFIRMED, actor=admin)
    assert not Notification.objects.exists()


def test_receipt_upload_and_removal_send_nothing():
    app = app_in(S.DRAFT, P.NOT_UPLOADED)
    app_services.mark_receipt_uploaded(app, actor=app.doctor.user)
    app_services.mark_receipt_removed(app, actor=app.doctor.user)
    assert not Notification.objects.exists()


def test_dues_rows_carry_their_dues_request(admin):
    app = app_in()
    dues = _dues(app, admin)
    row = Notification.objects.get(event=E.DUES_REQUESTED)
    assert row.dues_request_id == dues.pk
    assert row.application_id == app.pk
    assert dues.status == DS.REQUESTED


def test_row_uses_the_doctors_first_channel(admin):
    app = app_in()
    Doctor.objects.filter(pk=app.doctor_id).update(whatsapp_opt_in=True)
    app_services.transition(app, to_status=S.APPROVED, actor=admin)
    assert Notification.objects.get(event=E.APPROVED).channel == C.WHATSAPP


# --- an outage never reaches the admin action -----------------------------------------------------


@pytest.mark.parametrize("event,prepare", EVENT_ACTIONS)
def test_provider_outage_never_blocks_an_admin_action(event, prepare, admin):
    """The request path calls no provider, so an outage cannot fail or roll back the action."""
    action = prepare(admin)
    whatsapp, email = get_whatsapp_client(), get_email_client()
    whatsapp.errors = [PermanentProviderError("OUTAGE")] * 3
    email.errors = [PermanentProviderError("OUTAGE")] * 3

    action()

    assert Notification.objects.filter(event=event).count() == 1
    assert (len(whatsapp.errors), len(email.errors)) == (3, 3)  # nothing was called
    assert whatsapp.sent == [] and email.sent == []
