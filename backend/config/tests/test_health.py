from unittest import mock

import pytest
from django.db import OperationalError

pytestmark = pytest.mark.django_db


def test_health_is_public_and_does_not_touch_the_database(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_checks_the_database(client):
    response = client.get("/api/ready/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_ready_returns_503_when_db_down(client):
    with mock.patch("config.health.connection") as conn:
        conn.cursor.side_effect = OperationalError("down")
        response = client.get("/api/ready/")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}


def test_health_sets_no_session_cookie(client):
    response = client.get("/api/health/")
    assert "sessionid" not in response.cookies


def test_schema_generates(client):
    response = client.get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/applications/" in paths
    assert "/api/v1/applications/{id}/submit/" in paths


def test_unknown_api_url_returns_envelope_404(client):
    response = client.get("/api/v1/does-not-exist/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
