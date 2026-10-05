"""Beneficiary domain service (PROMPT.md §14).

Draft-level checks happen here (formats, enums, ranges that the database needs); submission
rules (birth year 1920..FY, required documents, kinship rules) are evaluated by
`applications.validation`, which reuses `check_kinship_rules`.
"""

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.applications.access import ensure_editable_by_owner, lock_application
from apps.applications.models import InsuranceApplication
from apps.common.exceptions import FieldError, ValidationFailed
from apps.documents.models import Document
from apps.documents.services import soft_delete_documents
from apps.reference.constants import ApplicationStatus, Gender, Kinship
from apps.reference.national_id import (
    INVALID_NATIONAL_ID_MESSAGE,
    InvalidNationalId,
    normalize_national_id,
    parse_national_id,
)

from .models import Beneficiary

BENEFICIARY_STEP = 2

MSG_ROW_LIMIT = "لا يمكن إضافة أكثر من {max} مستفيدين"
MSG_INVALID_KINSHIP = "درجة القرابة غير صحيحة"
MSG_INVALID_BIRTH_YEAR = "سنة الميلاد غير صحيحة"
MSG_SAME_AS_MEMBER = "الرقم القومي للمستفيد لا يمكن أن يطابق الرقم القومي للعضو"
MSG_DUPLICATE_IN_APPLICATION = "الرقم القومي مكرر لمستفيد آخر في نفس الطلب"
MSG_SPOUSE_GENDER = "المستفيد {name}: درجة القرابة لا تتوافق مع نوع العضو"
MSG_SON_MINOR_AGE = "المستفيد {name}: الابن القاصر يجب أن يكون {max_age} سنة أو أقل"
MSG_CROSS_APPLICATION_DUPLICATE = "المستفيد {name}: الرقم القومي مسجل كمستفيد في طلب آخر"


def _collapse(text: str | None) -> str:
    return " ".join((text or "").split())


def _clean(application: InsuranceApplication, row_number, kinship, birth_year, national_id):
    errors: dict[str, list[str]] = {}
    max_rows = settings.MAX_BENEFICIARIES
    if not (1 <= row_number <= max_rows):
        errors["row_number"] = [MSG_ROW_LIMIT.format(max=max_rows)]
    kinship = kinship or ""
    if kinship and kinship not in Kinship.values:
        errors["kinship"] = [MSG_INVALID_KINSHIP]
    if birth_year is not None and not (1000 <= birth_year <= 9999):
        errors["birth_year"] = [MSG_INVALID_BIRTH_YEAR]

    nid = normalize_national_id(national_id) or None
    if nid is not None:
        try:
            parse_national_id(nid)
        except InvalidNationalId:
            errors["national_id"] = [INVALID_NATIONAL_ID_MESSAGE]
        else:
            if nid == application.doctor.national_id:
                errors["national_id"] = [MSG_SAME_AS_MEMBER]
            elif (
                application.beneficiaries.filter(national_id=nid)
                .exclude(row_number=row_number)
                .exists()
            ):
                errors["national_id"] = [MSG_DUPLICATE_IN_APPLICATION]
    if errors:
        raise ValidationFailed(fields=errors)
    return kinship, nid


@transaction.atomic
def upsert_beneficiary(
    application: InsuranceApplication,
    *,
    row_number: int,
    kinship: Kinship | str | None,
    full_name: str,
    birth_year: int | None,
    national_id: str | None,
    actor,
) -> Beneficiary:
    """Create or update the row `row_number`. A kinship change discards that row's documents,
    because the required document set changes (the UI confirms before calling)."""
    application = lock_application(application.pk)
    ensure_editable_by_owner(application, actor)
    kinship, nid = _clean(application, row_number, kinship, birth_year, national_id)

    beneficiary = application.beneficiaries.filter(row_number=row_number).first()
    if beneficiary is None:
        beneficiary = Beneficiary(application=application, row_number=row_number)
    elif beneficiary.kinship != kinship:
        soft_delete_documents(
            Document.objects.filter(beneficiary=beneficiary), actor=actor, reason="KINSHIP_CHANGED"
        )

    beneficiary.kinship = kinship
    beneficiary.full_name = _collapse(full_name)
    beneficiary.birth_year = birth_year
    beneficiary.national_id = nid
    try:
        with transaction.atomic():
            beneficiary.save()
    except IntegrityError:
        # Concurrent insert of the same national ID: the database constraint is authoritative.
        raise ValidationFailed(fields={"national_id": [MSG_DUPLICATE_IN_APPLICATION]}) from None
    return beneficiary


MSG_ROW_TAKEN = "هذا الصف مستخدم لمستفيد آخر"
BENEFICIARY_FIELDS = ("kinship", "full_name", "birth_year", "national_id")


@transaction.atomic
def add_beneficiary(
    application: InsuranceApplication, *, actor, row_number: int | None = None, **fields
) -> Beneficiary:
    """New row: the requested `row_number` when free, otherwise the lowest free row."""
    application = lock_application(application.pk)
    ensure_editable_by_owner(application, actor)
    taken = set(application.beneficiaries.values_list("row_number", flat=True))
    max_rows = settings.MAX_BENEFICIARIES
    if row_number is None:
        row_number = next((n for n in range(1, max_rows + 1) if n not in taken), max_rows + 1)
    elif row_number in taken:
        raise ValidationFailed(fields={"row_number": [MSG_ROW_TAKEN]})
    values = {name: fields.get(name) for name in BENEFICIARY_FIELDS}
    values["full_name"] = values["full_name"] or ""
    return upsert_beneficiary(application, row_number=row_number, actor=actor, **values)


@transaction.atomic
def update_beneficiary(beneficiary: Beneficiary, *, actor, changes: dict) -> Beneficiary:
    """Partial update of one row; omitted fields keep their current value."""
    application = lock_application(beneficiary.application_id)
    ensure_editable_by_owner(application, actor)
    current = Beneficiary.objects.get(pk=beneficiary.pk)
    values = {name: changes.get(name, getattr(current, name)) for name in BENEFICIARY_FIELDS}
    values["full_name"] = values["full_name"] or ""
    return upsert_beneficiary(application, row_number=current.row_number, actor=actor, **values)


@transaction.atomic
def delete_beneficiary(beneficiary: Beneficiary, *, actor) -> None:
    application = lock_application(beneficiary.application_id)
    ensure_editable_by_owner(application, actor)
    soft_delete_documents(
        Document.objects.filter(beneficiary=beneficiary),
        actor=actor,
        reason="BENEFICIARY_DELETED",
        detach=True,
    )
    beneficiary.delete()


def check_kinship_rules(
    *,
    kinship: Kinship | str | None,
    birth_year: int | None,
    row_number: int,
    name: str,
    member_gender: Gender | str | None,
    fiscal_year: int,
) -> list[FieldError]:
    """Configurable kinship rules (open question 6): spouse vs member gender, SON_MINOR age."""
    errors: list[FieldError] = []
    field = f"beneficiaries[{row_number}].kinship"
    spouse_mismatch = (kinship == Kinship.WIFE and member_gender != Gender.MALE) or (
        kinship == Kinship.HUSBAND and member_gender != Gender.FEMALE
    )
    if settings.ENFORCE_SPOUSE_GENDER and member_gender and spouse_mismatch:
        errors.append(
            FieldError(
                BENEFICIARY_STEP,
                field,
                "SPOUSE_GENDER_MISMATCH",
                MSG_SPOUSE_GENDER.format(name=name),
            )
        )
    max_age = settings.SON_MINOR_MAX_AGE
    if (
        settings.ENFORCE_SON_MINOR_AGE
        and kinship == Kinship.SON_MINOR
        and birth_year is not None
        and fiscal_year - birth_year > max_age
    ):
        errors.append(
            FieldError(
                BENEFICIARY_STEP,
                field,
                "SON_MINOR_TOO_OLD",
                MSG_SON_MINOR_AGE.format(name=name, max_age=max_age),
            )
        )
    return errors


def beneficiary_warnings(beneficiary: Beneficiary) -> list[str]:
    """Admin warnings (never blocks): same national ID listed on another active application,
    e.g. a child listed by two member parents."""
    if not beneficiary.national_id:
        return []
    duplicate = (
        Beneficiary.objects.filter(national_id=beneficiary.national_id)
        .exclude(application_id=beneficiary.application_id)
        .exclude(application__status=ApplicationStatus.REJECTED)
        .exists()
    )
    return [MSG_CROSS_APPLICATION_DUPLICATE.format(name=beneficiary.full_name)] if duplicate else []
