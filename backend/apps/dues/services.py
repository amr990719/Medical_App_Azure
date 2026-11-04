"""Additional syndicate dues: request (admin) → receipt (member) → confirm / reject (admin), or
cancel (admin). The ONE place where dues statuses change.

Lock order everywhere: the application row (`lock_application`, shared with `transition`), then
the dues request, then its receipt. Approval checks the dues under the same application lock, so
an approval and a new request never interleave.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.applications.access import ensure_owner, lock_application
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.exceptions import InvalidStatusTransition, PermissionDeniedError, ValidationFailed
from apps.documents.models import DUES_RECEIPT_TYPE
from apps.documents.services import create_document_row, stored_blob
from apps.documents.validators import validate_upload
from apps.notifications.services import enqueue
from apps.reference.constants import ApplicationStatus, NotificationEvent
from apps.reference.constants import DuesReceiptStatus as RS
from apps.reference.constants import DuesRequestStatus as DS

from .models import UNRESOLVED_STATUSES, DuesReceipt, SyndicateDuesRequest

# Applications whose review is still open. Drafts have nothing to review; APPROVED and REJECTED
# are final and stay frozen (their requests too).
DUES_ACTIVE_STATUSES = frozenset(
    {
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.NEEDS_CORRECTION,
    }
)
UPLOADABLE_STATUSES = frozenset({DS.REQUESTED, DS.REJECTED})
REVIEW_DECISIONS = frozenset({RS.CONFIRMED, RS.REJECTED})
MAX_AMOUNT = Decimal("99999999.99")  # max_digits=10, decimal_places=2

MSG_DUES_OUTSTANDING = "لا يمكن قبول الطلب قبل تأكيد سداد جميع المستحقات النقابية المطلوبة"
MSG_NOT_ALLOWED_FOR_APPLICATION = "لا يمكن طلب أو مراجعة مستحقات نقابية في هذه الحالة من الطلب"
MSG_AMOUNT_INVALID = "يرجى إدخال مبلغ أكبر من صفر بالجنيه (بحد أقصى رقمان بعد العلامة العشرية)"
MSG_REASON_REQUIRED = "يرجى كتابة سبب المستحقات وتفاصيلها"
MSG_UPLOAD_NOT_ALLOWED = "لا يمكن رفع إيصال لهذه المستحقات في حالتها الحالية"
MSG_REVIEW_NOT_ALLOWED = "لا يوجد إيصال قيد المراجعة لهذه المستحقات"
MSG_REJECTION_REASON_REQUIRED = "يرجى كتابة سبب رفض الإيصال"
MSG_CANCEL_NOT_ALLOWED = "لا يمكن إلغاء مستحقات تم تأكيدها أو إلغاؤها"
MSG_CANCEL_REASON_REQUIRED = "يرجى كتابة سبب الإلغاء"

# Admin actions per request, as the UI shows them (derived here, never in the browser).
CONFIRM_RECEIPT = "CONFIRM_RECEIPT"
REJECT_RECEIPT = "REJECT_RECEIPT"
CANCEL = "CANCEL"


def _ensure_admin(actor) -> None:
    if actor is None or not getattr(actor, "is_admin", False):
        raise PermissionDeniedError()


def _ensure_active(app) -> None:
    if app.status not in DUES_ACTIVE_STATUSES:
        raise InvalidStatusTransition(MSG_NOT_ALLOWED_FOR_APPLICATION)


def _lock_request(dues_request_id) -> SyndicateDuesRequest:
    return SyndicateDuesRequest.objects.select_for_update().get(pk=dues_request_id)


# --- rules the API and the transition table read ---------------------------------------------


def outstanding_dues(application):
    """Requests that still block approval: every one not confirmed or cancelled."""
    return SyndicateDuesRequest.objects.filter(
        application_id=application.pk, status__in=UNRESOLVED_STATUSES
    )


def can_request_dues(application) -> bool:
    return application.status in DUES_ACTIVE_STATUSES


def doctor_can_upload(dues_request: SyndicateDuesRequest) -> bool:
    return (
        dues_request.application.status in DUES_ACTIVE_STATUSES
        and dues_request.status in UPLOADABLE_STATUSES
    )


def admin_dues_actions(dues_request: SyndicateDuesRequest) -> list[str]:
    if dues_request.application.status not in DUES_ACTIVE_STATUSES:
        return []
    actions = []
    if dues_request.status == DS.PENDING_REVIEW:
        actions += [CONFIRM_RECEIPT, REJECT_RECEIPT]
    if dues_request.is_unresolved:
        actions.append(CANCEL)
    return actions


# --- admin: request -------------------------------------------------------------------------------


def _clean_amount(amount) -> Decimal:
    """Whole piastres only: an amount with more than two decimals is refused, never rounded."""
    if (
        not isinstance(amount, Decimal)
        or not amount.is_finite()
        or amount != amount.quantize(Decimal("0.01"))
        or not Decimal("0") < amount <= MAX_AMOUNT
    ):
        raise ValidationFailed(fields={"amount": [MSG_AMOUNT_INVALID]})
    return amount.quantize(Decimal("0.01"))


@transaction.atomic
def create_dues_request(
    application, *, amount: Decimal, reason: str, actor, request=None
) -> SyndicateDuesRequest:
    """Ask the member to settle `amount` EGP. Changes nothing on the application itself."""
    _ensure_admin(actor)
    amount = _clean_amount(amount)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailed(fields={"reason": [MSG_REASON_REQUIRED]})
    app = lock_application(application.pk)
    _ensure_active(app)
    dues = SyndicateDuesRequest.objects.create(
        application=app, amount=amount, reason=reason, created_by=actor
    )
    record(
        actor=actor,
        action=AuditAction.DUES_REQUEST_CREATED,
        obj=dues,
        metadata={"application_id": str(app.pk), "amount": str(amount)},
        request=request,
    )
    enqueue(app, NotificationEvent.DUES_REQUESTED, dues_request=dues)
    return dues


# --- member: receipt ------------------------------------------------------------------------------


def _ensure_can_upload(app, dues: SyndicateDuesRequest, actor) -> None:
    ensure_owner(app, actor)
    if app.status not in DUES_ACTIVE_STATUSES or dues.status not in UPLOADABLE_STATUSES:
        raise InvalidStatusTransition(MSG_UPLOAD_NOT_ALLOWED)


def submit_dues_receipt(
    dues_request: SyndicateDuesRequest, *, upload, actor, request=None
) -> DuesReceipt:
    """The member's receipt for one request: stored privately, reviewed later. Uploading never
    marks the dues as paid and needs no edit or resubmission of the application."""
    app = dues_request.application
    _ensure_can_upload(app, dues_request, actor)  # fail fast, before reading the file
    info = validate_upload(upload, document_type=DUES_RECEIPT_TYPE)

    with stored_blob(app.pk, DUES_RECEIPT_TYPE, info) as blob_name, transaction.atomic():
        app = lock_application(app.pk)
        dues = _lock_request(dues_request.pk)
        _ensure_can_upload(app, dues, actor)  # re-check under the locks
        document = create_document_row(
            app, beneficiary=None, document_type=DUES_RECEIPT_TYPE, blob_name=blob_name,
            info=info, actor=actor, request=request,
        )  # fmt: skip
        receipt = DuesReceipt.objects.create(request=dues, document=document)
        dues.status = DS.PENDING_REVIEW
        dues.save(update_fields=["status", "updated_at"])
        record(
            actor=actor,
            action=AuditAction.DUES_RECEIPT_UPLOADED,
            obj=dues,
            metadata={"receipt_id": str(receipt.pk), "document_id": str(document.pk)},
            request=request,
        )
    return receipt


# --- admin: review and cancel ---------------------------------------------------------------------


@transaction.atomic
def review_dues_receipt(
    dues_request: SyndicateDuesRequest, *, receipt_id, decision: str, reason: str = "", actor,
    request=None,
) -> SyndicateDuesRequest:  # fmt: skip
    """Confirm or reject the receipt waiting for review. `receipt_id` must be that receipt, so a
    stale page never decides on an older submission. Rejection needs a reason for the member."""
    _ensure_admin(actor)
    if decision not in REVIEW_DECISIONS:
        raise InvalidStatusTransition(MSG_REVIEW_NOT_ALLOWED)
    reason = (reason or "").strip()
    if decision == RS.REJECTED and not reason:
        raise ValidationFailed(fields={"reason": [MSG_REJECTION_REASON_REQUIRED]})
    app = lock_application(dues_request.application_id)
    _ensure_active(app)
    dues = _lock_request(dues_request.pk)
    receipt = (
        dues.receipts.select_for_update().filter(pk=receipt_id, status=RS.PENDING_REVIEW).first()
        if receipt_id and dues.status == DS.PENDING_REVIEW
        else None
    )
    if receipt is None:
        raise InvalidStatusTransition(MSG_REVIEW_NOT_ALLOWED)

    now = timezone.now()
    receipt.status = decision
    receipt.rejection_reason = reason if decision == RS.REJECTED else ""
    receipt.reviewed_by, receipt.reviewed_at = actor, now
    receipt.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at"])
    if decision == RS.CONFIRMED:
        dues.status = DS.CONFIRMED
        dues.resolved_by, dues.resolved_at = actor, now
    else:
        dues.status = DS.REJECTED
    dues.save(update_fields=["status", "resolved_by", "resolved_at", "updated_at"])
    record(
        actor=actor,
        action=AuditAction.DUES_RECEIPT_REVIEWED,
        obj=dues,
        metadata={"receipt_id": str(receipt.pk), "decision": decision},
        request=request,
    )
    event = (
        NotificationEvent.DUES_CONFIRMED
        if decision == RS.CONFIRMED
        else NotificationEvent.DUES_RECEIPT_REJECTED
    )
    enqueue(app, event, dues_request=dues)
    return dues


@transaction.atomic
def cancel_dues_request(
    dues_request: SyndicateDuesRequest, *, reason: str, actor, request=None
) -> SyndicateDuesRequest:
    """Withdraw an unresolved request (it then no longer blocks approval). A receipt still waiting
    for review is closed unreviewed and kept in the history."""
    _ensure_admin(actor)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailed(fields={"reason": [MSG_CANCEL_REASON_REQUIRED]})
    app = lock_application(dues_request.application_id)
    _ensure_active(app)
    dues = _lock_request(dues_request.pk)
    if not dues.is_unresolved:
        raise InvalidStatusTransition(MSG_CANCEL_NOT_ALLOWED)

    now = timezone.now()
    dues.receipts.filter(status=RS.PENDING_REVIEW).update(
        status=RS.CANCELLED, reviewed_by=actor, reviewed_at=now
    )
    from_status = dues.status
    dues.status = DS.CANCELLED
    dues.cancellation_reason = reason
    dues.resolved_by, dues.resolved_at = actor, now
    dues.save()
    record(
        actor=actor,
        action=AuditAction.DUES_REQUEST_CANCELLED,
        obj=dues,
        metadata={"from": from_status},
        request=request,
    )
    enqueue(app, NotificationEvent.DUES_CANCELLED, dues_request=dues)
    return dues
