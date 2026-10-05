"""Doctor profile service (PROMPT.md §12–§13, §40).

The profile is created at first visit and completed while drafting. The national ID is the
source of truth for date of birth, birth year and gender; a conflicting typed value is an
error. Uniqueness is decided by the database constraint (IntegrityError → DUPLICATE_NATIONAL_ID).
"""

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.applications.models import EDITABLE_STATUSES, InsuranceApplication
from apps.common.exceptions import (
    ApplicationNotEditable,
    DuplicateNationalId,
    PermissionDeniedError,
    ValidationFailed,
)
from apps.reference.constants import ApplicationStatus
from apps.reference.national_id import parse_national_id

from .models import Doctor

MSG_GENDER_MISMATCH = "يرجى تحديد النوع (ذكر/أنثى)"
MSG_BIRTH_YEAR_MISMATCH = "سنة الميلاد لا تطابق الرقم القومي"

PROFILE_FIELDS = (
    "full_name", "national_id", "birth_year", "gender", "religion", "phone_number",
    "syndicate_type", "sub_syndicate", "syndicate_registration_number",
    "syndicate_registration_year", "treatment_card_number", "governorate", "neighborhood",
    "address",
)  # fmt: skip


def get_or_create_doctor(user) -> Doctor:
    doctor, _ = Doctor.objects.get_or_create(user=user)
    return doctor


def ensure_profile_editable(doctor: Doctor) -> None:
    """The profile is part of the submitted application: frozen while the current fiscal
    year's application is submitted, under review or approved."""
    locked = (
        InsuranceApplication.objects.filter(doctor=doctor, fiscal_year=settings.CURRENT_FISCAL_YEAR)
        .exclude(status__in=[*EDITABLE_STATUSES, ApplicationStatus.REJECTED])
        .exists()
    )
    if locked:
        raise ApplicationNotEditable()


@transaction.atomic
def update_profile(doctor: Doctor, *, actor, changes: dict) -> Doctor:
    if actor is None or doctor.user_id != actor.pk:
        raise PermissionDeniedError()
    doctor = Doctor.objects.select_for_update().get(pk=doctor.pk)
    ensure_profile_editable(doctor)

    unknown = set(changes) - set(PROFILE_FIELDS)
    if unknown:  # serializers only pass profile fields; guard against programming errors
        raise ValueError(f"not profile fields: {sorted(unknown)}")
    for name, value in changes.items():
        setattr(doctor, name, value)

    if "national_id" in changes:
        _apply_national_id(doctor, changes)

    if doctor.national_id and (
        Doctor.objects.filter(national_id=doctor.national_id).exclude(pk=doctor.pk).exists()
    ):
        raise DuplicateNationalId()
    try:
        with transaction.atomic():
            doctor.save()
    except IntegrityError:
        raise DuplicateNationalId() from None
    return doctor


def _apply_national_id(doctor: Doctor, changes: dict) -> None:
    if not doctor.national_id:
        doctor.national_id = None
        doctor.date_of_birth = None
        return
    info = parse_national_id(doctor.national_id)  # already format-checked by the serializer
    errors: dict[str, list[str]] = {}
    if changes.get("gender") and changes["gender"] != info.gender:
        errors["gender"] = [MSG_GENDER_MISMATCH]
    if changes.get("birth_year") is not None and changes["birth_year"] != info.birth_year:
        errors["birth_year"] = [MSG_BIRTH_YEAR_MISMATCH]
    if errors:
        raise ValidationFailed(fields=errors)
    doctor.date_of_birth = info.date_of_birth
    doctor.birth_year = info.birth_year
    doctor.gender = info.gender
