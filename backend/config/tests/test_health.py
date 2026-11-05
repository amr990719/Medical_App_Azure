from unittest import mock

import pytest
from django.db import OperationalError
from django.db.migrations.recorder import MigrationRecorder

from config import health

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_schema_state():
    health.reset_schema_state()
    yield
    health.reset_schema_state()


def test_health_is_public_and_does_not_touch_the_database(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_checks_the_database_and_the_schema(client):
    response = client.get("/api/ready/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "schema": "ok"}


def test_ready_returns_503_when_db_down(client):
    with mock.patch("config.health.connection") as conn:
        conn.cursor.side_effect = OperationalError("down")
        response = client.get("/api/ready/")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}


def test_ready_returns_503_while_a_migration_is_unapplied(client):
    # Rolled back with the test: this revision's code expects a migration the database lacks.
    MigrationRecorder.Migration.objects.filter(app="fees", name="0008_fy2026_v3_schedule").delete()
    response = client.get("/api/ready/")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "ok", "schema": "pending"}


def test_old_revision_on_a_newer_schema_stays_ready(client):
    # Expand/contract: the previous revision keeps serving after the migrate job ran. It does not
    # know the newer migration, so that row must not make it unready.
    MigrationRecorder.Migration.objects.create(app="fees", name="9999_from_a_newer_release")
    response = client.get("/api/ready/")
    assert response.status_code == 200
    assert response.json()["schema"] == "ok"


def test_ready_remembers_success_and_stops_building_the_graph(client):
    assert client.get("/api/ready/").status_code == 200
    with mock.patch("config.health.MigrationExecutor") as executor:
        response = client.get("/api/ready/")
    assert response.status_code == 200
    executor.assert_not_called()


def test_ready_rechecks_until_the_schema_is_ready(client):
    with mock.patch("config.health.MigrationExecutor") as executor:
        executor.return_value.migration_plan.return_value = [("a migration", False)]
        assert client.get("/api/ready/").status_code == 503
        executor.return_value.migration_plan.return_value = []
        assert client.get("/api/ready/").status_code == 200
        assert client.get("/api/ready/").status_code == 200
    assert executor.call_count == 2


def test_ready_reports_the_database_when_the_schema_check_cannot_read_it(client):
    with mock.patch("config.health.MigrationExecutor", side_effect=OperationalError("down")):
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
