"""THE document-rules table (PROMPT.md §15).

This module is the only place that decides which documents are required. It drives the
submission validator, the DocumentModal and the documents checklist (through
`/api/v1/reference-data/` and per-beneficiary requirement lists), so labels and enforcement
cannot drift apart (prototype defect 11).
"""

from dataclasses import dataclass
from typing import Literal

from .constants import DocumentType, Gender, Kinship

Stage = Literal["form", "submit"]
BaseRule = Literal["spouse", "parent", "child"]

DOCUMENT_LABELS: dict[DocumentType, str] = {t: t.label for t in DocumentType}

OCR_CAPABLE_TYPES: frozenset[DocumentType] = frozenset(
    {
        DocumentType.NATIONAL_ID_FRONT,
        DocumentType.NATIONAL_ID_BACK,
        DocumentType.SYNDICATE_ID,
        DocumentType.BENEFICIARY_NATIONAL_ID,
        DocumentType.BIRTH_CERTIFICATE,
    }
)

MEMBER_DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    DocumentType.NATIONAL_ID_FRONT,
    DocumentType.NATIONAL_ID_BACK,
    DocumentType.SYNDICATE_ID,
    DocumentType.PERSONAL_PHOTO,
    DocumentType.PAYMENT_RECEIPT,
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
    DocumentType.BENEFICIARY_NATIONAL_ID,
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

    def as_dict(self) -> dict:
        return {
            "type": self.document_type.value,
            "required": self.required,
            "label": self.label,
            "ocr_capable": self.ocr_capable,
            "stage": self.stage,
        }


def _requirement(document_type: DocumentType, required: bool, stage: Stage = "form"):
    return DocumentRequirement(
        document_type=document_type,
        required=required,
        label=DOCUMENT_LABELS[document_type],
        ocr_capable=document_type in OCR_CAPABLE_TYPES,
        stage=stage,
    )


def member_document_requirements(*, require_photo: bool) -> list[DocumentRequirement]:
    return [
        _requirement(DocumentType.NATIONAL_ID_FRONT, True),
        _requirement(DocumentType.NATIONAL_ID_BACK, True),
        _requirement(DocumentType.SYNDICATE_ID, True),
        _requirement(DocumentType.PERSONAL_PHOTO, require_photo),
        _requirement(DocumentType.PAYMENT_RECEIPT, True, stage="submit"),
    ]


def _child_requirements(
    age: int | None, member_gender: Gender | None, child_id_age: int
) -> list[DocumentRequirement]:
    # Unknown birth year → treated as younger than the threshold (Review Focus 3).
    under_threshold = age is None or age < child_id_age
    birth_certificate = under_threshold or member_gender == Gender.FEMALE
    reqs = [_requirement(DocumentType.BENEFICIARY_NATIONAL_ID, not under_threshold)]
    if birth_certificate:
        reqs.append(_requirement(DocumentType.BIRTH_CERTIFICATE, True))
    return reqs


def beneficiary_document_requirements(
    kinship: Kinship | str | None,
    birth_year: int | None,
    *,
    fiscal_year: int,
    member_gender: Gender | str | None,
    child_id_age: int = 16,
) -> list[DocumentRequirement]:
    """Required (and optional) document slots for one beneficiary row.

    age = fiscal_year − birth_year. Optional slots are returned with `required=False` so the
    DocumentModal can offer them.
    """
    if not kinship:
        return []
    rule = KINSHIP_DOCUMENT_RULES[Kinship(kinship)]
    gender = Gender(member_gender) if member_gender else None
    if rule.base_rule == "spouse":
        reqs = [_requirement(t, True) for t in _SPOUSE_DOCUMENTS]
    elif rule.base_rule == "parent":
        reqs = [_requirement(DocumentType.BENEFICIARY_NATIONAL_ID, True)]
    else:
        age = None if birth_year is None else fiscal_year - birth_year
        reqs = _child_requirements(age, gender, child_id_age)
    present = {r.document_type for r in reqs}
    reqs.extend(_requirement(t, True) for t in rule.extra_required if t not in present)
    return reqs


def rules_as_reference_data(*, require_photo: bool, child_id_age: int) -> dict:
    """Serializable description of this table for `GET /api/v1/reference-data/`."""
    return {
        "document_types": [
            {"type": t.value, "label": DOCUMENT_LABELS[t], "ocr_capable": t in OCR_CAPABLE_TYPES}
            for t in DocumentType
        ],
        "member": [r.as_dict() for r in member_document_requirements(require_photo=require_photo)],
        "child_national_id_age": child_id_age,
        "kinships": {
            kinship.value: {
                "base_rule": rule.base_rule,
                "extra_required": [t.value for t in rule.extra_required],
            }
            for kinship, rule in KINSHIP_DOCUMENT_RULES.items()
        },
        "base_rules": {
            "spouse": {"required": [t.value for t in _SPOUSE_DOCUMENTS]},
            "parent": {"required": [DocumentType.BENEFICIARY_NATIONAL_ID.value]},
            "child": {
                "below_age": {
                    "required": [DocumentType.BIRTH_CERTIFICATE.value],
                    "optional": [DocumentType.BENEFICIARY_NATIONAL_ID.value],
                },
                "at_or_above_age": {"required": [DocumentType.BENEFICIARY_NATIONAL_ID.value]},
                "female_member_always_requires": [DocumentType.BIRTH_CERTIFICATE.value],
                "unknown_birth_year": "below_age",
            },
        },
    }
