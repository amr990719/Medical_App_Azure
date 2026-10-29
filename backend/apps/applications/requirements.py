"""Document requirements of ONE application, evaluated on the server from THE rules table
(`apps/reference/document_rules.py`). The validator, the doctor API and the admin API all call
these functions, so a conditional slot (the member photo of a FIRST_TIME application, the member
birth certificate while a MOTHER is listed) is decided in exactly one place.
"""

from django.conf import settings

from apps.reference.constants import DocumentType, Kinship
from apps.reference.document_rules import (
    DocumentRequirement,
    beneficiary_document_requirements,
    member_document_requirements,
)


def has_active_mother(application) -> bool:
    return any(b.is_active and b.kinship == Kinship.MOTHER for b in application.beneficiaries.all())


def member_requirements(
    application, *, member_documents: set[str] | None = None
) -> list[DocumentRequirement]:
    """Member slots for this application. `member_documents` (active member document types)
    may be passed when already loaded; otherwise it is read from the prefetched documents."""
    if member_documents is None:
        member_documents = {
            d.document_type for d in application.documents.all() if d.beneficiary_id is None
        }
    return member_document_requirements(
        application_type=application.application_type,
        has_active_mother=has_active_mother(application),
        has_member_birth_certificate=DocumentType.MEMBER_BIRTH_CERTIFICATE in member_documents,
    )


def beneficiary_requirements(beneficiary, application=None) -> list[DocumentRequirement]:
    application = application or beneficiary.application
    return beneficiary_document_requirements(
        beneficiary.kinship or None,
        beneficiary.birth_year,
        fiscal_year=application.fiscal_year,
        member_gender=application.doctor.gender or None,
        child_id_age=settings.CHILD_NATIONAL_ID_AGE,
        photo_exempt_child_age=settings.PHOTO_EXEMPT_CHILD_AGE,
    )
