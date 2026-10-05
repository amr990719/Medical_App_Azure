"""Status transitions (PROMPT.md §16.2): every allowed pair succeeds, every other pair fails."""

import itertools

import pytest

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.applications.factories import build_submittable_application
from apps.applications.models import InsuranceApplication
from apps.applications.services import transition
from apps.applications.transitions import ALLOWED, allowed_targets
from apps.audit.models import AuditAction, AuditLog
from apps.common.exceptions import InvalidStatusTransition, PermissionDeniedError, ValidationFailed
from apps.reference.constants import ApplicationStatus as S
from apps.reference.constants import PaymentStatus as P

pytestmark = pytest.mark.django_db

ALLOWED_PAIRS = {
    (S.DRAFT, S.SUBMITTED),
    (S.NEEDS_CORRECTION, S.SUBMITTED),
    (S.SUBMITTED, S.UNDER_REVIEW),
    (S.SUBMITTED, S.NEEDS_CORRECTION),
    (S.UNDER_REVIEW, S.NEEDS_CORRECTION),
    (S.UNDER_REVIEW, S.APPROVED),
    (S.SUBMITTED, S.REJECTED),
    (S.UNDER_REVIEW, S.REJECTED),
}
ALL_PAIRS = set(itertools.product(S.values, S.values))
DOCTOR_TARGETS = {S.SUBMITTED}


def app_in(status, payment=P.CONFIRMED):
    fields = {"status": status, "payment_status": payment}
    if status != S.DRAFT:
        fields["reference_number"] = "MED-2026-000777"
    return build_submittable_application(**fields)


def actor_for(app, to_status):
    return app.doctor.user if to_status in DOCTOR_TARGETS else AdminUserFactory()


def test_table_is_exactly_the_specified_rows():
    assert set(ALLOWED) == ALLOWED_PAIRS


def test_allowed_targets_for_the_admin_ui():
    assert set(allowed_targets(S.UNDER_REVIEW, role="ADMIN")) == {
        S.NEEDS_CORRECTION,
        S.APPROVED,
        S.REJECTED,
    }
    assert allowed_targets(S.UNDER_REVIEW, role="DOCTOR") == []
    assert allowed_targets(S.DRAFT, role="DOCTOR") == [S.SUBMITTED]
    assert allowed_targets(S.APPROVED, role="ADMIN") == []


@pytest.mark.parametrize(("from_status", "to_status"), sorted(ALLOWED_PAIRS))
def test_every_allowed_transition_succeeds(from_status, to_status):
    app = app_in(from_status)
    result = transition(app, to_status=to_status, actor=actor_for(app, to_status),
                        review_notes="يرجى إعادة رفع البطاقة")  # fmt: skip
    assert result.status == to_status
    assert InsuranceApplication.objects.get(pk=app.pk).status == to_status


@pytest.mark.parametrize(("from_status", "to_status"), sorted(ALL_PAIRS - ALLOWED_PAIRS))
def test_every_other_pair_is_invalid(from_status, to_status):
    app = app_in(from_status)
    for actor in (app.doctor.user, AdminUserFactory()):
        with pytest.raises(InvalidStatusTransition) as exc:
            transition(app, to_status=to_status, actor=actor, review_notes="ملاحظة")
        assert exc.value.code == "INVALID_STATUS_TRANSITION"
    assert InsuranceApplication.objects.get(pk=app.pk).status == from_status
    assert not AuditLog.objects.exists()


@pytest.mark.parametrize("to_status", [S.NEEDS_CORRECTION, S.REJECTED])
@pytest.mark.parametrize("notes", ["", "   "])
def test_correction_and_rejection_require_notes(to_status, notes):
    app = app_in(S.UNDER_REVIEW)
    with pytest.raises(ValidationFailed) as exc:
        transition(app, to_status=to_status, actor=AdminUserFactory(), review_notes=notes)
    assert exc.value.fields == {"review_notes": ["يرجى كتابة ملاحظات المراجعة"]}
    assert InsuranceApplication.objects.get(pk=app.pk).status == S.UNDER_REVIEW


@pytest.mark.parametrize("payment", [P.NOT_UPLOADED, P.PENDING_REVIEW, P.REJECTED])
def test_approve_requires_confirmed_payment_and_writes_no_audit_on_failure(payment):
    # Review Focus 5.
    app = app_in(S.UNDER_REVIEW, payment=payment)
    with pytest.raises(InvalidStatusTransition) as exc:
        transition(app, to_status=S.APPROVED, actor=AdminUserFactory())
    assert exc.value.message == "لا يمكن قبول الطلب قبل تأكيد الدفع"
    assert InsuranceApplication.objects.get(pk=app.pk).status == S.UNDER_REVIEW
    assert not AuditLog.objects.exists()


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [(S.SUBMITTED, S.UNDER_REVIEW), (S.UNDER_REVIEW, S.APPROVED), (S.SUBMITTED, S.REJECTED)],
)
def test_doctor_cannot_call_admin_transition(from_status, to_status):
    app = app_in(from_status)
    with pytest.raises(PermissionDeniedError):
        transition(app, to_status=to_status, actor=app.doctor.user, review_notes="x")
    assert InsuranceApplication.objects.get(pk=app.pk).status == from_status


def test_admin_cannot_submit_on_behalf_of_a_doctor():
    app = app_in(S.DRAFT)
    with pytest.raises(PermissionDeniedError):
        transition(app, to_status=S.SUBMITTED, actor=AdminUserFactory())


def test_another_doctor_cannot_submit():
    app = app_in(S.DRAFT)
    with pytest.raises(PermissionDeniedError):
        transition(app, to_status=S.SUBMITTED, actor=UserFactory())


def test_admin_transition_records_reviewer_notes_and_audit():
    app = app_in(S.UNDER_REVIEW)
    admin = AdminUserFactory()
    result = transition(
        app, to_status=S.NEEDS_CORRECTION, actor=admin, review_notes="  صورة البطاقة غير واضحة "
    )
    assert result.review_notes == "صورة البطاقة غير واضحة"
    assert result.reviewed_by == admin
    assert result.reviewed_at is not None
    entry = AuditLog.objects.get(action=AuditAction.APPLICATION_STATUS_CHANGED)
    assert entry.user == admin
    assert entry.object_id == app.pk
    assert entry.metadata == {"from": "UNDER_REVIEW", "to": "NEEDS_CORRECTION", "notes": True}
    assert "غير واضحة" not in str(entry.metadata)
