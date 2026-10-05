"""Server-generated blob names (PROMPT.md §20). Browser paths and filenames are never used.

applications/{application}/doctor/{slug}-{uuid}.{ext}
applications/{application}/beneficiaries/{beneficiary}/{slug}-{uuid}.{ext}
"""

import uuid

from apps.reference.constants import DocumentType as T

BLOB_PREFIX = "applications/"

SLUGS: dict[T, str] = {
    T.NATIONAL_ID_FRONT: "national-id-front",
    T.NATIONAL_ID_BACK: "national-id-back",
    T.SYNDICATE_ID: "syndicate-id",
    T.PERSONAL_PHOTO: "personal-photo",
    T.PAYMENT_RECEIPT: "payment-receipt",
    T.BENEFICIARY_NATIONAL_ID: "national-id",
    T.BIRTH_CERTIFICATE: "birth-certificate",
    T.MARRIAGE_CERTIFICATE: "marriage-certificate",
    T.INSURANCE_PRINT: "insurance-print",
    T.UNIVERSITY_ID: "university-id",
    T.OTHER: "other",
}


def build_blob_name(application_id, beneficiary_id, document_type, extension: str) -> str:
    owner = f"beneficiaries/{beneficiary_id}" if beneficiary_id else "doctor"
    slug = SLUGS[T(document_type)]
    return f"{BLOB_PREFIX}{application_id}/{owner}/{slug}-{uuid.uuid4()}.{extension}"
