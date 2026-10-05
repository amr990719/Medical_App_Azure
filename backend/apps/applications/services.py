"""Application lifecycle services: drafts, the single transition entry point, submission with
fee snapshot and atomic reference numbers, and payment status (PROMPT.md §16, §17.5, §18).

Every mutation locks the application row (SELECT ... FOR UPDATE) first, so concurrent requests
for the same application are serialized and re-checked against the committed state.
"""

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.exceptions import (
    ActiveApplicationExists,
    InvalidStatusTransition,
    PermissionDeniedError,
    ValidationFailed,
)
from apps.fees.models import FeeSchedule
from apps.fees.services import NoActiveFeeSchedule, active_schedule, quote_for_application
from apps.reference.constants import ApplicationStatus, ApplicationType, PaymentStatus

from .access import ensure_editable_by_owner, ensure_owner, lock_application
from .models import InsuranceApplication, ReferenceCounter
from .transitions import ALLOWED
from .validation import validate_for_submission

MSG_NOTES_REQUIRED = "يرجى كتابة ملاحظات المراجعة"
MSG_PAYMENT_NOT_CONFIRMED = "لا يمكن قبول الطلب قبل تأكيد الدفع"
MSG_PAYMENT_CHANGE_NOT_ALLOWED = "لا يمكن تغيير حالة الدفع في هذه المرحلة"
MSG_NO_FEE_SCHEDULE = "لا يوجد جدول رسوم معتمد لهذه السنة المالية"

ADMIN_PAYMENT_TARGETS = frozenset({PaymentStatus.CONFIRMED, PaymentStatus.REJECTED})
PAYMENT_REVIEWABLE_STATUSES = frozenset(
    {
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.NEEDS_CORRECTION,
    }
)


# --- drafts -----------------------------------------------------------------------------------


def create_draft(
    doctor,
    *,
    actor,
    fiscal_year: int | None = None,
    application_type: str = ApplicationType.FIRST_TIME,
) -> InsuranceApplication:
    """Start the doctor's application for a fiscal year. One active application per year;
    the partial unique constraint is the authority under concurrency."""
    if actor is None or doctor.user_id != actor.pk:
        raise PermissionDeniedError()
    fiscal_year = fiscal_year or settings.CURRENT_FISCAL_YEAR
    active = InsuranceApplication.objects.filter(doctor=doctor, fiscal_year=fiscal_year).exclude(
        status=ApplicationStatus.REJECTED
    )
    if active.exists():
        raise ActiveApplicationExists()
    try:
        with transaction.atomic():
            application = InsuranceApplication.objects.create(
                doctor=doctor, fiscal_year=fiscal_year, application_type=application_type
            )
            record(actor=actor, action=AuditAction.APPLICATION_CREATED, obj=application)
    except IntegrityError:
        raise ActiveApplicationExists() from None
    return application


# --- reference numbers ------------------------------------------------------------------------


def generate_reference_number(fiscal_year: int) -> str:
    """Next `MED-{fy}-{000123}`. Must run inside the submission transaction: the counter row
    stays locked until commit, and a rollback releases the number unused."""
    ReferenceCounter.objects.bulk_create(
        [ReferenceCounter(fiscal_year=fiscal_year)], ignore_conflicts=True
    )
    counter = ReferenceCounter.objects.select_for_update().get(fiscal_year=fiscal_year)
    counter.last_sequence += 1
    counter.save(update_fields=["last_sequence"])
    return f"MED-{fiscal_year}-{counter.last_sequence:06d}"


# --- transitions ------------------------------------------------------------------------------


def _authorize(application: InsuranceApplication, rule, actor) -> None:
    if rule.actor_role == "DOCTOR":
        ensure_owner(application, actor)
    elif actor is None or not actor.is_admin:
        raise PermissionDeniedError()


def transition(
    application: InsuranceApplication,
    *,
    to_status: str,
    actor,
    review_notes: str = "",
    request=None,
) -> InsuranceApplication:
    """The ONE place where `status` changes. Returns the updated, locked-and-saved row."""
    with transaction.atomic():
        app = lock_application(application.pk)
        rule = ALLOWED.get((app.status, to_status))
        if rule is None:
            raise InvalidStatusTransition()
        _authorize(app, rule, actor)
        notes = review_notes.strip()
        if rule.requires_notes and not notes:
            raise ValidationFailed(fields={"review_notes": [MSG_NOTES_REQUIRED]})
        if rule.requires_payment_confirmed and app.payment_status != PaymentStatus.CONFIRMED:
            raise InvalidStatusTransition(MSG_PAYMENT_NOT_CONFIRMED)

        if to_status == ApplicationStatus.SUBMITTED:
            _submit_locked(app, actor, request)
        else:
            from_status = app.status
            app.status = to_status
            app.reviewed_by = actor
            app.reviewed_at = timezone.now()
            if notes:
                app.review_notes = notes
            app.save()
            record(
                actor=actor,
                action=AuditAction.APPLICATION_STATUS_CHANGED,
                obj=app,
                metadata={"from": from_status, "to": to_status, "notes": bool(notes)},
                request=request,
            )
    return app


def submit(application: InsuranceApplication, *, actor, request=None) -> InsuranceApplication:
    """Doctor submission (DRAFT or NEEDS_CORRECTION → SUBMITTED)."""
    return transition(
        application, to_status=ApplicationStatus.SUBMITTED, actor=actor, request=request
    )


def _submit_locked(app: InsuranceApplication, actor, request) -> None:
    result = validate_for_submission(app, stage="submit")
    if not result.is_valid:
        raise ValidationFailed.from_errors(result.errors)
    try:
        schedule = active_schedule(app.fiscal_year)
    except NoActiveFeeSchedule:
        raise ValidationFailed(MSG_NO_FEE_SCHEDULE) from None
    quote = quote_for_application(app, schedule=schedule)
    if not quote.is_valid:  # unreachable after validation; never freeze an invalid quote
        raise ValidationFailed(quote.error_message)

    from_status = app.status
    first_submission = app.reference_number is None
    if first_submission:
        app.reference_number = generate_reference_number(app.fiscal_year)
    now = timezone.now()
    FeeSchedule.objects.filter(pk=schedule.pk, locked_at__isnull=True).update(locked_at=now)

    app.fee_snapshot = quote.as_dict()
    app.fee_schedule = schedule
    app.submitted_snapshot = _submitted_snapshot(app)
    app.status = ApplicationStatus.SUBMITTED
    app.submitted_at = now
    app.save()

    record(
        actor=actor,
        action=(
            AuditAction.APPLICATION_SUBMITTED
            if first_submission
            else AuditAction.APPLICATION_RESUBMITTED
        ),
        obj=app,
        metadata={"from": from_status, "reference_number": app.reference_number},
        request=request,
    )
    record(
        actor=actor,
        action=AuditAction.FEE_SNAPSHOT_CREATED,
        obj=app,
        metadata={"schedule_id": quote.schedule_id, "tier": quote.tier, "total": quote.total},
        request=request,
    )


def _submitted_snapshot(app: InsuranceApplication) -> dict:
    """Copy of what was submitted, for audit and printing."""
    doctor = app.doctor
    member_fields = (
        "full_name", "national_id", "birth_year", "gender", "religion", "phone_number",
        "syndicate_type", "sub_syndicate", "syndicate_registration_number",
        "syndicate_registration_year", "treatment_card_number", "governorate", "neighborhood",
        "address",
    )  # fmt: skip
    return {
        "member": {f: getattr(doctor, f) for f in member_fields}
        | {"email": doctor.email, "date_of_birth": str(doctor.date_of_birth or "")},
        "application": {
            "fiscal_year": app.fiscal_year,
            "application_type": app.application_type,
            "work_status": app.work_status,
            "declaration_name": app.declaration_name,
        },
        "beneficiaries": [
            {
                "id": str(b.pk),
                "row_number": b.row_number,
                "kinship": b.kinship,
                "full_name": b.full_name,
                "birth_year": b.birth_year,
                "national_id": b.national_id,
            }
            for b in app.beneficiaries.all()
        ],
        "documents": [
            {
                "id": str(d.pk),
                "document_type": d.document_type,
                "beneficiary_id": str(d.beneficiary_id) if d.beneficiary_id else None,
            }
            for d in app.documents.all()
        ],
    }


# --- payment status ---------------------------------------------------------------------------


def _change_payment_status(app, status, actor, request) -> None:
    from_status = app.payment_status
    app.payment_status = status
    app.save(update_fields=["payment_status", "updated_at"])
    record(
        actor=actor,
        action=AuditAction.PAYMENT_STATUS_CHANGED,
        obj=app,
        metadata={"from": from_status, "to": status},
        request=request,
    )


@transaction.atomic
def mark_receipt_uploaded(
    application: InsuranceApplication, *, actor, request=None
) -> InsuranceApplication:
    """Called by the documents service when a PAYMENT_RECEIPT is stored (server-side only)."""
    app = lock_application(application.pk)
    ensure_editable_by_owner(app, actor)
    if app.payment_status != PaymentStatus.PENDING_REVIEW:
        _change_payment_status(app, PaymentStatus.PENDING_REVIEW, actor, request)
    return app


@transaction.atomic
def set_payment_status(
    application: InsuranceApplication, *, status: str, actor, request=None
) -> InsuranceApplication:
    """Admin confirms or rejects the uploaded receipt."""
    app = lock_application(application.pk)
    if actor is None or not actor.is_admin:
        raise PermissionDeniedError()
    if (
        status not in ADMIN_PAYMENT_TARGETS
        or app.status not in PAYMENT_REVIEWABLE_STATUSES
        or app.payment_status == PaymentStatus.NOT_UPLOADED
    ):
        raise InvalidStatusTransition(MSG_PAYMENT_CHANGE_NOT_ALLOWED)
    if app.payment_status != status:
        _change_payment_status(app, status, actor, request)
    return app
