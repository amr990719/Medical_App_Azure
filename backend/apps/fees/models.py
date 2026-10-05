import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

TIERS = ("1", "2", "3", "4")
FEE_KEYS = ("member", "spouse", "child", "grad_son", "parent")


class FeeScheduleLocked(Exception):
    """A schedule version used by a submission is read-only; create a new version instead."""


def validate_tier_fees(value) -> None:
    if not isinstance(value, dict) or set(value) != set(TIERS):
        raise ValidationError("tier_fees must define tiers 1-4.")
    for tier in TIERS:
        row = value[tier]
        if not isinstance(row, dict) or set(row) != set(FEE_KEYS):
            raise ValidationError(f"tier {tier} must define {', '.join(FEE_KEYS)}.")
        for key, amount in row.items():
            # Whole Egyptian pounds only: int, never float/str (bool is an int subclass).
            if type(amount) is not int or amount < 0:
                raise ValidationError(f"tier {tier} {key} must be a non-negative integer.")


def validate_tier_boundaries(value) -> None:
    if (
        not isinstance(value, list)
        or len(value) != len(TIERS) - 1
        or any(type(v) is not int or v < 0 for v in value)
        or value != sorted(value)
    ):
        raise ValidationError("tier_boundaries must be three ascending non-negative integers.")


class FeeSchedule(models.Model):
    """Versioned fee schedule per fiscal year (PROMPT.md §17.1).

    Amounts are whole Egyptian pounds (integers). A version referenced by a submission is
    locked (`locked_at`): its amounts can never change, only its `is_active` flag.
    """

    LOCKED_FIELDS = (
        "fiscal_year",
        "version",
        "tier_fees",
        "tier_boundaries",
        "admin_fee_member_only",
        "admin_fee_with_beneficiaries",
        "age_cap_threshold",
        "age_cap_amount",
        "registration_year_min",
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fiscal_year = models.PositiveSmallIntegerField()
    version = models.PositiveSmallIntegerField(default=1)
    # {"1": {"member": 600, "spouse": 800, "child": 500, "grad_son": 1200, "parent": 1050}, ...}
    tier_fees = models.JSONField(validators=[validate_tier_fees])
    # Years since registration: <= b[0] → tier 1, <= b[1] → 2, <= b[2] → 3, otherwise 4.
    tier_boundaries = models.JSONField(default=list, validators=[validate_tier_boundaries])
    admin_fee_member_only = models.PositiveIntegerField(default=150)
    admin_fee_with_beneficiaries = models.PositiveIntegerField(default=175)
    age_cap_threshold = models.PositiveSmallIntegerField(default=70)
    age_cap_amount = models.PositiveIntegerField(default=500)
    registration_year_min = models.PositiveSmallIntegerField(default=1950)
    is_active = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["fiscal_year", "version"], name="uniq_fee_schedule_version"
            ),
            models.UniqueConstraint(
                fields=["fiscal_year"],
                condition=Q(is_active=True),
                name="uniq_active_fee_schedule_per_year",
            ),
        ]

    def __str__(self) -> str:
        return f"FY{self.fiscal_year} v{self.version}"

    def save(self, *args, **kwargs):
        if not self.tier_boundaries:
            self.tier_boundaries = [5, 10, 15]
        validate_tier_fees(self.tier_fees)
        validate_tier_boundaries(self.tier_boundaries)
        if not self._state.adding:
            stored = (
                type(self)
                .objects.filter(pk=self.pk, locked_at__isnull=False)
                .values(*self.LOCKED_FIELDS)
                .first()
            )
            if stored and any(stored[f] != getattr(self, f) for f in self.LOCKED_FIELDS):
                raise FeeScheduleLocked(str(self))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if type(self).objects.filter(pk=self.pk, locked_at__isnull=False).exists():
            raise FeeScheduleLocked(str(self))
        return super().delete(*args, **kwargs)

    @property
    def is_locked(self) -> bool:
        return self.locked_at is not None
