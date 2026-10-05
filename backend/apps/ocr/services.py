"""OCR suggestions (PROMPT.md §21). Server-side only, behind OCR_ENABLED; the caller is
authorized and rate-limited by the view. Suggestions are RETURNED, never saved. Nothing about
the image, prompt or extracted values is logged or audited — only field names.
"""

import logging
from dataclasses import dataclass, field

from django.conf import settings

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.exceptions import OcrUnavailable, PermissionDeniedError, ValidationFailed
from apps.documents.storage import get_storage
from apps.documents.validators import PDF_CONTENT_TYPE
from apps.reference.constants import DocumentType as T
from apps.reference.document_rules import OCR_CAPABLE_TYPES

from . import normalizers as n
from .providers import OcrProviderError, get_provider

logger = logging.getLogger("apps.ocr")

MSG_NOT_OCR_CAPABLE = "هذا المستند لا يدعم المسح التلقائي"
MSG_PDF = "المسح التلقائي غير متاح لملفات PDF، يرجى إدخال البيانات يدوياً"


@dataclass(frozen=True)
class OcrSuggestion:
    document_id: str
    document_type: T
    fields: dict = field(default_factory=dict)


def _front(raw: dict) -> dict:
    national_id = n.clean_national_id(raw.get("national_id"))
    return {
        "member_name": n.clean_text(raw.get("member_name")),
        "national_id": national_id,
        "birth_year": n.birth_year_from_id(national_id),
        "governorate": n.map_governorate(raw.get("governorate")),
        "neighborhood": n.clean_text(raw.get("neighborhood")),
        "address": n.clean_text(raw.get("address")),
    }


def _back(raw: dict) -> dict:
    return {
        "gender": n.map_enum(raw.get("gender"), n.GENDER_VALUES),
        "religion": n.map_enum(raw.get("religion"), n.RELIGION_VALUES),
    }


def _syndicate(raw: dict) -> dict:
    return {
        "registration_number": n.digits_only(raw.get("registration_number")),
        "sub_syndicate": n.clean_text(raw.get("sub_syndicate")),
        "syndicate_registration_year": n.extract_year(raw.get("registration_date")),
        "syndicate_type": n.map_enum(raw.get("syndicate_type"), n.SYNDICATE_TYPE_VALUES),
    }


def _beneficiary(raw: dict) -> dict:
    national_id = n.clean_national_id(raw.get("national_id"))
    return {
        "name": n.triple_name(n.clean_text(raw.get("full_name"))),
        "national_id": national_id,
        "birth_year": n.birth_year_from_id(national_id) or n.extract_year(raw.get("birth_date")),
    }


NORMALIZERS = {
    T.NATIONAL_ID_FRONT: _front,
    T.NATIONAL_ID_BACK: _back,
    T.SYNDICATE_ID: _syndicate,
    T.BENEFICIARY_NATIONAL_ID: _beneficiary,
    T.BIRTH_CERTIFICATE: _beneficiary,
}


def extract_document(document, *, actor, request=None) -> OcrSuggestion:
    if not settings.OCR_ENABLED:
        raise OcrUnavailable()
    if actor is None or document.application.doctor.user_id != actor.pk:
        raise PermissionDeniedError()
    document_type = T(document.document_type)
    if document_type not in OCR_CAPABLE_TYPES:
        raise ValidationFailed(MSG_NOT_OCR_CAPABLE, fields={"document_type": [MSG_NOT_OCR_CAPABLE]})
    if document.content_type == PDF_CONTENT_TYPE:
        raise OcrUnavailable(MSG_PDF)

    try:
        provider = get_provider()
        raw = provider.extract(
            image=get_storage().download(document.blob_name),
            content_type=document.content_type,
            document_type=document_type,
        )
    except OcrProviderError as exc:
        logger.warning("OCR provider failed", extra={"error_type": type(exc).__name__})
        raise OcrUnavailable() from None

    suggestions = {k: v for k, v in NORMALIZERS[document_type](raw or {}).items() if v}
    record(
        actor=actor,
        action=AuditAction.OCR_REQUESTED,
        obj=document,
        metadata={
            "document_type": document_type,
            "provider": provider.name,
            "fields": sorted(suggestions),
        },
        request=request,
    )
    return OcrSuggestion(
        document_id=str(document.pk), document_type=document_type, fields=suggestions
    )
