"""`manage.py release_check`: the deep check a release runs before traffic shifts. `/api/ready/`
only says the database answers and the schema is current; this proves the rest."""

from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.db.migrations.recorder import MigrationRecorder

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.oidc import claims
from apps.documents.storage import get_storage
from apps.fees.models import FeeSchedule
from apps.reference import release_checks

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _no_cached_discovery():
    claims._discovery.cache_clear()
    yield
    claims._discovery.cache_clear()


def run(*args) -> tuple[int, dict[str, str], list[str]]:
    """Exit code, each check's `status`, and every output line."""
    out = StringIO()
    code = 0
    try:
        call_command("release_check", *args, stdout=out)
    except SystemExit as exc:
        code = exc.code
    lines = out.getvalue().splitlines()
    found = {}
    for line in lines:
        parts = dict(part.split("=", 1) for part in line.split()[1:] if "=" in part)
        if "name" in parts:
            found[parts["name"]] = parts["status"]
    return code, found, lines


def test_a_healthy_environment_passes_with_one_line_per_check():
    code, found, lines = run()
    assert code == 0
    assert found == {
        "migrations": "ok",
        "cache": "ok",
        "fiscal_year_explicit": "skipped",  # not production settings
        "fee_schedule": "ok",
        "reference_data": "ok",
        "blob_storage": "ok",
        "entra_discovery": "skipped",  # dev sign-in: no authority
    }
    assert lines[-1] == "release_check result=ok"
    assert len(lines) == len(found) + 1


def test_every_line_has_the_documented_shape():
    _, _, lines = run()
    for line in lines[:-1]:
        name, status, detail = line.split()[1:4]
        assert line.startswith("release_check name=")
        assert name.startswith("name=")
        assert status in {"status=ok", "status=skipped", "status=fail"}
        assert detail.startswith("detail=")


def test_an_unapplied_migration_fails():
    MigrationRecorder.Migration.objects.filter(app="fees", name="0008_fy2026_v3_schedule").delete()
    code, found, lines = run()
    assert code == 1
    assert found["migrations"] == "fail"
    assert lines[-1] == "release_check result=fail"


def test_a_cache_failure_fails_and_names_only_the_class():
    with mock.patch.object(release_checks, "cache") as cache:
        cache.set.side_effect = RuntimeError("postgres://user:secret@host")
        code, found, lines = run()
    assert code == 1
    assert found["cache"] == "fail"
    assert "secret" not in "\n".join(lines)
    assert "detail=RuntimeError" in next(line for line in lines if "name=cache" in line)


def test_a_cache_that_returns_something_else_fails():
    with mock.patch.object(release_checks, "cache") as cache:
        cache.get.return_value = "not the value"
        _, found, _ = run()
    assert found["cache"] == "fail"


def test_a_year_without_an_active_fee_schedule_fails():
    code, found, _ = run("--fiscal-year", "2027")
    assert code == 1
    assert found["fee_schedule"] == "fail"


def test_a_next_year_schedule_can_be_checked_before_activating_the_year():
    current = FeeSchedule.objects.get(fiscal_year=2026, is_active=True)
    current.pk = None
    current.fiscal_year = 2027
    current.version = 1
    current.locked_at = None
    current.save()
    code, found, lines = run("--fiscal-year", "2027")
    assert code == 0
    assert found["fee_schedule"] == "ok"
    assert found["fiscal_year_explicit"] == "skipped"
    assert "detail=fiscal_year=2027,version=1" in "\n".join(lines)


def test_production_settings_without_the_variable_fail(monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.production")
    monkeypatch.delenv("CURRENT_FISCAL_YEAR", raising=False)
    code, found, _ = run()
    assert code == 1
    assert found["fiscal_year_explicit"] == "fail"


def test_production_settings_with_the_variable_pass(monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.production")
    monkeypatch.setenv("CURRENT_FISCAL_YEAR", "2026")
    _, found, _ = run()
    assert found["fiscal_year_explicit"] == "ok"


def test_reference_data_failure_fails():
    with mock.patch.object(release_checks, "reference_data", side_effect=KeyError("rule")):
        code, found, _ = run()
    assert code == 1
    assert found["reference_data"] == "fail"


def test_the_blob_probe_stays_outside_the_documents_prefix_and_leaves_nothing():
    names = []
    storage = get_storage()
    with mock.patch.object(storage, "upload", wraps=storage.upload) as upload:
        run()
        names = [call.args[0] for call in upload.call_args_list]
    assert len(names) == 1
    assert names[0].startswith("release-check/")
    assert not list(storage.list("release-check/"))


def test_a_blob_that_reads_back_differently_fails_and_is_still_removed():
    storage = get_storage()
    with mock.patch.object(storage, "download", return_value=b"different"):
        code, found, _ = run()
    assert code == 1
    assert found["blob_storage"] == "fail"
    assert not list(storage.list("release-check/"))


def test_blob_storage_failure_fails():
    with mock.patch.object(release_checks, "get_storage", side_effect=OSError("no account")):
        code, found, _ = run()
    assert code == 1
    assert found["blob_storage"] == "fail"


def test_skip_blob_skips_and_touches_nothing():
    with mock.patch.object(release_checks, "get_storage") as storage:
        code, found, _ = run("--skip-blob")
    assert code == 0
    assert found["blob_storage"] == "skipped"
    storage.assert_not_called()


def _discovery_response(payload):
    response = mock.Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_entra_discovery_passes_on_a_document_with_an_issuer(settings):
    settings.ENTRA_AUTHORITY = "https://tenant.ciamlogin.com/tenant-id"
    issuer = "https://tenant-id.ciamlogin.com/tenant-id/v2.0"
    with mock.patch.object(
        claims.requests, "get", return_value=_discovery_response({"issuer": issuer})
    ) as get:
        code, found, lines = run()
    assert code == 0
    assert found["entra_discovery"] == "ok"
    assert get.call_args.args[0] == (
        "https://tenant.ciamlogin.com/tenant-id/v2.0/.well-known/openid-configuration"
    )
    assert get.call_args.kwargs["timeout"] == 10
    assert "tenant-id" not in "\n".join(lines)


def test_entra_discovery_without_an_issuer_fails(settings):
    settings.ENTRA_AUTHORITY = "https://tenant.ciamlogin.com/tenant-id"
    with mock.patch.object(claims.requests, "get", return_value=_discovery_response({})):
        code, found, _ = run()
    assert code == 1
    assert found["entra_discovery"] == "fail"


def test_entra_discovery_network_failure_fails(settings):
    settings.ENTRA_AUTHORITY = "https://tenant.ciamlogin.com/tenant-id"
    with mock.patch.object(claims.requests, "get", side_effect=OSError("unreachable")):
        code, found, _ = run()
    assert code == 1
    assert found["entra_discovery"] == "fail"


def test_the_admin_check_runs_only_when_asked():
    assert "admin" not in run()[1]


def test_require_admin_fails_without_an_active_admin():
    UserFactory()
    AdminUserFactory(is_active=False)
    code, found, _ = run("--require-admin")
    assert code == 1
    assert found["admin"] == "fail"


def test_require_admin_reports_the_count_only():
    admin = AdminUserFactory()
    code, found, lines = run("--require-admin")
    assert code == 0
    assert found["admin"] == "ok"
    text = "\n".join(lines)
    assert "detail=count=1" in text
    assert admin.email not in text
