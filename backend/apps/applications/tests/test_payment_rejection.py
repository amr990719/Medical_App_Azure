"""PAY-1: rejecting a payment receipt returns the application to the member for correction with
a reason the member can see (D220, refines D52).

Production failure this guards against: the admin rejected the receipt of a SUBMITTED
application, the member saw no reason and could not upload a new receipt, because the
application stayed SUBMITTED (read-only) and the dialog's note was internal only.
"""

import itertools

import pytest
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory
from apps.applications import services
from apps.applications.factories import build_submittable_application
from apps.applications.models import AdminNote, InsuranceApplication
from apps.audit.models import AuditAction, AuditLog
from apps.common.exceptions import InvalidStatusTransition, ValidationFailed
from apps.notifications.models import Notification
from apps.reference.constants import ApplicationStatus as S
from apps.reference.constants import NotificationEvent as E
from apps.reference.constants import PaymentStatus as P
from tests.files import png_upload

pytestmark = pytest.mark.django_db
_seq = itertools.count(1)
REASON = "المبلغ في الإيصال لا يطابق قيمة الاشتراك"
INTERNAL = "راجعت كشف الحساب البنكي"
MSG_REASON_REQUIRED = "يرجى كتابة سبب رفض الإيصال"


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def admin_user():
    return AdminUserFactory()


@pytest.fixture
def admin(admin_user):
    return client_for(admin_user)


def application(status=S.SUBMITTED, payment=P.PENDING_REVIEW, review_notes=""):
    app = build_submittable_application()
    InsuranceApplication.objects.filter(pk=app.pk).update(
        status=status,
        payment_status=payment,
        reference_number=f"MED-2026-{next(_seq):06d}",
        submitted_at=timezone.now(),
        fee_snapshot={"total": 4835, "tier": 3},
        review_notes=review_notes,
    )
    app.refresh_from_db()
    return app


def payment_url(app) -> str:
    return f"/api/v1/admin/applications/{app.pk}/payment/"


def reject(admin, app, reason=REASON, note=""):
    return admin.post(
        payment_url(app), {"payment_status": "REJECTED", "reason": reason, "note": note}
    )


def doctor_view(app) -> dict:
    return client_for(app.doctor.user).get(f"/api/v1/applications/{app.pk}/").json()


# --- the combined action ----------------------------------------------------------------------


@pytest.mark.parametrize("status", [S.SUBMITTED, S.UNDER_REVIEW])
def test_rejection_with_reason_requests_a_correction(admin, status):
    app = application(status)
    response = reject(admin, app)
    assert response.status_code == 200, response.json()
    body = response.json()
    assert (body["status"], body["payment_status"]) == ("NEEDS_CORRECTION", "REJECTED")
    assert body["review_notes"] == REASON
    app.refresh_from_db()
    assert (app.status, app.payment_status, app.review_notes) == (
        S.NEEDS_CORRECTION, P.REJECTED, REASON,
    )  # fmt: skip
    assert app.reviewed_by is not None and app.reviewed_at is not None


def test_rejection_is_atomic_when_the_correction_fails(admin_user, monkeypatch):
    """The payment change rolls back with a failed status transition."""
    app = application(S.SUBMITTED)

    def boom(*args, **kwargs):
        raise RuntimeError("transition failed")

    monkeypatch.setattr(services, "transition", boom)
    with pytest.raises(RuntimeError):
        services.review_payment(app, status=P.REJECTED, reason=REASON, actor=admin_user)
    app.refresh_from_db()
    assert (app.status, app.payment_status) == (S.SUBMITTED, P.PENDING_REVIEW)
    assert not AuditLog.objects.filter(action=AuditAction.PAYMENT_STATUS_CHANGED).exists()
    assert not Notification.objects.exists()


@pytest.mark.parametrize("reason", ["", "   ", "\n\t"])
def test_rejection_without_a_reason_is_400_and_changes_nothing(admin, reason):
    app = application(S.SUBMITTED)
    response = reject(admin, app, reason=reason)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["fields"]["reason"] == [MSG_REASON_REQUIRED]
    app.refresh_from_db()
    assert (app.status, app.payment_status) == (S.SUBMITTED, P.PENDING_REVIEW)
    assert not AuditLog.objects.exists()
    assert not Notification.objects.exists()


def test_rejection_without_the_reason_field_is_400(admin):
    app = application(S.SUBMITTED)
    response = admin.post(payment_url(app), {"payment_status": "REJECTED"})
    assert response.status_code == 400
    assert response.json()["error"]["fields"]["reason"] == [MSG_REASON_REQUIRED]


def test_service_refuses_a_rejection_without_reason(admin_user):
    app = application(S.UNDER_REVIEW)
    with pytest.raises(ValidationFailed):
        services.set_payment_status(app, status=P.REJECTED, actor=admin_user, reason=" ")
    app.refresh_from_db()
    assert (app.status, app.payment_status) == (S.UNDER_REVIEW, P.PENDING_REVIEW)


def test_reason_is_trimmed(admin):
    app = application(S.SUBMITTED)
    assert reject(admin, app, reason=f"  {REASON}  ").status_code == 200
    app.refresh_from_db()
    assert app.review_notes == REASON


# --- what the member sees ---------------------------------------------------------------------


def test_member_sees_the_reason_but_never_the_internal_note(admin):
    app = application(S.SUBMITTED)
    assert reject(admin, app, note=INTERNAL).status_code == 200
    view = doctor_view(app)
    assert view["status"] == "NEEDS_CORRECTION"
    assert view["payment_status"] == "REJECTED"
    assert view["review_notes"] == REASON
    assert view["is_editable"] is True
    assert INTERNAL not in str(view)
    # The internal note stays internal (D52), separate from the visible reason.
    note = AdminNote.objects.get(application=app)
    assert note.body == INTERNAL
    assert [n["body"] for n in admin.get(f"/api/v1/admin/applications/{app.pk}/notes/").json()] == [
        INTERNAL
    ]


def test_without_internal_note_no_admin_note_is_created(admin):
    app = application(S.SUBMITTED)
    assert reject(admin, app).status_code == 200
    assert not AdminNote.objects.exists()


def test_already_needs_correction_keeps_status_and_appends_the_reason(admin):
    """The open correction request may list other items still to fix, so it is kept."""
    app = application(S.NEEDS_CORRECTION, review_notes="صورة البطاقة غير واضحة")
    response = reject(admin, app)
    assert response.status_code == 200
    app.refresh_from_db()
    assert app.status == S.NEEDS_CORRECTION
    assert app.payment_status == P.REJECTED
    assert app.review_notes == f"صورة البطاقة غير واضحة\n\n{REASON}"
    assert doctor_view(app)["review_notes"] == app.review_notes
    assert not AuditLog.objects.filter(action=AuditAction.APPLICATION_STATUS_CHANGED).exists()


def test_already_needs_correction_without_notes_sets_the_reason(admin):
    app = application(S.NEEDS_CORRECTION, review_notes="")
    assert reject(admin, app).status_code == 200
    app.refresh_from_db()
    assert app.review_notes == REASON


def test_repeating_the_same_reason_does_not_duplicate_it(admin):
    app = application(S.NEEDS_CORRECTION, payment=P.REJECTED, review_notes=REASON)
    assert reject(admin, app).status_code == 200
    app.refresh_from_db()
    assert app.review_notes == REASON
    assert not Notification.objects.exists()


def test_rejected_payment_on_a_submitted_application_can_be_sent_back(admin):
    """Data left by the old behaviour (SUBMITTED + REJECTED): rejecting again with a reason now
    returns it to the member."""
    app = application(S.SUBMITTED, payment=P.REJECTED)
    response = reject(admin, app)
    assert response.status_code == 200
    app.refresh_from_db()
    assert (app.status, app.payment_status, app.review_notes) == (
        S.NEEDS_CORRECTION, P.REJECTED, REASON,
    )  # fmt: skip
    assert Notification.objects.filter(event=E.PAYMENT_RECEIPT_REJECTED).count() == 1
    assert not AuditLog.objects.filter(action=AuditAction.PAYMENT_STATUS_CHANGED).exists()


# --- replacing the receipt and resubmitting ---------------------------------------------------


def test_member_replaces_the_receipt_and_resubmits_with_the_same_reference(admin):
    app = application(S.SUBMITTED)
    reference = app.reference_number
    assert reject(admin, app).status_code == 200
    doctor = client_for(app.doctor.user)
    receipt = app.documents.get(document_type="PAYMENT_RECEIPT")

    # Remove the rejected receipt, then upload a new one.
    assert doctor.delete(f"/api/v1/documents/{receipt.pk}/").status_code == 204
    app.refresh_from_db()
    assert app.payment_status == P.NOT_UPLOADED
    response = doctor.post(
        f"/api/v1/applications/{app.pk}/documents/",
        {"file": png_upload(), "document_type": "PAYMENT_RECEIPT"},
        format="multipart",
    )
    assert response.status_code == 201, response.json()
    app.refresh_from_db()
    assert app.payment_status == P.PENDING_REVIEW

    response = doctor.post(f"/api/v1/applications/{app.pk}/submit/")
    assert response.status_code == 200, response.json()
    app.refresh_from_db()
    assert app.status == S.SUBMITTED
    assert app.payment_status == P.PENDING_REVIEW
    assert app.reference_number == reference
    assert AuditLog.objects.filter(action=AuditAction.APPLICATION_RESUBMITTED).count() == 1


def test_uploading_over_the_rejected_receipt_replaces_it(admin):
    app = application(S.UNDER_REVIEW)
    assert reject(admin, app).status_code == 200
    response = client_for(app.doctor.user).post(
        f"/api/v1/applications/{app.pk}/documents/",
        {"file": png_upload(), "document_type": "PAYMENT_RECEIPT"},
        format="multipart",
    )
    assert response.status_code == 201, response.json()
    app.refresh_from_db()
    assert app.payment_status == P.PENDING_REVIEW
    assert app.documents.filter(document_type="PAYMENT_RECEIPT").count() == 1


def test_resubmission_without_a_receipt_is_refused(admin):
    app = application(S.SUBMITTED)
    assert reject(admin, app).status_code == 200
    doctor = client_for(app.doctor.user)
    receipt = app.documents.get(document_type="PAYMENT_RECEIPT")
    assert doctor.delete(f"/api/v1/documents/{receipt.pk}/").status_code == 204
    response = doctor.post(f"/api/v1/applications/{app.pk}/submit/")
    assert response.status_code == 400
    assert response.json()["error"]["fields"]["receipt"] == ["يرجى رفع إيصال الدفع"]
    app.refresh_from_db()
    assert app.status == S.NEEDS_CORRECTION


def test_resubmission_with_the_rejected_receipt_is_refused(admin):
    app = application(S.SUBMITTED)
    assert reject(admin, app).status_code == 200
    response = client_for(app.doctor.user).post(f"/api/v1/applications/{app.pk}/submit/")
    assert response.status_code == 400
    assert response.json()["error"]["fields"]["receipt"] == [
        "تم رفض إيصال الدفع، يرجى رفع إيصال جديد"
    ]
    app.refresh_from_db()
    assert app.status == S.NEEDS_CORRECTION


# --- notification and audit -------------------------------------------------------------------


def test_one_notification_for_the_combined_action(admin):
    app = application(S.SUBMITTED)
    assert reject(admin, app).status_code == 200
    rows = Notification.objects.filter(application=app)
    assert list(rows.values_list("event", flat=True)) == [E.PAYMENT_RECEIPT_REJECTED]


def test_one_notification_when_already_needs_correction(admin):
    app = application(S.NEEDS_CORRECTION, review_notes="ملاحظة")
    assert reject(admin, app).status_code == 200
    assert list(Notification.objects.values_list("event", flat=True)) == [
        E.PAYMENT_RECEIPT_REJECTED
    ]


def test_audit_records_payment_change_and_transition_with_the_actor(admin, admin_user):
    app = application(S.UNDER_REVIEW)
    assert reject(admin, app, note=INTERNAL).status_code == 200
    payment = AuditLog.objects.get(action=AuditAction.PAYMENT_STATUS_CHANGED)
    assert payment.user_id == admin_user.pk
    assert payment.metadata == {"from": "PENDING_REVIEW", "to": "REJECTED", "reason": True}
    status = AuditLog.objects.get(action=AuditAction.APPLICATION_STATUS_CHANGED)
    assert status.user_id == admin_user.pk
    assert status.metadata == {
        "from": "UNDER_REVIEW", "to": "NEEDS_CORRECTION", "notes": True,
        "cause": "PAYMENT_REJECTED",
    }  # fmt: skip
    assert AuditLog.objects.filter(action=AuditAction.ADMIN_NOTE_ADDED).count() == 1
    # Never the free text of the reason or the note.
    for entry in AuditLog.objects.all():
        assert REASON not in str(entry.metadata) and INTERNAL not in str(entry.metadata)


def test_audit_when_already_needs_correction_records_the_visible_note(admin):
    app = application(S.NEEDS_CORRECTION, review_notes="ملاحظة")
    assert reject(admin, app).status_code == 200
    payment = AuditLog.objects.get(action=AuditAction.PAYMENT_STATUS_CHANGED)
    assert payment.metadata == {
        "from": "PENDING_REVIEW", "to": "REJECTED", "reason": True, "review_notes_updated": True,
    }  # fmt: skip


# --- unchanged paths --------------------------------------------------------------------------


@pytest.mark.parametrize("status", [S.SUBMITTED, S.UNDER_REVIEW, S.NEEDS_CORRECTION])
def test_confirming_is_unchanged(admin, status):
    app = application(status, review_notes="قديمة")
    response = admin.post(payment_url(app), {"payment_status": "CONFIRMED"})
    assert response.status_code == 200
    app.refresh_from_db()
    assert (app.status, app.payment_status, app.review_notes) == (status, P.CONFIRMED, "قديمة")
    assert list(Notification.objects.values_list("event", flat=True)) == [E.PAYMENT_CONFIRMED]
    assert not AuditLog.objects.filter(action=AuditAction.APPLICATION_STATUS_CHANGED).exists()


def test_confirming_ignores_a_reason(admin):
    app = application(S.SUBMITTED)
    response = admin.post(payment_url(app), {"payment_status": "CONFIRMED", "reason": "x"})
    assert response.status_code == 200
    app.refresh_from_db()
    assert (app.status, app.review_notes) == (S.SUBMITTED, "")


@pytest.mark.parametrize("status", [S.APPROVED, S.REJECTED])
def test_payment_changes_after_a_final_decision_are_still_refused(admin, status):
    app = application(status, payment=P.CONFIRMED)
    response = reject(admin, app)
    assert response.status_code == 409
    app.refresh_from_db()
    assert (app.status, app.payment_status) == (status, P.CONFIRMED)
    assert not Notification.objects.exists()


def test_service_refuses_after_approval(admin_user):
    app = application(S.APPROVED, payment=P.CONFIRMED)
    with pytest.raises(InvalidStatusTransition):
        services.review_payment(app, status=P.REJECTED, reason=REASON, actor=admin_user)


def test_doctor_cannot_call_the_admin_payment_endpoint():
    app = application(S.SUBMITTED)
    response = client_for(app.doctor.user).post(
        payment_url(app), {"payment_status": "REJECTED", "reason": REASON}
    )
    assert response.status_code == 403
    app.refresh_from_db()
    assert (app.status, app.payment_status) == (S.SUBMITTED, P.PENDING_REVIEW)


def test_rolled_back_rejection_leaves_no_notification(admin_user):
    app = application(S.SUBMITTED)
    with pytest.raises(RuntimeError), transaction.atomic():
        services.review_payment(app, status=P.REJECTED, reason=REASON, actor=admin_user)
        raise RuntimeError
    assert not Notification.objects.exists()
    app.refresh_from_db()
    assert app.status == S.SUBMITTED
