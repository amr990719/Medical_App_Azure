import pytest
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.applications.factories import ApplicationFactory, build_submittable_application
from apps.applications.models import InsuranceApplication, ReferenceCounter
from apps.applications.services import (
    create_draft,
    mark_receipt_uploaded,
    set_payment_status,
    submit,
    transition,
)
from apps.audit.models import AuditAction, AuditLog
from apps.common.exceptions import (
    ActiveApplicationExists,
    ApplicationNotEditable,
    InvalidStatusTransition,
    PermissionDeniedError,
    ValidationFailed,
)
from apps.doctors.factories import DoctorFactory
from apps.doctors.models import Doctor
from apps.documents.factories import DocumentFactory
from apps.documents.models import Document
from apps.fees.models import FeeSchedule
from apps.fees.services import quote_for_application
from apps.reference.constants import ApplicationStatus as S
from apps.reference.constants import ApplicationType, DocumentType, Kinship, WorkStatus
from apps.reference.constants import PaymentStatus as P

pytestmark = pytest.mark.django_db


def actions():
    return list(AuditLog.objects.order_by("timestamp").values_list("action", flat=True))


# --- submit ---------------------------------------------------------------------------------


def test_submit_stores_fee_snapshot_matching_example_2():
    app = build_submittable_application()
    result = submit(app, actor=app.doctor.user)
    assert result.status == S.SUBMITTED
    assert result.reference_number == "MED-2026-000001"
    assert result.submitted_at is not None
    assert result.fee_snapshot["total"] == 3860
    assert result.fee_snapshot["tier"] == 3
    assert result.fee_snapshot["is_valid"] is True
    assert [line["fee"] for line in result.fee_snapshot["breakdown"]] == [825, 1100, 605, 605, 725]
    assert result.fee_schedule == FeeSchedule.objects.get(fiscal_year=2026, version=2)


def test_submit_locks_the_fee_schedule():
    app = build_submittable_application()
    submit(app, actor=app.doctor.user)
    assert FeeSchedule.objects.get(fiscal_year=2026, version=2).is_locked is True


def test_submit_writes_snapshot_and_audit():
    app = build_submittable_application()
    result = submit(app, actor=app.doctor.user)
    snapshot = result.submitted_snapshot
    assert snapshot["member"]["full_name"] == app.doctor.full_name
    assert snapshot["member"]["national_id"] == app.doctor.national_id
    assert snapshot["application"]["work_status"] == "WORKING"
    assert [b["kinship"] for b in snapshot["beneficiaries"]] == ["WIFE", "SON_MINOR", "DAUGHTER"]
    assert [b["is_first_time"] for b in snapshot["beneficiaries"]] == [False, False, False]
    assert len(snapshot["documents"]) == Document.objects.filter(application=app).count()
    assert actions() == [AuditAction.APPLICATION_SUBMITTED, AuditAction.FEE_SNAPSHOT_CREATED]
    submitted = AuditLog.objects.get(action=AuditAction.APPLICATION_SUBMITTED)
    assert submitted.metadata["reference_number"] == "MED-2026-000001"
    assert "national_id" not in str(submitted.metadata)


def test_submit_with_errors_raises_validation_failed_and_changes_nothing():
    app = build_submittable_application()
    Document.objects.filter(application=app, document_type=DocumentType.SYNDICATE_ID).update(
        deleted_at=timezone.now()
    )
    with pytest.raises(ValidationFailed) as exc:
        submit(app, actor=app.doctor.user)
    assert exc.value.fields == {"documents.SYNDICATE_ID": ["يرجى إرفاق صورة كارنيه النقابة"]}
    assert [e.step for e in exc.value.errors] == [3]
    app.refresh_from_db()
    assert (app.status, app.reference_number, app.fee_snapshot) == (S.DRAFT, None, None)
    assert not AuditLog.objects.exists()
    assert not ReferenceCounter.objects.filter(last_sequence__gt=0).exists()
    assert FeeSchedule.objects.get(fiscal_year=2026, version=2).is_locked is False


def test_resubmit_keeps_reference_number():
    app = build_submittable_application()
    first = submit(app, actor=app.doctor.user)
    transition(first, to_status=S.NEEDS_CORRECTION, actor=AdminUserFactory(),
               review_notes="الإيصال غير واضح")  # fmt: skip
    again = submit(first, actor=app.doctor.user)
    assert again.status == S.SUBMITTED
    assert again.reference_number == "MED-2026-000001"
    assert ReferenceCounter.objects.get(fiscal_year=2026).last_sequence == 1
    assert actions()[-2:] == [AuditAction.APPLICATION_RESUBMITTED, AuditAction.FEE_SNAPSHOT_CREATED]


def test_resubmission_recomputes_the_fee_snapshot():
    app = build_submittable_application()
    submit(app, actor=app.doctor.user)
    transition(app, to_status=S.NEEDS_CORRECTION, actor=AdminUserFactory(), review_notes="x")
    app.beneficiaries.filter(row_number=3).update(full_name="")  # daughter row no longer active
    again = submit(app, actor=app.doctor.user)
    # 825 + 1100 + 605 + (200 + 2 × 175): one line and one per-beneficiary admin fee fewer
    assert again.fee_snapshot["total"] == 3860 - 605 - 175 == 3080


def test_sequential_submissions_get_sequential_numbers():
    numbers = []
    for _ in range(3):
        app = build_submittable_application()
        numbers.append(submit(app, actor=app.doctor.user).reference_number)
    assert numbers == ["MED-2026-000001", "MED-2026-000002", "MED-2026-000003"]


# --- quotes ---------------------------------------------------------------------------------


def test_quote_for_draft_uses_the_active_schedule():
    quote = quote_for_application(build_submittable_application())
    assert quote.total == 3860
    assert quote.schedule_id == str(FeeSchedule.objects.get(fiscal_year=2026, is_active=True).id)


def test_addition_priced_like_first_time():
    first = build_submittable_application()
    addition = build_submittable_application(application_type=ApplicationType.ADDITION)
    assert quote_for_application(addition).total == quote_for_application(first).total == 3860


def test_tier_0_university_child_blocks_submission_with_an_arabic_error():
    app = build_submittable_application()
    Doctor.objects.filter(pk=app.doctor_id).update(syndicate_registration_year=2026)
    son = app.beneficiaries.get(row_number=2)
    son.kinship, son.birth_year = Kinship.SON_UNIVERSITY, 2005
    son.save()
    DocumentFactory(application=app, beneficiary=son, document_type=DocumentType.UNIVERSITY_ID)
    for side in (DocumentType.BENEFICIARY_NATIONAL_ID, DocumentType.BENEFICIARY_NATIONAL_ID_BACK):
        DocumentFactory(application=app, beneficiary=son, document_type=side)
    app.refresh_from_db()
    quote = quote_for_application(app)
    assert (quote.is_valid, quote.tier, quote.total) == (False, 0, 0)
    with pytest.raises(ValidationFailed) as exc:
        submit(app, actor=app.doctor.user)
    assert [(e.step, e.code) for e in exc.value.errors] == [(2, "NOT_ELIGIBLE_FOR_TIER")]
    assert "عمر أحمد محمد" in exc.value.errors[0].message
    app.refresh_from_db()
    assert (app.status, app.fee_snapshot) == (S.DRAFT, None)


def test_tier_0_application_submits_with_tier_0_pricing():
    app = build_submittable_application()
    Doctor.objects.filter(pk=app.doctor_id).update(syndicate_registration_year=2026)
    app.refresh_from_db()
    snapshot = submit(app, actor=app.doctor.user).fee_snapshot
    # 400 + wife 880 + 550 + 550 + (200 + 3 × 175)
    assert (snapshot["tier"], snapshot["is_valid"], snapshot["total"]) == (0, True, 3105)


def test_quote_for_pensioner_uses_application_work_status():
    app = build_submittable_application(work_status=WorkStatus.PENSIONER)
    assert quote_for_application(app).tier == 4


# --- drafts ---------------------------------------------------------------------------------


def test_create_draft_creates_and_audits():
    doctor = DoctorFactory()
    app = create_draft(doctor, actor=doctor.user)
    assert (app.status, app.fiscal_year, app.application_type) == (S.DRAFT, 2026, "FIRST_TIME")
    assert actions() == [AuditAction.APPLICATION_CREATED]


def test_create_draft_refuses_a_second_active_application():
    app = ApplicationFactory()
    with pytest.raises(ActiveApplicationExists):
        create_draft(app.doctor, actor=app.doctor.user)


def test_create_draft_after_rejection_is_allowed():
    app = ApplicationFactory(status=S.REJECTED, reference_number="MED-2026-000005")
    assert create_draft(app.doctor, actor=app.doctor.user).pk != app.pk


def test_create_draft_only_for_yourself():
    with pytest.raises(PermissionDeniedError):
        create_draft(DoctorFactory(), actor=UserFactory())


# --- payment status -------------------------------------------------------------------------


def test_mark_receipt_uploaded_sets_pending_review():
    app = ApplicationFactory()
    result = mark_receipt_uploaded(app, actor=app.doctor.user)
    assert result.payment_status == P.PENDING_REVIEW
    entry = AuditLog.objects.get(action=AuditAction.PAYMENT_STATUS_CHANGED)
    assert entry.metadata == {"from": "NOT_UPLOADED", "to": "PENDING_REVIEW"}


def test_mark_receipt_uploaded_requires_editable_application():
    app = ApplicationFactory(status=S.SUBMITTED, reference_number="MED-2026-000001")
    with pytest.raises(ApplicationNotEditable):
        mark_receipt_uploaded(app, actor=app.doctor.user)


@pytest.mark.parametrize("target", [P.CONFIRMED, P.REJECTED])
def test_admin_sets_payment_status(target):
    app = build_submittable_application(status=S.SUBMITTED, reference_number="MED-2026-000001")
    result = set_payment_status(app, status=target, actor=AdminUserFactory())
    assert result.payment_status == target
    assert AuditLog.objects.filter(action=AuditAction.PAYMENT_STATUS_CHANGED).count() == 1


def test_doctor_cannot_set_payment_status():
    app = build_submittable_application(status=S.SUBMITTED, reference_number="MED-2026-000001")
    with pytest.raises(PermissionDeniedError):
        set_payment_status(app, status=P.CONFIRMED, actor=app.doctor.user)
    assert InsuranceApplication.objects.get(pk=app.pk).payment_status == P.PENDING_REVIEW


@pytest.mark.parametrize(
    ("status", "payment", "target"),
    [
        (S.DRAFT, P.PENDING_REVIEW, P.CONFIRMED),  # not submitted yet
        (S.APPROVED, P.CONFIRMED, P.REJECTED),  # final decision taken
        (S.REJECTED, P.PENDING_REVIEW, P.CONFIRMED),
        (S.SUBMITTED, P.NOT_UPLOADED, P.CONFIRMED),  # nothing to confirm
        (S.SUBMITTED, P.PENDING_REVIEW, P.NOT_UPLOADED),  # server-only states
        (S.SUBMITTED, P.CONFIRMED, P.PENDING_REVIEW),
    ],
)
def test_invalid_payment_status_changes(status, payment, target):
    ref = None if status == S.DRAFT else "MED-2026-000001"
    app = build_submittable_application(status=status, payment_status=payment, reference_number=ref)
    with pytest.raises(InvalidStatusTransition):
        set_payment_status(app, status=target, actor=AdminUserFactory())
    assert not AuditLog.objects.exists()
