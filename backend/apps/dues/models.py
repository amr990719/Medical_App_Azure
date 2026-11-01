"""Additional syndicate dues (مستحقات نقابية) an admin asks a member to settle before the
treatment application can be approved, e.g. the syndicate subscription.

Kept apart from the treatment fee: never part of `fee_snapshot`, the fee engine, the
application's `PAYMENT_RECEIPT` or its `payment_status`. Every receipt the member uploads is its
own `DuesReceipt` row pointing at its own `Document` (type SYNDICATE_DUES_RECEIPT), so rejected
submissions stay in the history. Statuses change only through `apps.dues.services`.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.reference.constants import DuesReceiptStatus, DuesRequestStatus

UNRESOLVED_STATUSES = frozenset(
    {DuesRequestStatus.REQUESTED, DuesRequestStatus.PENDING_REVIEW, DuesRequestStatus.REJECTED}
)
RESOLVED_STATUSES = frozenset({DuesRequestStatus.CONFIRMED, DuesRequestStatus.CANCELLED})


class SyndicateDuesRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        "applications.InsuranceApplication",
        on_delete=models.PROTECT,
        related_name="dues_requests",
        db_index=False,  # covered by dues_request_app_created_idx
    )
    # EGP, two decimal places; never a float.
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(
        max_length=20, choices=DuesRequestStatus.choices, default=DuesRequestStatus.REQUESTED
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Who confirmed the payment or cancelled the request, and when.
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["application", "created_at"], name="dues_request_app_created_idx")
        ]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="dues_request_amount_positive"),
            models.CheckConstraint(condition=~Q(reason=""), name="dues_request_reason_present"),
            models.CheckConstraint(
                condition=Q(status__in=DuesRequestStatus.values), name="dues_request_status_valid"
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=DuesRequestStatus.CANCELLED) & ~Q(cancellation_reason="")
                    | ~Q(status=DuesRequestStatus.CANCELLED) & Q(cancellation_reason="")
                ),
                name="dues_request_cancellation_reason_iff_cancelled",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status__in=RESOLVED_STATUSES)
                    & Q(resolved_by__isnull=False, resolved_at__isnull=False)
                    | Q(status__in=UNRESOLVED_STATUSES)
                    & Q(resolved_by__isnull=True, resolved_at__isnull=True)
                ),
                name="dues_request_resolved_iff_final",
            ),
        ]

    def __str__(self) -> str:
        return f"dues {self.pk}"

    @property
    def is_unresolved(self) -> bool:
        return self.status in UNRESOLVED_STATUSES


class DuesReceipt(models.Model):
    """One uploaded receipt for one dues request; never replaced or deleted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        SyndicateDuesRequest, on_delete=models.PROTECT, related_name="receipts"
    )
    document = models.OneToOneField(
        "documents.Document", on_delete=models.PROTECT, related_name="dues_receipt"
    )
    status = models.CharField(
        max_length=20, choices=DuesReceiptStatus.choices, default=DuesReceiptStatus.PENDING_REVIEW
    )
    rejection_reason = models.TextField(blank=True)  # shown to the member
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=DuesReceiptStatus.values), name="dues_receipt_status_valid"
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=DuesReceiptStatus.REJECTED) & ~Q(rejection_reason="")
                    | ~Q(status=DuesReceiptStatus.REJECTED) & Q(rejection_reason="")
                ),
                name="dues_receipt_rejection_reason_iff_rejected",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=DuesReceiptStatus.PENDING_REVIEW)
                    & Q(reviewed_by__isnull=True, reviewed_at__isnull=True)
                    | ~Q(status=DuesReceiptStatus.PENDING_REVIEW)
                    & Q(reviewed_by__isnull=False, reviewed_at__isnull=False)
                ),
                name="dues_receipt_reviewed_iff_decided",
            ),
            # At most one receipt waiting for review, and at most one accepted, per request.
            models.UniqueConstraint(
                fields=["request"],
                condition=Q(status=DuesReceiptStatus.PENDING_REVIEW),
                name="uniq_pending_receipt_per_dues_request",
            ),
            models.UniqueConstraint(
                fields=["request"],
                condition=Q(status=DuesReceiptStatus.CONFIRMED),
                name="uniq_confirmed_receipt_per_dues_request",
            ),
        ]

    def __str__(self) -> str:
        return f"dues receipt {self.pk}"
