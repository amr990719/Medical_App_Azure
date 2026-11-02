"""Doctor profile service (PROMPT.md §12–§13, §40).

The profile is created at first visit and completed while drafting. The national ID is the
source of truth for date of birth, birth year and gender; a conflicting typed value is an
error. Uniqueness is decided by the database constraint (IntegrityError → DUPLICATE_NATIONAL_ID).
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.applications.models import EDITABLE_STATUSES, InsuranceApplication
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.arabic import normalize_mobile
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
MSG_INVALID_MOBILE = "رقم الهاتف المحمول غير صحيح"

PROFILE_FIELDS = (
    "full_name", "national_id", "birth_year", "gender", "religion", "phone_number",
    "syndicate_type", "sub_syndicate", "syndicate_registration_number",
    "syndicate_registration_year", "governorate", "neighborhood", "address",
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
    old_mobile = normalize_mobile(doctor.phone_number)
    for name, value in changes.items():
        setattr(doctor, name, value)
    # Consent was given for the old number: a different number needs a fresh opt-in.
    consent_cleared = (
        "phone_number" in changes
        and doctor.whatsapp_opt_in
        and normalize_mobile(doctor.phone_number) != old_mobile
    )
    if consent_cleared:
        doctor.whatsapp_opt_in = False
        doctor.whatsapp_opt_in_at = None

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
    if consent_cleared:
        _audit_opt_in(doctor, actor, enabled=False, request=None)
    return doctor


@transaction.atomic
def set_whatsapp_opt_in(doctor: Doctor, *, enabled: bool, actor, request=None) -> Doctor:
    """Record the doctor's WhatsApp consent. Deliberately not gated by
    `ensure_profile_editable`: consent can change while the profile is frozen."""
    if actor is None or doctor.user_id != actor.pk:
        raise PermissionDeniedError()
    doctor = Doctor.objects.select_for_update().get(pk=doctor.pk)
    if enabled and normalize_mobile(doctor.phone_number) is None:
        raise ValidationFailed(fields={"whatsapp_opt_in": [MSG_INVALID_MOBILE]})
    if doctor.whatsapp_opt_in == enabled:
        return doctor
    doctor.whatsapp_opt_in = enabled
    doctor.whatsapp_opt_in_at = timezone.now() if enabled else None
    doctor.save(update_fields=["whatsapp_opt_in", "whatsapp_opt_in_at", "updated_at"])
    _audit_opt_in(doctor, actor, enabled=enabled, request=request)
    return doctor


HELP_REPLY_INTERVAL = timedelta(hours=24)


@transaction.atomic
def stop_whatsapp_for_number(local: str, *, message_time: datetime) -> bool:
    """A stop word came from this number (local `01...` form): clear the consent of every
    doctor with it. Returns True if any consent changed. A stop sent before a doctor's latest
    opt-in is ignored, so a retried old message cannot undo it."""
    changed = False
    for doctor in Doctor.objects.select_for_update().filter(phone_number=local).order_by("pk"):
        if not doctor.whatsapp_opt_in:
            continue
        if doctor.whatsapp_opt_in_at is not None and doctor.whatsapp_opt_in_at > message_time:
            continue
        doctor.whatsapp_opt_in = False
        doctor.whatsapp_opt_in_at = None
        doctor.save(update_fields=["whatsapp_opt_in", "whatsapp_opt_in_at", "updated_at"])
        record(
            actor=None,
            action=AuditAction.WHATSAPP_OPT_IN_CHANGED,
            obj=doctor,
            metadata={"enabled": False, "source": "whatsapp_reply"},
        )
        changed = True
    return changed


@transaction.atomic
def claim_help_reply(local: str, *, now: datetime) -> bool:
    """True if a help reply is due for this number: some matching doctor has had none in the
    last 24 hours. Marks every matching doctor as answered."""
    doctors = list(Doctor.objects.select_for_update().filter(phone_number=local).order_by("pk"))
    cutoff = now - HELP_REPLY_INTERVAL
    if not any(
        d.whatsapp_help_sent_at is None or d.whatsapp_help_sent_at < cutoff for d in doctors
    ):
        return False
    Doctor.objects.filter(pk__in=[d.pk for d in doctors]).update(
        whatsapp_help_sent_at=now, updated_at=now
    )
    return True


def _audit_opt_in(doctor: Doctor, actor, *, enabled: bool, request) -> None:
    # Never the phone number: only the new state and where the change came from.
    record(
        actor=actor,
        action=AuditAction.WHATSAPP_OPT_IN_CHANGED,
        obj=doctor,
        metadata={"enabled": enabled, "source": "profile"},
        request=request,
    )


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
