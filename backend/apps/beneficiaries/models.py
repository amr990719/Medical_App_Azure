import uuid

from django.db import models
from django.db.models import Q

from apps.doctors.models import NATIONAL_ID_REGEX
from apps.reference.constants import Kinship
from apps.reference.national_id import mask_national_id

# Database-level bound; the business limit (MAX_BENEFICIARIES, default 10) is a setting.
MAX_ROW_NUMBER = 20


class Beneficiary(models.Model):
    """A family member on ONE application — a per-fiscal-year snapshot (PROMPT.md §14).

    A row counts (fees, validation) only when it has a kinship AND a non-empty name.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        "applications.InsuranceApplication",
        on_delete=models.PROTECT,
        related_name="beneficiaries",
        db_index=False,  # covered by uniq_beneficiary_row (application_id, row_number)
    )
    row_number = models.PositiveSmallIntegerField()
    kinship = models.CharField(max_length=16, choices=Kinship.choices, blank=True)
    full_name = models.CharField(max_length=200, blank=True)
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True)
    national_id = models.CharField(  # noqa: DJ001 — young children have none
        max_length=14, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["row_number"]
        indexes = [
            # Cross-application duplicate warnings look beneficiaries up by national ID alone.
            models.Index(
                fields=["national_id"],
                condition=Q(national_id__isnull=False),
                name="beneficiary_national_id_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["application", "row_number"], name="uniq_beneficiary_row"
            ),
            models.UniqueConstraint(
                fields=["application", "national_id"],
                condition=Q(national_id__isnull=False),
                name="uniq_beneficiary_national_id_per_application",
            ),
            models.CheckConstraint(
                condition=Q(row_number__gte=1, row_number__lte=MAX_ROW_NUMBER),
                name="beneficiary_row_number_range",
            ),
            models.CheckConstraint(
                condition=Q(national_id__isnull=True) | Q(national_id__regex=NATIONAL_ID_REGEX),
                name="beneficiary_national_id_format",
            ),
            models.CheckConstraint(
                condition=Q(kinship="") | Q(kinship__in=Kinship.values),
                name="beneficiary_kinship_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.row_number}: {self.full_name or '—'}"

    @property
    def is_active(self) -> bool:
        return bool(self.kinship) and bool(self.full_name.strip())

    @property
    def masked_national_id(self) -> str:
        return mask_national_id(self.national_id)
