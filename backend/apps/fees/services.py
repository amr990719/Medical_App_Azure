"""Authoritative fee engine (port of the prototype's CalculationService; PROMPT.md §17).

`calculate_fees` and `get_tier` are pure: they read a FeeSchedule instance and plain inputs and
never touch the database. Money is always `int` (whole Egyptian pounds), never float.
"""

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

from apps.reference.constants import KINSHIP_FEE_KEY, SPOUSE_KINSHIPS, Kinship, WorkStatus

from .models import FeeSchedule

MEMBER_LABEL = "العضو الأصلي"
ADMIN_FEE_LABEL = "رسوم إدارية"
AGE_CAP_NOTE = "تم تطبيق سقف {amount} ج (عمر {age} سنة)"
INVALID_REGISTRATION_YEAR_MESSAGE = "يرجى إدخال سنة قيد النقابة بشكل صحيح لحساب الاشتراك."


class NoActiveFeeSchedule(LookupError):
    pass


@dataclass(frozen=True)
class BeneficiaryInput:
    kinship: Kinship | str | None
    name: str
    birth_year: int | None

    @property
    def is_active(self) -> bool:
        """Counted only with a kinship AND a non-empty name (PROMPT.md §17.2 rule 4)."""
        return bool(self.kinship) and bool((self.name or "").strip())


@dataclass(frozen=True)
class FeeLine:
    label: str
    fee: int
    note: str = ""


@dataclass(frozen=True)
class FeeQuote:
    fiscal_year: int
    tier: int
    breakdown: list[FeeLine] = field(default_factory=list)
    admin_fee: int = 0
    total: int = 0
    is_valid: bool = True
    error_message: str = ""
    schedule_id: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def is_valid_registration_year(schedule: FeeSchedule, registration_year: int | None) -> bool:
    return (
        type(registration_year) is int
        and schedule.registration_year_min <= registration_year <= schedule.fiscal_year
    )


def get_tier(
    schedule: FeeSchedule, registration_year: int, work_status: WorkStatus | str | None
) -> int:
    """Tier 1-4 from years since registration; pensioners are always tier 4.

    DECEASED (and a missing work status) is priced like WORKING — open question 2.
    """
    if work_status == WorkStatus.PENSIONER:
        return 4
    years = schedule.fiscal_year - registration_year
    for tier, upper in enumerate(schedule.tier_boundaries, start=1):
        if years <= upper:
            return tier
    return 4


def _capped(schedule: FeeSchedule, fee: int, birth_year: int | None) -> tuple[int, str]:
    """Apply the 70+ age cap. Unknown birth year → no cap."""
    if birth_year is None:
        return fee, ""
    age = schedule.fiscal_year - birth_year
    if age >= schedule.age_cap_threshold and fee > schedule.age_cap_amount:
        return schedule.age_cap_amount, AGE_CAP_NOTE.format(amount=schedule.age_cap_amount, age=age)
    return fee, ""


def calculate_fees(
    schedule: FeeSchedule,
    *,
    registration_year: int | None,
    work_status: WorkStatus | str | None,
    birth_year: int | None,
    beneficiaries: Iterable[BeneficiaryInput],
) -> FeeQuote:
    """Quote for one application. ADDITION applications are priced exactly like FIRST_TIME."""
    schedule_id = str(schedule.id)
    if not is_valid_registration_year(schedule, registration_year):
        return FeeQuote(
            fiscal_year=schedule.fiscal_year,
            tier=0,
            is_valid=False,
            error_message=INVALID_REGISTRATION_YEAR_MESSAGE,
            schedule_id=schedule_id,
        )

    tier = get_tier(schedule, registration_year, work_status)
    fees = schedule.tier_fees[str(tier)]

    member_fee, member_note = _capped(schedule, fees["member"], birth_year)
    breakdown = [FeeLine(MEMBER_LABEL, member_fee, member_note)]

    active = [b for b in beneficiaries if b.is_active]
    for beneficiary in active:
        kinship = Kinship(beneficiary.kinship)
        fee, note = fees[KINSHIP_FEE_KEY[kinship]], ""
        if kinship in SPOUSE_KINSHIPS:  # the cap never applies to parents or children
            fee, note = _capped(schedule, fee, beneficiary.birth_year)
        breakdown.append(FeeLine(beneficiary.name.strip(), fee, note))

    admin_fee = schedule.admin_fee_with_beneficiaries if active else schedule.admin_fee_member_only
    breakdown.append(FeeLine(ADMIN_FEE_LABEL, admin_fee))
    return FeeQuote(
        fiscal_year=schedule.fiscal_year,
        tier=tier,
        breakdown=breakdown,
        admin_fee=admin_fee,
        total=sum(line.fee for line in breakdown),
        schedule_id=schedule_id,
    )


def active_schedule(fiscal_year: int) -> FeeSchedule:
    try:
        return FeeSchedule.objects.get(fiscal_year=fiscal_year, is_active=True)
    except FeeSchedule.DoesNotExist:
        raise NoActiveFeeSchedule(fiscal_year) from None


def quote_for_application(application, *, schedule: FeeSchedule | None = None) -> FeeQuote:
    """Live quote from the saved draft (`GET /applications/{id}/fees/`). Submitted applications
    keep their frozen `fee_snapshot`; this function never reads or writes it."""
    schedule = schedule or active_schedule(application.fiscal_year)
    doctor = application.doctor
    return calculate_fees(
        schedule,
        registration_year=doctor.syndicate_registration_year,
        work_status=application.work_status or None,
        birth_year=doctor.birth_year,
        beneficiaries=[
            BeneficiaryInput(b.kinship or None, b.full_name, b.birth_year)
            for b in application.beneficiaries.all()
        ],
    )


SCHEDULE_FIELDS = (
    "tier_fees", "tier_boundaries", "admin_fee_member_only", "admin_fee_with_beneficiaries",
    "age_cap_threshold", "age_cap_amount", "registration_year_min",
)  # fmt: skip


def create_schedule_version(*, fiscal_year: int, actor, request=None, **values) -> FeeSchedule:
    """New active version for a fiscal year; the previous active version is deactivated (its
    amounts never change — submitted applications keep their snapshot)."""
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from django.db.models import Max

    from apps.audit.models import AuditAction
    from apps.audit.services import record
    from apps.common.exceptions import PermissionDeniedError, ValidationFailed

    if actor is None or not actor.is_admin:
        raise PermissionDeniedError()
    with transaction.atomic():
        existing = FeeSchedule.objects.select_for_update().filter(fiscal_year=fiscal_year)
        latest = existing.aggregate(v=Max("version"))["v"] or 0
        previous = existing.filter(is_active=True).first()
        if previous is not None:
            previous.is_active = False
            previous.save(update_fields=["is_active"])
        schedule = FeeSchedule(
            fiscal_year=fiscal_year,
            version=latest + 1,
            is_active=True,
            created_by=actor,
            **{k: v for k, v in values.items() if k in SCHEDULE_FIELDS},
        )
        try:
            schedule.save()
        except ValidationError as exc:
            raise ValidationFailed(fields={"tier_fees": exc.messages}) from None
        record(
            actor=actor,
            action=AuditAction.FEE_SCHEDULE_CHANGED,
            obj=schedule,
            metadata={
                "fiscal_year": fiscal_year,
                "version": schedule.version,
                "previous_id": str(previous.pk) if previous else None,
            },
            request=request,
        )
    return schedule
