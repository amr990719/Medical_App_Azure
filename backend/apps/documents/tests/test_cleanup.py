"""`manage.py cleanup_blobs`: removes blobs of documents soft-deleted beyond the grace period and
orphan blobs with no metadata (PROMPT.md §19, prototype defect 7)."""

import logging
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.applications.factories import ApplicationFactory
from apps.documents.management.commands import cleanup_blobs as command
from apps.documents.models import Document
from apps.documents.services import store_document
from apps.documents.storage import get_storage
from apps.reference.constants import DocumentType as T
from tests.files import png_upload

pytestmark = pytest.mark.django_db


def stored(app=None):
    app = app or ApplicationFactory()
    return store_document(
        app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=app.doctor.user
    )


def run(*args) -> str:
    out = StringIO()
    call_command("cleanup_blobs", *args, stdout=out)
    return out.getvalue()


def age(document, hours: int) -> None:
    Document.all_objects.filter(pk=document.pk).update(
        deleted_at=timezone.now() - timedelta(hours=hours)
    )


def test_cleanup_removes_soft_deleted_after_grace():
    doc = stored()
    age(doc, 25)
    run()
    assert not get_storage().exists(doc.blob_name)
    doc = Document.all_objects.get(pk=doc.pk)
    assert doc.blob_purged_at is not None


def test_cleanup_keeps_recently_deleted_and_active_documents():
    recent, active = stored(), stored()
    age(recent, 1)
    run()
    assert get_storage().exists(recent.blob_name)
    assert get_storage().exists(active.blob_name)


def test_orphan_blob_without_metadata_removed_after_grace():
    storage = get_storage()
    storage.upload("applications/x/doctor/orphan.png", b"x", content_type="image/png")
    storage.set_last_modified(
        "applications/x/doctor/orphan.png", timezone.now() - timedelta(hours=30)
    )
    storage.upload("applications/x/doctor/fresh.png", b"x", content_type="image/png")
    output = run()
    assert not storage.exists("applications/x/doctor/orphan.png")
    assert storage.exists("applications/x/doctor/fresh.png")  # may still be mid-upload
    assert "orphans=1" in output


def test_dry_run_deletes_nothing():
    doc = stored()
    age(doc, 48)
    output = run("--dry-run")
    assert get_storage().exists(doc.blob_name)
    assert Document.all_objects.get(pk=doc.pk).blob_purged_at is None
    assert "purged=1" in output


def test_cleanup_is_idempotent():
    doc = stored()
    age(doc, 48)
    run()
    assert "purged=0" in run()


def test_grace_period_is_configurable():
    doc = stored()
    age(doc, 3)
    run("--grace-hours", "2")
    assert not get_storage().exists(doc.blob_name)


# --- Telemetry: a failed or missed run must be alertable (service alerts) -------------------------


def test_a_run_logs_cleanup_run_with_its_counts_and_flushes(monkeypatch, caplog):
    flushed = []
    monkeypatch.setattr(command, "flush_telemetry", lambda: flushed.append(True))
    doc = stored()
    age(doc, 48)
    with caplog.at_level(logging.INFO, logger="apps.documents"):
        run()
    (record,) = [r for r in caplog.records if r.getMessage() == "cleanup_run"]
    assert (record.purged, record.orphans, record.dry_run) == (1, 0, False)
    assert flushed == [True]


def test_a_dry_run_says_so_in_cleanup_run(caplog):
    with caplog.at_level(logging.INFO, logger="apps.documents"):
        run("--dry-run")
    (record,) = [r for r in caplog.records if r.getMessage() == "cleanup_run"]
    assert record.dry_run is True


def test_a_failed_run_logs_the_class_name_and_exits_1_without_a_traceback(monkeypatch, caplog):
    def boom():
        raise RuntimeError("applications/secret-blob-name.png")

    monkeypatch.setattr(command, "get_storage", boom)
    flushed = []
    monkeypatch.setattr(command, "flush_telemetry", lambda: flushed.append(True))
    with caplog.at_level(logging.INFO, logger="apps.documents"), pytest.raises(SystemExit) as ei:
        run()
    assert ei.value.code == 1
    assert ei.value.__suppress_context__ and ei.value.__cause__ is None
    assert flushed == [True]
    (record,) = [r for r in caplog.records if r.getMessage() == "cleanup_run_failed"]
    assert record.levelno == logging.ERROR
    assert record.error_type == "RuntimeError"
    assert "secret-blob-name" not in caplog.text
    assert not [r for r in caplog.records if r.getMessage() == "cleanup_run"]
