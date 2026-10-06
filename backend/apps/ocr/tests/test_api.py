"""`POST /api/v1/documents/{id}/extract/` (PROMPT.md §21.1)."""

from unittest import mock

import pytest
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory
from apps.applications.factories import ApplicationFactory
from apps.doctors.factories import DoctorFactory
from apps.documents.services import store_document
from apps.reference.constants import DocumentType as T
from tests.files import png_upload

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def ocr_on(settings):
    settings.OCR_ENABLED = True
    settings.OCR_PROVIDER = "mock"


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def stored(doc_type=T.NATIONAL_ID_FRONT):
    app = ApplicationFactory()
    return store_document(app, document_type=doc_type, upload=png_upload(), actor=app.doctor.user)


def extract_url(doc) -> str:
    return f"/api/v1/documents/{doc.pk}/extract/"


def test_extract_returns_suggestions():
    doc = stored()
    response = client_for(doc.application.doctor.user).post(extract_url(doc))
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == str(doc.pk)
    assert body["document_type"] == "NATIONAL_ID_FRONT"
    assert body["fields"]["national_id"] == "28506150101234"


def test_extract_only_suggests_and_saves_nothing():
    # PROMPT.md §21 / defect 2.3 #9: OCR suggests; the doctor's data changes only via autosave.
    from apps.applications.models import InsuranceApplication
    from apps.beneficiaries.models import Beneficiary
    from apps.doctors.models import Doctor

    doc = stored()
    application, doctor = doc.application, doc.application.doctor
    before = (
        Doctor.objects.filter(pk=doctor.pk).values().get(),
        InsuranceApplication.objects.filter(pk=application.pk).values().get(),
        Beneficiary.objects.filter(application=application).count(),
    )
    response = client_for(doctor.user).post(extract_url(doc))
    assert response.status_code == 200
    assert response.json()["fields"]["national_id"] != doctor.national_id
    after = (
        Doctor.objects.filter(pk=doctor.pk).values().get(),
        InsuranceApplication.objects.filter(pk=application.pk).values().get(),
        Beneficiary.objects.filter(application=application).count(),
    )
    assert after == before


def test_other_users_document_404():
    doc = stored()
    assert client_for(DoctorFactory().user).post(extract_url(doc)).status_code == 404


def test_admin_cannot_run_ocr():
    doc = stored()
    assert client_for(AdminUserFactory()).post(extract_url(doc)).status_code == 403


def test_anonymous_401():
    assert APIClient().post(extract_url(stored())).status_code == 401


def test_disabled_returns_ocr_unavailable(settings):
    settings.OCR_ENABLED = False
    doc = stored()
    response = client_for(doc.application.doctor.user).post(extract_url(doc))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "OCR_UNAVAILABLE"


def test_non_ocr_type_400():
    doc = stored(T.PAYMENT_RECEIPT)
    response = client_for(doc.application.doctor.user).post(extract_url(doc))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_rate_limit_31st_call_429():
    doc = stored()
    client = client_for(doc.application.doctor.user)
    statuses = [client.post(extract_url(doc)).status_code for _ in range(31)]
    assert statuses[:30] == [200] * 30
    assert statuses[30] == 429
    assert client.post(extract_url(doc)).json()["error"]["code"] == "RATE_LIMITED"


def test_rate_limit_is_per_user():
    from rest_framework.throttling import ScopedRateThrottle

    first, second = stored(), stored()
    with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"ocr": "1/hour"}):
        assert client_for(first.application.doctor.user).post(extract_url(first)).status_code == 200
        assert client_for(first.application.doctor.user).post(extract_url(first)).status_code == 429
        assert (
            client_for(second.application.doctor.user).post(extract_url(second)).status_code == 200
        )
