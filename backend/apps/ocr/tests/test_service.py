"""OCR service (PROMPT.md §21): suggestions only, nothing saved, audited without values."""

from unittest import mock

import pytest

from apps.applications.factories import ApplicationFactory
from apps.audit.models import AuditAction, AuditLog
from apps.beneficiaries.factories import BeneficiaryFactory
from apps.common.exceptions import OcrUnavailable, ValidationFailed
from apps.doctors.models import Doctor
from apps.documents.services import store_document
from apps.ocr.providers.base import OcrProviderError
from apps.ocr.providers.mock import MockOcrProvider
from apps.ocr.services import extract_document
from apps.reference.constants import DocumentType as T
from tests.files import pdf_bytes, png_upload, upload

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def ocr_on(settings):
    settings.OCR_ENABLED = True
    settings.OCR_PROVIDER = "mock"


def stored(doc_type, app=None, **kwargs):
    app = app or ApplicationFactory()
    return store_document(
        app, document_type=doc_type, upload=kwargs.pop("file", png_upload()),
        actor=app.doctor.user, **kwargs,
    )  # fmt: skip


def test_front_of_national_id_suggestions_are_normalized():
    doc = stored(T.NATIONAL_ID_FRONT)
    result = extract_document(doc, actor=doc.application.doctor.user)
    assert result.document_type == T.NATIONAL_ID_FRONT
    assert result.fields == {
        "member_name": "أحمد محمد علي حسن",
        "national_id": "28506150101234",
        "birth_year": 1985,
        "governorate": "القاهرة",
        "neighborhood": "مدينة نصر",
        "address": "12 شارع عباس العقاد",
    }


def test_back_of_national_id_maps_to_enums():
    doc = stored(T.NATIONAL_ID_BACK)
    fields = extract_document(doc, actor=doc.application.doctor.user).fields
    assert fields == {"gender": "MALE", "religion": "MUSLIM"}


def test_syndicate_card_year_only_from_registration_date():
    doc = stored(T.SYNDICATE_ID)
    fields = extract_document(doc, actor=doc.application.doctor.user).fields
    assert fields == {
        "registration_number": "12345",
        "sub_syndicate": "القاهرة",
        "syndicate_registration_year": 2014,
        "syndicate_type": "HUMAN_MEDICINE",
    }


def test_beneficiary_document_triple_name_and_year():
    app = ApplicationFactory()
    b = BeneficiaryFactory(application=app)
    doc = stored(T.BIRTH_CERTIFICATE, app=app, beneficiary_id=b.pk)
    fields = extract_document(doc, actor=app.doctor.user).fields
    assert fields == {"name": "عمر أحمد محمد", "birth_year": 2015}


def test_extract_returns_suggestions_and_saves_nothing(django_assert_max_num_queries):
    doc = stored(T.NATIONAL_ID_FRONT)
    doctor = Doctor.objects.get(pk=doc.application.doctor_id)
    before = Doctor.objects.filter(pk=doctor.pk).values().get()
    extract_document(doc, actor=doctor.user)
    assert Doctor.objects.filter(pk=doctor.pk).values().get() == before


def test_audit_metadata_has_no_values():
    doc = stored(T.NATIONAL_ID_FRONT)
    extract_document(doc, actor=doc.application.doctor.user)
    entry = AuditLog.objects.get(action=AuditAction.OCR_REQUESTED)
    assert entry.object_id == doc.pk
    assert entry.metadata == {
        "document_type": "NATIONAL_ID_FRONT",
        "provider": "mock",
        "fields": [
            "address",
            "birth_year",
            "governorate",
            "member_name",
            "national_id",
            "neighborhood",
        ],
    }
    assert "28506150101234" not in str(entry.metadata)
    assert "أحمد" not in str(entry.metadata)


def test_disabled_returns_ocr_unavailable(settings):
    settings.OCR_ENABLED = False
    doc = stored(T.NATIONAL_ID_FRONT)
    with pytest.raises(OcrUnavailable):
        extract_document(doc, actor=doc.application.doctor.user)


def test_non_ocr_type_is_a_validation_error():
    doc = stored(T.PAYMENT_RECEIPT)
    with pytest.raises(ValidationFailed):
        extract_document(doc, actor=doc.application.doctor.user)


def test_pdf_is_skipped_with_a_clear_message(settings):
    settings.ALLOW_PDF_DOCUMENTS = True
    doc = stored(T.SYNDICATE_ID, file=upload(pdf_bytes(), "card.pdf", "application/pdf"))
    with pytest.raises(OcrUnavailable) as exc:
        extract_document(doc, actor=doc.application.doctor.user)
    assert "PDF" in exc.value.message


def test_provider_failure_is_ocr_unavailable_without_details():
    doc = stored(T.NATIONAL_ID_FRONT)
    with (
        mock.patch.object(
            MockOcrProvider, "extract", side_effect=OcrProviderError("boom 29501150101234")
        ),
        pytest.raises(OcrUnavailable) as exc,
    ):
        extract_document(doc, actor=doc.application.doctor.user)
    assert "boom" not in exc.value.message


def test_azure_openai_provider_is_not_wired_yet(settings):
    settings.OCR_PROVIDER = "azure_openai"
    doc = stored(T.NATIONAL_ID_FRONT)
    with pytest.raises(OcrUnavailable):
        extract_document(doc, actor=doc.application.doctor.user)


def test_provider_receives_the_document_bytes_and_type():
    doc = stored(T.NATIONAL_ID_BACK)
    with mock.patch.object(MockOcrProvider, "extract", return_value={}) as extract:
        extract_document(doc, actor=doc.application.doctor.user)
    kwargs = extract.call_args.kwargs
    assert kwargs["image"][:4] == b"\x89PNG"
    assert kwargs["content_type"] == "image/png"
    assert kwargs["document_type"] == T.NATIONAL_ID_BACK
