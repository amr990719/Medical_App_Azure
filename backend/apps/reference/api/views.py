"""`GET /api/v1/reference-data/` — every enum, table and limit the SPA needs, so the frontend
never duplicates them (PROMPT.md §24, CLAUDE.md "Server is authoritative")."""

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.validators import accepted_content_types
from apps.reference.constants import (
    GOVERNORATES,
    KINSHIP_FEE_KEY,
    ApplicationStatus,
    ApplicationType,
    Gender,
    Kinship,
    PaymentStatus,
    Religion,
    SyndicateType,
    WorkStatus,
)
from apps.reference.document_rules import rules_as_reference_data


def _choices(enum) -> list[dict]:
    return [{"value": value, "label": label} for value, label in enum.choices]


def reference_data() -> dict:
    return {
        "fiscal_year": settings.CURRENT_FISCAL_YEAR,
        "max_beneficiaries": settings.MAX_BENEFICIARIES,
        "governorates": GOVERNORATES,
        "syndicate_types": _choices(SyndicateType),
        "work_statuses": _choices(WorkStatus),
        "religions": _choices(Religion),
        "genders": _choices(Gender),
        "kinships": [
            {"value": k.value, "label": k.label, "fee_key": KINSHIP_FEE_KEY[k]} for k in Kinship
        ],
        "application_types": _choices(ApplicationType),
        "statuses": _choices(ApplicationStatus),
        "payment_statuses": _choices(PaymentStatus),
        "document_rules": rules_as_reference_data(
            require_photo=settings.REQUIRE_MEMBER_PHOTO,
            child_id_age=settings.CHILD_NATIONAL_ID_AGE,
        ),
        "ocr_enabled": settings.OCR_ENABLED,
        "features": {
            "require_member_photo": settings.REQUIRE_MEMBER_PHOTO,
            "allow_pdf": settings.ALLOW_PDF_DOCUMENTS,
            "allow_heic": settings.ALLOW_HEIC,
        },
        "upload": {
            "max_bytes": settings.MAX_UPLOAD_BYTES,
            "receipt_min_width": settings.RECEIPT_MIN_WIDTH,
            "receipt_min_height": settings.RECEIPT_MIN_HEIGHT,
            "accepted_content_types": accepted_content_types(),
        },
    }


class ReferenceDataView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT, operation_id="reference_data")
    def get(self, request):
        response = Response(reference_data())
        response["Cache-Control"] = "private, max-age=3600"
        return response
