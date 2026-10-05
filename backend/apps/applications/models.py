import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.reference.constants import (
    ApplicationStatus,
    ApplicationType,
    PaymentStatus,
    WorkStatus,
)

REFERENCE_NUMBER_REGEX = r"^MED-[0-9]{4}-[0-9]{6}$"
EDITABLE_STATUSES = frozenset({ApplicationStatus.DRAFT, ApplicationStatus.NEEDS_CORRECTION})


class InsuranceApplication(models.Model):
    """One subscription application per doctor per fiscal year (PROMPT.md §16.1).

    `status`, `payment_status`, `reference_number`, `fee_snapshot`, `fee_schedule`,
    `review_notes`, `reviewed_by`, `reviewed_at` and `submitted_at` are written only by
    `applications.services` — never by a doctor-facing serializer.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    doctor = models.ForeignKey(
        "doctors.Doctor", on_delete=models.PROTECT, related_name="applications"
    )
    fiscal_year = models.PositiveSmallIntegerField()
    application_type = models.CharField(
        max_length=16, choices=ApplicationType.choices, default=ApplicationType.FIRST_TIME
    )
    # Lives on the application because it changes that year's fee. Blank while drafting.
    work_status = models.CharField(max_length=16, choices=WorkStatus.choices, blank=True)
    status = models.CharField(
        max_length=20, choices=ApplicationStatus.choices, default=ApplicationStatus.DRAFT
    )
    payment_status = models.CharField(
        max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.NOT_UPLOADED
    )
    reference_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    declaration_name = models.CharField(max_length=200, blank=True)
    declaration_accepted_at = models.DateTimeField(null=True, blank=True)
    fee_snapshot = models.JSONField(null=True, blank=True)
    fee_schedule = models.ForeignKey(
        "fees.FeeSchedule",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="applications",
    )
    submitted_snapshot = models.JSONField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "submitted_at"], name="app_status_submitted_idx"),
            models.Index(fields=["fiscal_year", "status"], name="app_year_status_idx"),
            models.Index(fields=["payment_status"], name="app_payment_status_idx"),
        ]
        constraints = [
            # One active application per doctor per fiscal year; REJECTED frees the slot.
            models.UniqueConstraint(
                fields=["doctor", "fiscal_year"],
                condition=~Q(status=ApplicationStatus.REJECTED),
                name="uniq_active_application_per_year",
            ),
            models.CheckConstraint(
                condition=Q(status__in=ApplicationStatus.values), name="app_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(payment_status__in=PaymentStatus.values),
                name="app_payment_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(application_type__in=ApplicationType.values),
                name="app_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(work_status="") | Q(work_status__in=WorkStatus.values),
                name="app_work_status_valid",
            ),
            # A draft has never been submitted; everything else has a reference number.
            # (isnull=False is explicit: a CHECK that evaluates to NULL passes.)
            models.CheckConstraint(
                condition=(
                    Q(status=ApplicationStatus.DRAFT, reference_number__isnull=True)
                    | (
                        ~Q(status=ApplicationStatus.DRAFT)
                        & Q(reference_number__isnull=False)
                        & Q(reference_number__regex=REFERENCE_NUMBER_REGEX)
                    )
                ),
                name="app_reference_number_iff_submitted",
            ),
        ]

    def __str__(self) -> str:
        return self.reference_number or f"مسودة {self.fiscal_year}"

    @property
    def is_editable(self) -> bool:
        return self.status in EDITABLE_STATUSES


class ReferenceCounter(models.Model):
    """Per-fiscal-year sequence for `MED-{fy}-{000123}` numbers, locked with SELECT FOR UPDATE."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fiscal_year = models.PositiveSmallIntegerField(unique=True)
    last_sequence = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.fiscal_year}: {self.last_sequence}"


class AdminNote(models.Model):
    """Internal reviewer note, never shown to the doctor.

    `InsuranceApplication.review_notes` is the doctor-visible message.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        InsuranceApplication,
        on_delete=models.PROTECT,
        related_name="admin_notes",
        db_index=False,  # covered by adminnote_app_created_idx
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["application", "created_at"], name="adminnote_app_created_idx")
        ]

    def __str__(self) -> str:
        return f"note {self.pk}"
