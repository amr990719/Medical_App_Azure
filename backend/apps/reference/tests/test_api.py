import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.reference.constants import GOVERNORATES

pytestmark = pytest.mark.django_db
URL = "/api/v1/reference-data/"


def get(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    return client.get(URL)


def test_reference_data_requires_authentication():
    assert get().status_code == 401


def test_reference_data_shape_and_27_governorates():
    data = get(UserFactory()).json()
    assert data["fiscal_year"] == 2026
    assert data["max_beneficiaries"] == 10
    assert data["governorates"] == GOVERNORATES
    assert len(data["governorates"]) == 27
    assert {"value": "HUMAN_MEDICINE", "label": "بشري"} in data["syndicate_types"]
    assert {"value": "PENSIONER", "label": "معاش"} in data["work_statuses"]
    assert {"value": "MUSLIM", "label": "مسلم"} in data["religions"]
    assert {"value": "FEMALE", "label": "أنثى"} in data["genders"]
    assert [(k["value"], k["label"], k["fee_key"]) for k in data["kinships"]] == [
        ("MOTHER", "أم", "parent"),
        ("FATHER", "أب", "parent"),
        ("SON_MINOR", "ابن/ابنة (18 سنة أو أقل)", "child"),
        ("SON_UNIVERSITY", "ابن/ابنة (طالب جامعي)", "grad_son"),
        ("SON_GRADUATE", "ابن/ابنة (خريج)", "grad_son"),
        ("DAUGHTER", "ابنة", "child"),
        ("HUSBAND", "زوج", "spouse"),
        ("WIFE", "زوجة", "spouse"),
    ]
    assert {"value": "ADDITION", "label": "إضافة"} in data["application_types"]
    assert {"value": "NEEDS_CORRECTION", "label": "يحتاج تصحيح"} in data["statuses"]
    assert {"value": "PENDING_REVIEW", "label": "بانتظار التأكيد"} in data["payment_statuses"]
    assert data["ocr_enabled"] is False
    assert data["features"] == {
        "require_member_photo": False,
        "allow_pdf": False,
        "allow_heic": False,
    }
    assert data["upload"] == {
        "max_bytes": 8 * 1024 * 1024,
        "receipt_min_width": 400,
        "receipt_min_height": 300,
        "accepted_content_types": ["image/jpeg", "image/png", "image/webp"],
        "image_content_types": ["image/jpeg", "image/png", "image/webp"],
    }


def test_document_rules_come_from_the_single_rules_table():
    from apps.reference.document_rules import rules_as_reference_data

    data = get(UserFactory()).json()
    assert data["document_rules"] == rules_as_reference_data(
        require_photo=False, child_id_age=16, photo_exempt_child_age=3
    )
    ocr = {t["type"] for t in data["document_rules"]["document_types"] if t["ocr_capable"]}
    assert ocr == {
        "NATIONAL_ID_FRONT",
        "NATIONAL_ID_BACK",
        "SYNDICATE_ID",
        "BENEFICIARY_NATIONAL_ID",
        "BIRTH_CERTIFICATE",
    }


@override_settings(ALLOW_PDF_DOCUMENTS=True, OCR_ENABLED=True, MAX_BENEFICIARIES=6)
def test_reference_data_follows_settings():
    data = get(AdminUserFactory()).json()
    assert data["max_beneficiaries"] == 6
    assert data["ocr_enabled"] is True
    assert data["features"]["allow_pdf"] is True
    assert "application/pdf" in data["upload"]["accepted_content_types"]
    # Photos stay image-only even when PDF documents are enabled.
    assert data["upload"]["image_content_types"] == ["image/jpeg", "image/png", "image/webp"]
