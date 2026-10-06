import logging
import re

import pytest

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
