"""Document endpoints (PROMPT.md §24): upload, metadata, authorized content, delete."""

from datetime import UTC, datetime
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest
from rest_framework.test import APIClient

from apps.accounts.factories import AdminUserFactory
from apps.applications.factories import ApplicationFactory
from apps.beneficiaries.factories import BeneficiaryFactory
from apps.doctors.factories import DoctorFactory
from apps.documents.models import Document
from apps.documents.services import store_document
from apps.reference.constants import ApplicationStatus as S
from apps.reference.constants import DocumentType as T
from tests.files import EXE_BYTES, pdf_bytes, png_upload, upload

pytestmark = pytest.mark.django_db


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def upload_url(app) -> str:
    return f"/api/v1/applications/{app.pk}/documents/"


def stored(app=None, doc_type=T.SYNDICATE_ID, status=None):
    app = app or ApplicationFactory()
    doc = store_document(app, document_type=doc_type, upload=png_upload(), actor=app.doctor.user)
    if status:
        app.status, app.reference_number = status, "MED-2026-000001"
        app.save()
    return doc


# --- upload -------------------------------------------------------------------------------------


def test_upload_returns_summary_without_storage_details():
    app = ApplicationFactory()
    response = client_for(app.doctor.user).post(
        upload_url(app),
        {"file": png_upload(name="وجه.png"), "document_type": "NATIONAL_ID_FRONT"},
        format="multipart",
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["document_type"] == "NATIONAL_ID_FRONT"
    assert body["original_filename"] == "وجه.png"
    assert body["content_type"] == "image/png"
    assert body["content_url"] == f"/api/v1/documents/{body['id']}/content/"
    assert "blob_name" not in body
    assert "applications/" not in str(body)


def test_upload_for_a_beneficiary():
    app = ApplicationFactory()
    b = BeneficiaryFactory(application=app)
    response = client_for(app.doctor.user).post(
        upload_url(app),
        {"file": png_upload(), "document_type": "BIRTH_CERTIFICATE", "beneficiary_id": str(b.pk)},
        format="multipart",
    )
    assert response.status_code == 201
    assert response.json()["beneficiary_id"] == str(b.pk)


def test_upload_exe_renamed_jpg_rejected_with_code():
    app = ApplicationFactory()
    response = client_for(app.doctor.user).post(
        upload_url(app),
        {
            "file": upload(EXE_BYTES, "receipt.jpg", "image/jpeg"),
            "document_type": "PAYMENT_RECEIPT",
        },
        format="multipart",
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_tiny_receipt_rejected_with_code():
    app = ApplicationFactory()
    response = client_for(app.doctor.user).post(
        upload_url(app),
        {"file": png_upload((10, 10)), "document_type": "PAYMENT_RECEIPT"},
        format="multipart",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMAGE_TOO_SMALL"


def test_upload_requires_file_and_known_type():
    app = ApplicationFactory()
    response = client_for(app.doctor.user).post(
        upload_url(app), {"document_type": "PASSPORT"}, format="multipart"
    )
    assert response.status_code == 400
    assert set(response.json()["error"]["fields"]) == {"file", "document_type"}


def test_upload_to_another_doctors_application_404():
    victim = ApplicationFactory()
    response = client_for(DoctorFactory().user).post(
        upload_url(victim),
        {"file": png_upload(), "document_type": "SYNDICATE_ID"},
        format="multipart",
    )
    assert response.status_code == 404
    assert not Document.all_objects.exists()


def test_upload_when_not_editable_409():
    app = ApplicationFactory(status=S.SUBMITTED, reference_number="MED-2026-000001")
    response = client_for(app.doctor.user).post(
        upload_url(app), {"file": png_upload(), "document_type": "SYNDICATE_ID"}, format="multipart"
    )
    assert response.status_code == 409


def test_uploads_are_rate_limited():
    from rest_framework.throttling import ScopedRateThrottle

    app = ApplicationFactory()
    client = client_for(app.doctor.user)
    with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"uploads": "2/min"}):
        statuses = [
            client.post(
                upload_url(app), {"file": png_upload(), "document_type": "SYNDICATE_ID"},
                format="multipart",
            ).status_code
            for _ in range(3)
        ]  # fmt: skip
    assert statuses == [201, 201, 429]


def test_admin_cannot_upload():
    app = ApplicationFactory()
    response = client_for(AdminUserFactory()).post(
        upload_url(app), {"file": png_upload(), "document_type": "SYNDICATE_ID"}, format="multipart"
    )
    assert response.status_code == 403


# --- metadata and content -----------------------------------------------------------------------


def test_metadata_for_owner():
    doc = stored()
    body = client_for(doc.application.doctor.user).get(f"/api/v1/documents/{doc.pk}/").json()
    assert body["id"] == str(doc.pk)


def test_content_streams_with_safe_headers():
    doc = stored()
    response = client_for(doc.application.doctor.user).get(f"/api/v1/documents/{doc.pk}/content/")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response["Content-Disposition"].startswith("inline")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "no-store" in response["Cache-Control"]
    assert response.content[:4] == b"\x89PNG"


def test_pdf_content_is_a_download_never_framed(settings):
    # Q-T17: an uploaded PDF is never rendered inside the app (no iframe, no inline viewer):
    # it is served as an attachment and keeps the sandbox CSP, nosniff and X-Frame-Options.
    settings.ALLOW_PDF_DOCUMENTS = True
    app = ApplicationFactory()
    doc = store_document(
        app,
        document_type=T.SYNDICATE_ID,
        upload=upload(pdf_bytes(), "كارنيه.pdf", "application/pdf"),
        actor=app.doctor.user,
    )
    response = client_for(app.doctor.user).get(f"/api/v1/documents/{doc.pk}/content/")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("attachment")
    assert "sandbox" in response["Content-Security-Policy"]
    assert response["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize("path", ["", "content/"])
def test_content_requires_owner_or_admin(path):
    doc = stored(status=S.SUBMITTED)
    url = f"/api/v1/documents/{doc.pk}/{path}"
    assert APIClient().get(url).status_code == 401
    assert client_for(DoctorFactory().user).get(url).status_code == 404  # IDOR → 404
    assert client_for(AdminUserFactory()).get(url).status_code == 200
    assert client_for(doc.application.doctor.user).get(url).status_code == 200


def test_admin_cannot_read_documents_of_an_unsubmitted_draft():
    doc = stored()
    assert (
        client_for(AdminUserFactory()).get(f"/api/v1/documents/{doc.pk}/content/").status_code
        == 404
    )


def test_soft_deleted_document_is_gone():
    doc = stored()
    Document.objects.filter(pk=doc.pk).update(deleted_at=datetime.now(UTC))
    client = client_for(doc.application.doctor.user)
    assert client.get(f"/api/v1/documents/{doc.pk}/").status_code == 404
    assert client.get(f"/api/v1/documents/{doc.pk}/content/").status_code == 404


def test_content_sas_redirect_ttl_at_most_300s(settings):
    from apps.documents.tests.test_storage import OFFLINE_CONNECTION

    doc = stored()
    settings.BLOB_BACKEND = "azure"
    settings.BLOB_CONNECTION_STRING = OFFLINE_CONNECTION
    settings.DOCUMENT_CONTENT_DELIVERY = "sas"
    response = client_for(doc.application.doctor.user).get(f"/api/v1/documents/{doc.pk}/content/")
    assert response.status_code == 302
    params = {k: v[0] for k, v in parse_qs(urlparse(response["Location"]).query).items()}
    expiry = datetime.strptime(params["se"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert 0 < (expiry - datetime.now(UTC)).total_seconds() <= 300
    assert params["sp"] == "r"
    assert response["Cache-Control"].startswith("no-store")


# --- delete -------------------------------------------------------------------------------------


def test_delete_by_owner_while_editable():
    doc = stored()
    response = client_for(doc.application.doctor.user).delete(f"/api/v1/documents/{doc.pk}/")
    assert response.status_code == 204
    assert Document.all_objects.get(pk=doc.pk).deleted_at is not None


def test_delete_only_when_editable():
    doc = stored(status=S.SUBMITTED)
    response = client_for(doc.application.doctor.user).delete(f"/api/v1/documents/{doc.pk}/")
    assert response.status_code == 409
    assert Document.objects.filter(pk=doc.pk).exists()


def test_delete_by_other_doctor_or_admin_refused():
    doc = stored(status=S.SUBMITTED)
    assert (
        client_for(DoctorFactory().user).delete(f"/api/v1/documents/{doc.pk}/").status_code == 404
    )
    assert client_for(AdminUserFactory()).delete(f"/api/v1/documents/{doc.pk}/").status_code == 403
    assert Document.objects.filter(pk=doc.pk).exists()
