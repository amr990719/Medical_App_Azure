"""Additional syndicate dues (مستحقات نقابية): request → receipt → review lifecycle, cancellation,
ownership, approval blocking, and separation from the treatment fee and its receipt."""

import itertools
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.applications.factories import build_submittable_application
from apps.applications.models import InsuranceApplication
from apps.applications.services import admin_allowed_transitions, transition
from apps.audit.models import AuditAction, AuditLog
from apps.common.exceptions import InvalidStatusTransition, PermissionDeniedError, ValidationFailed
from apps.documents.models import Document
from apps.dues import services
from apps.dues.models import DuesReceipt, SyndicateDuesRequest
from apps.reference.constants import ApplicationStatus as S
from apps.reference.constants import DocumentType as T
from apps.reference.constants import DuesReceiptStatus as RS
from apps.reference.constants import DuesRequestStatus as DS
from apps.reference.constants import PaymentStatus as P
from tests.files import png_upload

pytestmark = pytest.mark.django_db
_seq = itertools.count(900)

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


@pytest.fixture
def admin():
    return AdminUserFactory()


def request_dues(app, admin, amount="250.00", reason="اشتراك النقابة لعام 2026"):
    return services.create_dues_request(app, amount=Decimal(amount), reason=reason, actor=admin)


def upload_receipt(dues, actor=None):
    return services.submit_dues_receipt(
        dues, upload=png_upload(), actor=actor or dues.application.doctor.user
    )


# --- creation -------------------------------------------------------------------------------------


def test_create_records_amount_reason_and_status_without_touching_the_application(admin):
    app = app_in()
    before = InsuranceApplication.objects.values().get(pk=app.pk)
    dues = request_dues(app, admin, amount="1250.50")
    assert dues.status == DS.REQUESTED
    assert dues.amount == Decimal("1250.50")
    assert dues.reason == "اشتراك النقابة لعام 2026"
    assert dues.created_by == admin
    after = InsuranceApplication.objects.values().get(pk=app.pk)
    assert {k: v for k, v in after.items() if k != "updated_at"} == {
        k: v for k, v in before.items() if k != "updated_at"
    }
    assert AuditLog.objects.filter(
        action=AuditAction.DUES_REQUEST_CREATED, object_id=dues.pk
    ).exists()


@pytest.mark.parametrize("status", [S.SUBMITTED, S.UNDER_REVIEW, S.NEEDS_CORRECTION])
def test_create_allowed_in_active_review_states(admin, status):
    assert request_dues(app_in(status), admin).status == DS.REQUESTED


@pytest.mark.parametrize("status", [S.DRAFT, S.APPROVED, S.REJECTED])
def test_create_refused_for_drafts_and_terminal_states(admin, status):
    app = app_in(status)
    with pytest.raises(InvalidStatusTransition):
        request_dues(app, admin)
    assert not SyndicateDuesRequest.objects.exists()


@pytest.mark.parametrize("amount", ["0", "-5", "0.00", "10.005", "100000000"])
def test_amount_must_be_greater_than_zero(admin, amount):
    with pytest.raises(ValidationFailed) as error:
        request_dues(app_in(), admin, amount=amount)
    assert "amount" in error.value.fields


@pytest.mark.parametrize("reason", ["", "   "])
def test_reason_is_required(admin, reason):
    with pytest.raises(ValidationFailed) as error:
        request_dues(app_in(), admin, reason=reason)
    assert "reason" in error.value.fields


def test_only_admins_create(admin):
    app = app_in()
    for actor in (app.doctor.user, UserFactory(), None):
        with pytest.raises(PermissionDeniedError):
            request_dues(app, actor)


def test_database_refuses_non_positive_amount(admin):
    dues = request_dues(app_in(), admin)
    with pytest.raises(IntegrityError), transaction.atomic():
        SyndicateDuesRequest.objects.filter(pk=dues.pk).update(amount=Decimal("0"))


def test_multiple_requests_over_time(admin):
    app = app_in()
    first = request_dues(app, admin, amount="100")
    second = request_dues(app, admin, amount="200")
    assert set(app.dues_requests.values_list("pk", flat=True)) == {first.pk, second.pk}


# --- receipts -------------------------------------------------------------------------------------


def test_upload_marks_the_request_under_review_not_paid(admin):
    app = app_in(S.UNDER_REVIEW)
    dues = request_dues(app, admin)
    receipt = upload_receipt(dues)
    dues.refresh_from_db()
    assert dues.status == DS.PENDING_REVIEW
    assert receipt.status == RS.PENDING_REVIEW
    assert receipt.document.document_type == T.SYNDICATE_DUES_RECEIPT
    assert receipt.document.application_id == app.pk
    assert receipt.document.beneficiary_id is None
    assert receipt.document.uploaded_by == app.doctor.user
    app.refresh_from_db()
    assert app.status == S.UNDER_REVIEW  # no edit or resubmission needed


def test_upload_never_touches_the_original_receipt_or_payment_data(admin):
    app = app_in(S.UNDER_REVIEW, payment=P.PENDING_REVIEW)
    original = Document.objects.get(application=app, document_type=T.PAYMENT_RECEIPT)
    dues = request_dues(app, admin)
    receipt = upload_receipt(dues)
    services.review_dues_receipt(dues, receipt_id=receipt.pk, decision=RS.CONFIRMED, actor=admin)
    app.refresh_from_db()
    original.refresh_from_db()
    assert original.deleted_at is None
    assert app.payment_status == P.PENDING_REVIEW
    assert app.fee_snapshot == SNAPSHOT
    assert Document.objects.filter(application=app, document_type=T.PAYMENT_RECEIPT).count() == 1


def test_other_doctor_cannot_upload(admin):
    dues = request_dues(app_in(), admin)
    other = build_submittable_application().doctor.user
    with pytest.raises(PermissionDeniedError):
        upload_receipt(dues, actor=other)
    with pytest.raises(PermissionDeniedError):
        upload_receipt(dues, actor=admin)
    assert not DuesReceipt.objects.exists()


def test_no_second_upload_while_a_receipt_is_pending(admin):
    dues = request_dues(app_in(), admin)
    upload_receipt(dues)
    with pytest.raises(InvalidStatusTransition):
        upload_receipt(dues)
    assert dues.receipts.count() == 1


@pytest.mark.parametrize("status", [S.APPROVED, S.REJECTED])
def test_no_upload_once_the_application_is_terminal(admin, status):
    app = app_in(S.UNDER_REVIEW)
    dues = request_dues(app, admin)
    InsuranceApplication.objects.filter(pk=app.pk).update(status=status)
    with pytest.raises(InvalidStatusTransition):
        upload_receipt(dues)


def test_failed_upload_leaves_no_blob(admin):
    from apps.documents.storage import _memory_storage

    dues = request_dues(app_in(), admin)
    InsuranceApplication.objects.filter(pk=dues.application_id).update(status=S.APPROVED)
    with pytest.raises(InvalidStatusTransition):
        upload_receipt(dues)
    assert list(_memory_storage.list("")) == []


# --- the full flow ----------------------------------------------------------------------------


def test_request_upload_reject_reupload_confirm_keeps_every_submission(admin):
    app = app_in(S.UNDER_REVIEW)
    dues = request_dues(app, admin)

    first = upload_receipt(dues)
    services.review_dues_receipt(
        dues, receipt_id=first.pk, decision=RS.REJECTED, reason="الإيصال غير واضح", actor=admin
    )
    dues.refresh_from_db()
    first.refresh_from_db()
    assert dues.status == DS.REJECTED
    assert first.status == RS.REJECTED
    assert first.rejection_reason == "الإيصال غير واضح"
    assert first.reviewed_by == admin

    second = upload_receipt(dues)
    dues.refresh_from_db()
    assert dues.status == DS.PENDING_REVIEW
    services.review_dues_receipt(dues, receipt_id=second.pk, decision=RS.CONFIRMED, actor=admin)
    dues.refresh_from_db()
    second.refresh_from_db()
    assert dues.status == DS.CONFIRMED
    assert dues.resolved_by == admin and dues.resolved_at is not None
    assert second.status == RS.CONFIRMED

    # both submissions and both documents are preserved, none soft-deleted
    assert list(dues.receipts.order_by("created_at").values_list("pk", flat=True)) == [
        first.pk,
        second.pk,
    ]
    assert first.document.deleted_at is None and second.document.deleted_at is None
    actions = set(AuditLog.objects.filter(object_id=dues.pk).values_list("action", flat=True))
    assert {
        AuditAction.DUES_REQUEST_CREATED,
        AuditAction.DUES_RECEIPT_UPLOADED,
        AuditAction.DUES_RECEIPT_REVIEWED,
    } <= actions


def test_rejection_requires_a_reason(admin):
    dues = request_dues(app_in(), admin)
    receipt = upload_receipt(dues)
    with pytest.raises(ValidationFailed) as error:
        services.review_dues_receipt(
            dues, receipt_id=receipt.pk, decision=RS.REJECTED, reason="  ", actor=admin
        )
    assert "reason" in error.value.fields
    receipt.refresh_from_db()
    assert receipt.status == RS.PENDING_REVIEW


def test_review_needs_the_pending_receipt(admin):
    dues = request_dues(app_in(), admin)
    first = upload_receipt(dues)
    services.review_dues_receipt(
        dues, receipt_id=first.pk, decision=RS.REJECTED, reason="غير مقروء", actor=admin
    )
    upload_receipt(dues)
    with pytest.raises(InvalidStatusTransition):  # stale page: the old receipt
        services.review_dues_receipt(dues, receipt_id=first.pk, decision=RS.CONFIRMED, actor=admin)


def test_review_without_a_receipt_is_refused(admin):
    dues = request_dues(app_in(), admin)
    with pytest.raises(InvalidStatusTransition):
        services.review_dues_receipt(dues, receipt_id=None, decision=RS.CONFIRMED, actor=admin)


def test_only_admins_review(admin):
    dues = request_dues(app_in(), admin)
    receipt = upload_receipt(dues)
    with pytest.raises(PermissionDeniedError):
        services.review_dues_receipt(
            dues, receipt_id=receipt.pk, decision=RS.CONFIRMED, actor=dues.application.doctor.user
        )


@pytest.mark.parametrize("decision", [RS.PENDING_REVIEW, RS.CANCELLED, "PAID"])
def test_review_decision_must_be_confirm_or_reject(admin, decision):
    dues = request_dues(app_in(), admin)
    receipt = upload_receipt(dues)
    with pytest.raises(InvalidStatusTransition):
        services.review_dues_receipt(dues, receipt_id=receipt.pk, decision=decision, actor=admin)


def test_review_refused_once_the_application_is_terminal(admin):
    app = app_in()
    dues = request_dues(app, admin)
    receipt = upload_receipt(dues)
    InsuranceApplication.objects.filter(pk=app.pk).update(status=S.REJECTED)
    with pytest.raises(InvalidStatusTransition):
        services.review_dues_receipt(
            dues, receipt_id=receipt.pk, decision=RS.CONFIRMED, actor=admin
        )


def test_database_allows_one_pending_receipt_per_request(admin):
    dues = request_dues(app_in(), admin)
    receipt = upload_receipt(dues)
    from apps.documents.factories import DocumentFactory

    document = DocumentFactory(application=dues.application, document_type=T.SYNDICATE_DUES_RECEIPT)
    with pytest.raises(IntegrityError), transaction.atomic():
        DuesReceipt.objects.create(request=dues, document=document)
    assert receipt.status == RS.PENDING_REVIEW


# --- cancellation ---------------------------------------------------------------------------------


@pytest.mark.parametrize("with_receipt", [False, True])
def test_cancel_records_the_reason(admin, with_receipt):
    dues = request_dues(app_in(), admin)
    receipt = upload_receipt(dues) if with_receipt else None
    services.cancel_dues_request(dues, reason="تم السداد مباشرة للنقابة", actor=admin)
    dues.refresh_from_db()
    assert dues.status == DS.CANCELLED
    assert dues.cancellation_reason == "تم السداد مباشرة للنقابة"
    assert dues.resolved_by == admin
    if receipt:
        receipt.refresh_from_db()
        assert receipt.status == RS.CANCELLED  # closed unreviewed, kept in the history
        assert receipt.document.deleted_at is None
    assert AuditLog.objects.filter(
        action=AuditAction.DUES_REQUEST_CANCELLED, object_id=dues.pk
    ).exists()


def test_cancel_requires_a_reason(admin):
    dues = request_dues(app_in(), admin)
    with pytest.raises(ValidationFailed) as error:
        services.cancel_dues_request(dues, reason="", actor=admin)
    assert "reason" in error.value.fields


def test_resolved_requests_cannot_be_cancelled(admin):
    dues = request_dues(app_in(), admin)
    receipt = upload_receipt(dues)
    services.review_dues_receipt(dues, receipt_id=receipt.pk, decision=RS.CONFIRMED, actor=admin)
    with pytest.raises(InvalidStatusTransition):
        services.cancel_dues_request(dues, reason="خطأ", actor=admin)
    cancelled = request_dues(dues.application, admin)
    services.cancel_dues_request(cancelled, reason="مكرر", actor=admin)
    with pytest.raises(InvalidStatusTransition):
        services.cancel_dues_request(cancelled, reason="مرة أخرى", actor=admin)


def test_cancelled_request_takes_no_receipt(admin):
    dues = request_dues(app_in(), admin)
    services.cancel_dues_request(dues, reason="مكرر", actor=admin)
    with pytest.raises(InvalidStatusTransition):
        upload_receipt(dues)


def test_only_admins_cancel(admin):
    dues = request_dues(app_in(), admin)
    with pytest.raises(PermissionDeniedError):
        services.cancel_dues_request(dues, reason="x", actor=dues.application.doctor.user)


# --- approval -------------------------------------------------------------------------------------


@pytest.mark.parametrize("outcome", ["requested", "pending", "rejected"])
def test_unresolved_dues_block_approval(admin, outcome):
    app = app_in(S.UNDER_REVIEW, payment=P.CONFIRMED)
    dues = request_dues(app, admin)
    if outcome != "requested":
        receipt = upload_receipt(dues)
        if outcome == "rejected":
            services.review_dues_receipt(
                dues, receipt_id=receipt.pk, decision=RS.REJECTED, reason="x", actor=admin
            )
    assert S.APPROVED not in admin_allowed_transitions(app)
    with pytest.raises(InvalidStatusTransition) as error:
        transition(app, to_status=S.APPROVED, actor=admin)
    assert error.value.message == services.MSG_DUES_OUTSTANDING
    app.refresh_from_db()
    assert app.status == S.UNDER_REVIEW


def test_confirmed_and_cancelled_dues_allow_approval(admin):
    app = app_in(S.UNDER_REVIEW, payment=P.CONFIRMED)
    paid = request_dues(app, admin)
    receipt = upload_receipt(paid)
    services.review_dues_receipt(paid, receipt_id=receipt.pk, decision=RS.CONFIRMED, actor=admin)
    services.cancel_dues_request(request_dues(app, admin), reason="مكرر", actor=admin)
    assert S.APPROVED in admin_allowed_transitions(app)
    assert transition(app, to_status=S.APPROVED, actor=admin).status == S.APPROVED


def test_unpaid_treatment_fee_still_blocks_approval_after_dues_are_paid(admin):
    app = app_in(S.UNDER_REVIEW, payment=P.PENDING_REVIEW)
    dues = request_dues(app, admin)
    receipt = upload_receipt(dues)
    services.review_dues_receipt(dues, receipt_id=receipt.pk, decision=RS.CONFIRMED, actor=admin)
    with pytest.raises(InvalidStatusTransition):
        transition(app, to_status=S.APPROVED, actor=admin)


def test_outstanding_dues_do_not_block_correction_or_rejection(admin):
    app = app_in(S.UNDER_REVIEW)
    request_dues(app, admin)
    app = transition(app, to_status=S.NEEDS_CORRECTION, actor=admin, review_notes="صحح")
    assert app.status == S.NEEDS_CORRECTION


# --- actions derived from the server rules ------------------------------------------------------


def test_admin_actions_follow_the_lifecycle(admin):
    app = app_in()
    assert services.can_request_dues(app)
    dues = request_dues(app, admin)
    assert services.admin_dues_actions(dues) == ["CANCEL"]
    assert services.doctor_can_upload(dues)
    upload_receipt(dues)
    dues.refresh_from_db()
    assert services.admin_dues_actions(dues) == ["CONFIRM_RECEIPT", "REJECT_RECEIPT", "CANCEL"]
    assert not services.doctor_can_upload(dues)
    InsuranceApplication.objects.filter(pk=app.pk).update(status=S.APPROVED)
    dues.application.refresh_from_db()
    assert services.admin_dues_actions(dues) == []
    assert not services.can_request_dues(dues.application)
