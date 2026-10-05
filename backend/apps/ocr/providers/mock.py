"""Deterministic provider for local development and tests (PROMPT.md §21.2).

Returns raw, un-normalized values (Eastern Arabic digits, colloquial spellings) so that the
normalizers are exercised exactly as with a real model: the ID front matches worked example 2's
member (born 1985), the syndicate card says 2014 / بشري, beneficiary documents describe a child.
"""

from typing import Any

from apps.reference.constants import DocumentType as T

RESPONSES: dict[T, dict[str, str]] = {
    T.NATIONAL_ID_FRONT: {
        "member_name": "أحمد محمد علي حسن",
        "national_id": "٢٨٥٠٦١٥٠١٠١٢٣٤",
        "governorate": "القاهره",
        "address": "١٢ شارع عباس العقاد",
        "neighborhood": "مدينة نصر",
    },
    T.NATIONAL_ID_BACK: {"gender": "ذكر", "religion": "مسلم"},
    T.SYNDICATE_ID: {
        "registration_number": "١٢٣٤٥",
        "sub_syndicate": "القاهرة",
        "registration_date": "تاريخ القيد ٢٠١٤-٠٤-٢٨",
        "syndicate_type": "طبيب بشري",
    },
    T.BENEFICIARY_NATIONAL_ID: {
        "full_name": "عمر أحمد محمد علي",
        "national_id": "",
        "birth_date": "٢٠١٥-٠٣-١٠",
    },
    T.BIRTH_CERTIFICATE: {
        "full_name": "عمر أحمد محمد علي",
        "national_id": "",
        "birth_date": "١٠-٠٣-٢٠١٥",
    },
}


class MockOcrProvider:
    name = "mock"

    def extract(self, *, image: bytes, content_type: str, document_type: T) -> dict[str, Any]:
        return dict(RESPONSES.get(T(document_type), {}))
