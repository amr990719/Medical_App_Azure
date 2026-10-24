"""THE document-rules table (PROMPT.md §15).

This module is the only place that decides which documents are required. It drives the
submission validator, the DocumentModal and the documents checklist (through
`/api/v1/reference-data/`, the per-beneficiary requirement lists and the application's member
requirement list), so labels and enforcement cannot drift apart (prototype defect 11).
"""

from dataclasses import dataclass
from typing import Literal

from .constants import CHILD_KINSHIPS, DocumentType, Gender, Kinship

Stage = Literal["form", "submit"]
BaseRule = Literal["spouse", "parent", "child"]

DOCUMENT_LABELS: dict[DocumentType, str] = {t: t.label for t in DocumentType}

# Only types with a working extraction (apps/ocr/schemas.py). The beneficiary ID BACK carries no
# name / ID / birth date, and the member birth certificate must never fill beneficiary fields.
OCR_CAPABLE_TYPES: frozenset[DocumentType] = frozenset(
    {
        DocumentType.NATIONAL_ID_FRONT,
        DocumentType.NATIONAL_ID_BACK,
        DocumentType.SYNDICATE_ID,
        DocumentType.BENEFICIARY_NATIONAL_ID,
        DocumentType.BIRTH_CERTIFICATE,
    }
)

# Personal photos accept supported image formats only, even when PDFs are enabled.
IMAGE_ONLY_TYPES: frozenset[DocumentType] = frozenset(
    {DocumentType.PERSONAL_PHOTO, DocumentType.BENEFICIARY_PERSONAL_PHOTO}
)

MEMBER_DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    DocumentType.NATIONAL_ID_FRONT,
    DocumentType.NATIONAL_ID_BACK,
    DocumentType.SYNDICATE_ID,
    DocumentType.PERSONAL_PHOTO,
    DocumentType.PAYMENT_RECEIPT,
    DocumentType.MEMBER_BIRTH_CERTIFICATE,
)

# Both sides, wherever a beneficiary's national ID is required (or optional).
BENEFICIARY_NATIONAL_ID_SIDES: tuple[DocumentType, ...] = (
    DocumentType.BENEFICIARY_NATIONAL_ID,
    DocumentType.BENEFICIARY_NATIONAL_ID_BACK,
)

HINT_PHOTO = "صورة شخصية بخلفية بيضاء مطلوبة عند الاشتراك لأول مرة."
HINT_PHOTO_CHILD_EXEMPT = "لا تُطلب صورة شخصية للأطفال أقل من 3 سنوات."
HINT_FEMALE_MEMBER_BIRTH_CERTIFICATE = (
    "شهادة ميلاد الابن/الابنة مطلوبة لإثبات صلة القرابة بالأم (العضوة) مهما كان العمر."
)
HINT_MEMBER_BIRTH_CERTIFICATE = (
    "مطلوبة لإضافة الأم: شهادة ميلاد العضو الأصلي نفسه، ولا تغني عنها شهادة ميلاد الأم."
)


@dataclass(frozen=True)
class KinshipRule:
    base_rule: BaseRule
    extra_required: tuple[DocumentType, ...] = ()


KINSHIP_DOCUMENT_RULES: dict[Kinship, KinshipRule] = {
    Kinship.HUSBAND: KinshipRule("spouse"),
    Kinship.WIFE: KinshipRule("spouse"),
    Kinship.MOTHER: KinshipRule("parent"),
    Kinship.FATHER: KinshipRule("parent"),
    Kinship.SON_MINOR: KinshipRule("child"),
    Kinship.DAUGHTER: KinshipRule("child"),
    Kinship.SON_UNIVERSITY: KinshipRule("child", (DocumentType.UNIVERSITY_ID,)),
    Kinship.SON_GRADUATE: KinshipRule("child", (DocumentType.INSURANCE_PRINT,)),
}

_SPOUSE_DOCUMENTS = (
    *BENEFICIARY_NATIONAL_ID_SIDES,
    DocumentType.MARRIAGE_CERTIFICATE,
    DocumentType.INSURANCE_PRINT,
)


@dataclass(frozen=True)
class DocumentRequirement:
    document_type: DocumentType
    required: bool
    label: str
    ocr_capable: bool
    stage: Stage = "form"
    hints: tuple[str, ...] = ()

    @property
    def images_only(self) -> bool:
        return self.document_type in IMAGE_ONLY_TYPES

    def as_dict(self) -> dict:
        return {
            "type": self.document_type.value,
            "required": self.required,
            "label": self.label,
            "ocr_capable": self.ocr_capable,
            "stage": self.stage,
            "images_only": self.images_only,
            "hints": list(self.hints),
        }


def _requirement(
    document_type: DocumentType,
    required: bool,
    stage: Stage = "form",
    hints: tuple[str, ...] = (),
) -> DocumentRequirement:
    return DocumentRequirement(
        document_type=document_type,
        required=required,
        label=DOCUMENT_LABELS[document_type],
        ocr_capable=document_type in OCR_CAPABLE_TYPES,
        stage=stage,
        hints=hints,
    )


def member_document_requirements(
    *,
    require_photo: bool,
    has_active_mother: bool = False,
    has_member_birth_certificate: bool = False,
) -> list[DocumentRequirement]:
    """Member slots. Called without the application facts it returns the global list
    (reference data); `has_active_mother` adds the member's own birth certificate as a required
    slot. An already uploaded certificate stays visible (optional) once it is no longer needed.
    """
    reqs = [
        _requirement(DocumentType.NATIONAL_ID_FRONT, True),
        _requirement(DocumentType.NATIONAL_ID_BACK, True),
        _requirement(DocumentType.SYNDICATE_ID, True),
        _requirement(DocumentType.PERSONAL_PHOTO, require_photo),
    ]
    if has_active_mother or has_member_birth_certificate:
        reqs.append(
            _requirement(
                DocumentType.MEMBER_BIRTH_CERTIFICATE,
                has_active_mother,
                hints=(HINT_MEMBER_BIRTH_CERTIFICATE,),
            )
        )
    reqs.append(_requirement(DocumentType.PAYMENT_RECEIPT, True, stage="submit"))
    return reqs


def _child_requirements(
    age: int | None, member_gender: Gender | None, child_id_age: int
) -> list[DocumentRequirement]:
    # Unknown birth year → treated as younger than the threshold (Review Focus 3).
    under_threshold = age is None or age < child_id_age
    female_member = member_gender == Gender.FEMALE
    reqs = [_requirement(t, not under_threshold) for t in BENEFICIARY_NATIONAL_ID_SIDES]
    if under_threshold or female_member:
        hints = (HINT_FEMALE_MEMBER_BIRTH_CERTIFICATE,) if female_member else ()
        reqs.append(_requirement(DocumentType.BIRTH_CERTIFICATE, True, hints=hints))
    return reqs


def photo_required(
    kinship: Kinship,
    age: int | None,
    *,
    is_first_time: bool | None,
    photo_exempt_child_age: int,
) -> bool:
    """A first-time beneficiary needs a white-background photo; children younger than
    `photo_exempt_child_age` do not. An unknown age never grants the exemption."""
    if is_first_time is not True:
        return False
    exempt = kinship in CHILD_KINSHIPS and age is not None and age < photo_exempt_child_age
    return not exempt


def beneficiary_document_requirements(
    kinship: Kinship | str | None,
    birth_year: int | None,
    *,
    fiscal_year: int,
    member_gender: Gender | str | None,
    child_id_age: int = 16,
    is_first_time: bool | None = None,
    photo_exempt_child_age: int = 3,
) -> list[DocumentRequirement]:
    """Required (and optional) document slots for one beneficiary row.

    age = fiscal_year − birth_year. Optional slots are returned with `required=False` so the
    DocumentModal can offer them. The photo slot is always offered; it is required only for a
    first-time beneficiary (see `photo_required`).
    """
    if not kinship:
        return []
    kinship = Kinship(kinship)
    rule = KINSHIP_DOCUMENT_RULES[kinship]
    gender = Gender(member_gender) if member_gender else None
    age = None if birth_year is None else fiscal_year - birth_year
    if rule.base_rule == "spouse":
        reqs = [_requirement(t, True) for t in _SPOUSE_DOCUMENTS]
    elif rule.base_rule == "parent":
        reqs = [_requirement(t, True) for t in BENEFICIARY_NATIONAL_ID_SIDES]
    else:
        reqs = _child_requirements(age, gender, child_id_age)
    present = {r.document_type for r in reqs}
    reqs.extend(_requirement(t, True) for t in rule.extra_required if t not in present)

    photo_hints = (HINT_PHOTO,)
    if kinship == Kinship.SON_MINOR:
        photo_hints += (HINT_PHOTO_CHILD_EXEMPT,)
    reqs.append(
        _requirement(
            DocumentType.BENEFICIARY_PERSONAL_PHOTO,
            photo_required(
                kinship,
                age,
                is_first_time=is_first_time,
                photo_exempt_child_age=photo_exempt_child_age,
            ),
            hints=photo_hints,
        )
    )
    return reqs


def rules_as_reference_data(
    *, require_photo: bool, child_id_age: int, photo_exempt_child_age: int = 3
) -> dict:
    """Serializable description of this table for `GET /api/v1/reference-data/`.

    `member` is the global list; the application's own list (with conditional slots such as the
    member birth certificate) is `member_required_documents` on the application.
    """
    national_id_sides = [t.value for t in BENEFICIARY_NATIONAL_ID_SIDES]
    return {
        "document_types": [
            {
                "type": t.value,
                "label": DOCUMENT_LABELS[t],
                "ocr_capable": t in OCR_CAPABLE_TYPES,
                "images_only": t in IMAGE_ONLY_TYPES,
            }
            for t in DocumentType
        ],
        "member": [r.as_dict() for r in member_document_requirements(require_photo=require_photo)],
        "member_conditional": {
            DocumentType.MEMBER_BIRTH_CERTIFICATE.value: {"required_with_kinship": "MOTHER"}
        },
        "child_national_id_age": child_id_age,
        "photo_exempt_child_age": photo_exempt_child_age,
        "kinships": {
            kinship.value: {
                "base_rule": rule.base_rule,
                "extra_required": [t.value for t in rule.extra_required],
            }
            for kinship, rule in KINSHIP_DOCUMENT_RULES.items()
        },
        "base_rules": {
            "spouse": {"required": [t.value for t in _SPOUSE_DOCUMENTS]},
            "parent": {"required": national_id_sides},
            "child": {
                "below_age": {
                    "required": [DocumentType.BIRTH_CERTIFICATE.value],
                    "optional": national_id_sides,
                },
                "at_or_above_age": {"required": national_id_sides},
                "female_member_always_requires": [DocumentType.BIRTH_CERTIFICATE.value],
                "unknown_birth_year": "below_age",
            },
        },
        "photo": {
            "type": DocumentType.BENEFICIARY_PERSONAL_PHOTO.value,
            "required_when": "is_first_time",
            "exempt_child_below_age": photo_exempt_child_age,
            "unknown_age_exempt": False,
        },
    }
