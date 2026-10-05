"""Authoritative submission validation (port of the prototype's validateForm; PROMPT.md §22).

Returns ALL errors at once, each with its wizard step, field path, stable code and Arabic
message. Frontend Zod schemas mirror the field rules for instant feedback only; this result is
what gates navigation and submission.

Steps: 1 member · 2 beneficiaries · 3 documents · 4 receipt · 5 declaration.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from django.conf import settings
from django.utils import timezone

from apps.beneficiaries.services import beneficiary_warnings, check_kinship_rules
from apps.common.arabic import is_valid_mobile, normalize_arabic_name
from apps.common.exceptions import FieldError
from apps.doctors.models import Doctor
from apps.reference.constants import (
    BENEFICIARY_BIRTH_YEAR_MIN,
    GOVERNORATES,
    REGISTRATION_YEAR_MIN,
    DocumentType,
    SyndicateType,
    WorkStatus,
)
from apps.reference.document_rules import (
    beneficiary_document_requirements,
    member_document_requirements,
)
from apps.reference.national_id import (
    INVALID_NATIONAL_ID_MESSAGE,
    InvalidNationalId,
    parse_national_id,
)

from .models import InsuranceApplication

Stage = Literal["form", "submit"]
STEPS = (1, 2, 3, 4, 5)
MEMBER, BENEFICIARIES, DOCUMENTS, RECEIPT, DECLARATION = STEPS

MIN_MEMBER_NAME_LENGTH = 5

# Messages — PROMPT.md §22 (rule number in brackets).
MSG_SYNDICATE_TYPE = "يرجى اختيار نوع النقابة"  # [1]
MSG_MEMBER_NAME = "اسم العضو يجب أن يكون 5 أحرف على الأقل"  # [2]
MSG_NATIONAL_ID = INVALID_NATIONAL_ID_MESSAGE  # [3]
MSG_GENDER = "يرجى تحديد النوع (ذكر/أنثى)"  # [4]
MSG_WORK_STATUS = "يرجى تحديد حالة العمل"  # [5]
MSG_REGISTRATION_YEAR = "سنة قيد النقابة غير صحيحة"  # [6]
MSG_MOBILE = "رقم الهاتف المحمول غير صحيح"  # [7]
MSG_MEMBER_DOCUMENT = {  # [8] [9] [10]
    DocumentType.NATIONAL_ID_FRONT: "يرجى إرفاق صورة وجه البطاقة الشخصية",
    DocumentType.NATIONAL_ID_BACK: "يرجى إرفاق صورة ظهر البطاقة الشخصية",
    DocumentType.SYNDICATE_ID: "يرجى إرفاق صورة كارنيه النقابة",
}
MSG_MEMBER_DOCUMENT_DEFAULT = "يرجى إرفاق {label}"
MSG_BENEFICIARY_KINSHIP = "المستفيد رقم {n}: يرجى تحديد درجة القرابة"  # [11]
MSG_BENEFICIARY_BIRTH_YEAR = "المستفيد {name}: سنة الميلاد غير صحيحة"  # [12]
MSG_BENEFICIARY_DOCUMENT = "المستفيد {name}: مستند {label} مطلوب"  # [13]
MSG_REQUIRED_FIELD = "يرجى إدخال {field}"  # [14]
MSG_DECLARATION_NAME = "اسم المقر يجب أن يطابق اسم العضو"  # [15]
MSG_RECEIPT = "يرجى رفع إيصال الدفع"  # [16]
MSG_DECLARATION_ACCEPTED = "يرجى الموافقة على الإقرار"  # [17]
MSG_DUPLICATE_NATIONAL_ID = "الرقم القومي مسجل لعضو آخر"  # [18]
# Not in §22 — added for the §13/§14 consistency rules (docs/progress.md, Session 2).
MSG_BIRTH_YEAR_MISMATCH = "سنة الميلاد لا تطابق الرقم القومي"
MSG_BENEFICIARY_SAME_AS_MEMBER = (
    "المستفيد {name}: الرقم القومي للمستفيد لا يمكن أن يطابق الرقم القومي للعضو"
)

REQUIRED_MEMBER_TEXT_FIELDS = (  # [14] field → Arabic label
    ("governorate", "محافظة السكن"),
    ("address", "العنوان"),
    ("sub_syndicate", "النقابة الفرعية"),
    ("syndicate_registration_number", "رقم قيد النقابة"),
)


@dataclass
class ValidationResult:
    errors: list[FieldError]
    steps: dict[int, bool]
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        by_step: dict[str, list[dict]] = {str(step): [] for step in STEPS}
        for error in self.errors:
            by_step[str(error.step)].append(error.as_dict())
        return {
            "is_valid": self.is_valid,
            "errors": [e.as_dict() for e in self.errors],
            "by_step": by_step,
            "steps_complete": {str(step): done for step, done in self.steps.items()},
            "warnings": self.warnings,
        }


class _Collector:
    def __init__(self) -> None:
        self.items: list[tuple[FieldError, bool]] = []

    def add(self, step: int, path: str, code: str, message: str, *, submit_only=False) -> None:
        self.items.append((FieldError(step, path, code, message), submit_only))


def _validate_member(c: _Collector, app: InsuranceApplication, doctor: Doctor) -> list[str]:
    warnings: list[str] = []
    fy = app.fiscal_year
    if doctor.syndicate_type not in SyndicateType.values:
        c.add(MEMBER, "member.syndicate_type", "REQUIRED", MSG_SYNDICATE_TYPE)
    if len(" ".join(doctor.full_name.split())) < MIN_MEMBER_NAME_LENGTH:
        c.add(MEMBER, "member.full_name", "TOO_SHORT", MSG_MEMBER_NAME)

    parsed = None
    try:
        parsed = parse_national_id(doctor.national_id, today=timezone.localdate())
    except InvalidNationalId:
        c.add(MEMBER, "member.national_id", "INVALID", MSG_NATIONAL_ID)
    else:
        warnings.extend(parsed.warnings)
        if Doctor.objects.filter(national_id=parsed.value).exclude(pk=doctor.pk).exists():
            c.add(MEMBER, "member.national_id", "DUPLICATE_NATIONAL_ID", MSG_DUPLICATE_NATIONAL_ID)

    if not doctor.gender:
        c.add(MEMBER, "member.gender", "REQUIRED", MSG_GENDER)
    elif parsed and doctor.gender != parsed.gender:
        c.add(MEMBER, "member.gender", "GENDER_MISMATCH", MSG_GENDER)

    if doctor.birth_year is None:
        c.add(
            MEMBER, "member.birth_year", "REQUIRED", MSG_REQUIRED_FIELD.format(field="سنة الميلاد")
        )
    elif parsed and doctor.birth_year != parsed.birth_year:
        c.add(MEMBER, "member.birth_year", "BIRTH_YEAR_MISMATCH", MSG_BIRTH_YEAR_MISMATCH)

    if app.work_status not in WorkStatus.values:
        c.add(MEMBER, "member.work_status", "REQUIRED", MSG_WORK_STATUS)

    year = doctor.syndicate_registration_year
    if year is None or not (REGISTRATION_YEAR_MIN <= year <= fy):
        c.add(MEMBER, "member.syndicate_registration_year", "INVALID", MSG_REGISTRATION_YEAR)

    if not is_valid_mobile(doctor.phone_number):
        c.add(MEMBER, "member.phone_number", "INVALID", MSG_MOBILE)

    for name, label in REQUIRED_MEMBER_TEXT_FIELDS:
        value = getattr(doctor, name).strip()
        if not value or (name == "governorate" and value not in GOVERNORATES):
            c.add(MEMBER, f"member.{name}", "REQUIRED", MSG_REQUIRED_FIELD.format(field=label))
    return warnings


def _validate_member_documents(c: _Collector, member_docs: set[str]) -> None:
    for req in member_document_requirements(require_photo=settings.REQUIRE_MEMBER_PHOTO):
        if not req.required or req.document_type in member_docs:
            continue
        if req.stage == "submit":  # the payment receipt has its own wizard step
            c.add(RECEIPT, "receipt", "MISSING_RECEIPT", MSG_RECEIPT, submit_only=True)
            continue
        message = MSG_MEMBER_DOCUMENT.get(
            req.document_type, MSG_MEMBER_DOCUMENT_DEFAULT.format(label=req.label)
        )
        c.add(DOCUMENTS, f"documents.{req.document_type}", "MISSING_DOCUMENT", message)


def _validate_beneficiaries(
    c: _Collector, app: InsuranceApplication, doctor: Doctor, docs_by_beneficiary
) -> list[str]:
    warnings: list[str] = []
    fy = app.fiscal_year
    for b in app.beneficiaries.all():
        n, name = b.row_number, b.full_name.strip()
        if name and not b.kinship:
            c.add(BENEFICIARIES, f"beneficiaries[{n}].kinship", "REQUIRED",
                  MSG_BENEFICIARY_KINSHIP.format(n=n))  # fmt: skip
        if not b.is_active:
            continue  # kinship without a name: ignored, like the fee engine (example 8)

        if b.birth_year is None or not (BENEFICIARY_BIRTH_YEAR_MIN <= b.birth_year <= fy):
            c.add(BENEFICIARIES, f"beneficiaries[{n}].birth_year", "INVALID",
                  MSG_BENEFICIARY_BIRTH_YEAR.format(name=name))  # fmt: skip
        if b.national_id and b.national_id == doctor.national_id:
            c.add(BENEFICIARIES, f"beneficiaries[{n}].national_id", "SAME_AS_MEMBER",
                  MSG_BENEFICIARY_SAME_AS_MEMBER.format(name=name))  # fmt: skip
        for error in check_kinship_rules(
            kinship=b.kinship, birth_year=b.birth_year, row_number=n, name=name,
            member_gender=doctor.gender or None, fiscal_year=fy,
        ):  # fmt: skip
            c.items.append((error, False))

        for req in beneficiary_document_requirements(
            b.kinship, b.birth_year, fiscal_year=fy, member_gender=doctor.gender or None,
            child_id_age=settings.CHILD_NATIONAL_ID_AGE,
        ):  # fmt: skip
            if req.required and req.document_type not in docs_by_beneficiary[b.pk]:
                c.add(DOCUMENTS, f"beneficiaries[{n}].documents.{req.document_type}",
                      "MISSING_DOCUMENT",
                      MSG_BENEFICIARY_DOCUMENT.format(name=name, label=req.label))  # fmt: skip
        warnings.extend(beneficiary_warnings(b))
    return warnings


def _validate_declaration(c: _Collector, app: InsuranceApplication, doctor: Doctor) -> None:
    declared = normalize_arabic_name(app.declaration_name)
    if not declared or declared != normalize_arabic_name(doctor.full_name):
        c.add(DECLARATION, "declaration.name", "MISMATCH", MSG_DECLARATION_NAME)
    if app.declaration_accepted_at is None:
        c.add(DECLARATION, "declaration.accepted", "REQUIRED", MSG_DECLARATION_ACCEPTED,
              submit_only=True)  # fmt: skip


def validate_for_submission(
    application: InsuranceApplication, *, stage: Stage = "submit"
) -> ValidationResult:
    """Evaluate every submission rule.

    `stage="form"` (used by `GET /validation/` for the stepper) omits the submit-only rules
    16-17 from `errors`; `steps` always reflects the full submit-stage evaluation so the stepper
    can show the receipt and declaration steps as incomplete.
    """
    doctor = application.doctor
    member_docs: set[str] = set()
    docs_by_beneficiary: dict = defaultdict(set)
    for doc_type, beneficiary_id in application.documents.values_list(
        "document_type", "beneficiary_id"
    ):
        (docs_by_beneficiary[beneficiary_id] if beneficiary_id else member_docs).add(doc_type)

    c = _Collector()
    warnings = _validate_member(c, application, doctor)
    _validate_member_documents(c, member_docs)
    warnings += _validate_beneficiaries(c, application, doctor, docs_by_beneficiary)
    _validate_declaration(c, application, doctor)

    all_errors = [error for error, _ in c.items]
    errors = [error for error, submit_only in c.items if stage == "submit" or not submit_only]
    errors.sort(key=lambda e: e.step)
    steps = {step: not any(e.step == step for e in all_errors) for step in STEPS}
    return ValidationResult(errors=errors, steps=steps, warnings=warnings)
