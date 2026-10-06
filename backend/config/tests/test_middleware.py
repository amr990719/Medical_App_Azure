import logging
import re
from unittest import mock

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_response_carries_generated_request_id(client):
    response = client.get("/api/v1/unknown/")
    assert re.fullmatch(r"[0-9a-f]{32}", response["X-Request-ID"])


def test_safe_incoming_request_id_is_propagated(client):
    response = client.get("/api/v1/unknown/", HTTP_X_REQUEST_ID="abc-123_DEF")
    assert response["X-Request-ID"] == "abc-123_DEF"


def test_unsafe_incoming_request_id_is_replaced(client):
    response = client.get("/api/v1/unknown/", HTTP_X_REQUEST_ID="evil\nheader" + "x" * 200)
    assert re.fullmatch(r"[0-9a-f]{32}", response["X-Request-ID"])


def test_access_log_is_structured_and_masks_national_ids_in_path(client, caplog):
    with caplog.at_level(logging.INFO, logger="apps.access"):
        client.get("/api/v1/unknown/29501150101234/?q=29501150101234")
    record = next(r for r in caplog.records if r.name == "apps.access")
    assert record.method == "GET"
    assert record.status == 404
    assert isinstance(record.duration_ms, float)
    assert record.request_id
    assert "29501150101234" not in record.path
    assert "?" not in record.path  # query strings are never logged
    assert record.user_id is None


# --- Request body cap (uploads are refused before Django parses or spools the body) ---------


def test_oversized_body_is_refused_before_parsing(settings):
    from apps.applications.factories import ApplicationFactory
    from apps.documents.models import Document

    app = ApplicationFactory()
    client = APIClient()
    client.force_authenticate(app.doctor.user)
    declared = settings.MAX_UPLOAD_BYTES + 2 * 1024 * 1024
    with mock.patch(
        "django.http.multipartparser.MultiPartParser.parse", side_effect=AssertionError("parsed")
    ):
        response = client.post(
            f"/api/v1/applications/{app.pk}/documents/",
            data=b"x",
            content_type="multipart/form-data; boundary=x",
            CONTENT_LENGTH=str(declared),
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert response.json()["error"]["message"] == "حجم الملف يجب أن يكون أقل من 8 ميجابايت"
    assert "حجم الملف".encode() in response.content  # raw UTF-8 like DRF, not escapes
    assert Document.objects.count() == 0


def test_a_body_within_the_cap_reaches_the_view(settings):
    response = APIClient().post(
        "/api/v1/auth/logout/", data=b"{}", content_type="application/json",
        CONTENT_LENGTH=str(settings.MAX_UPLOAD_BYTES),
    )  # fmt: skip
    assert response.status_code in {401, 403}  # the view answered, not the cap
