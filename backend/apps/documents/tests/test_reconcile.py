"""`manage.py reconcile_documents`: compares database rows with blob bytes after a restore. It only
reads: the operator decides what to do with what it reports."""

from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.applications.factories import ApplicationFactory
from apps.documents import reconcile
from apps.documents.models import Document
from apps.documents.services import store_document
from apps.documents.storage import get_storage
from apps.reference.constants import DocumentType as T
from tests.files import png_upload

pytestmark = pytest.mark.django_db

RESTORED_TO = datetime(2026, 11, 5, 8, 0, tzinfo=UTC)
ORPHAN = "applications/11111111-1111-1111-1111-111111111111/doctor/other-1.png"


def stored():
    app = ApplicationFactory()
    return store_document(
        app, document_type=T.SYNDICATE_ID, upload=png_upload(), actor=app.doctor.user
    )


def orphan(name=ORPHAN, when=RESTORED_TO - timedelta(hours=1)) -> str:
    storage = get_storage()
    storage.upload(name, b"x", content_type="image/png")
    storage.set_last_modified(name, when)
    return name


def run(*args) -> str:
    out = StringIO()
    call_command("reconcile_documents", *args, stdout=out)
    return out.getvalue()


def blobs() -> list[str]:
    return sorted(b.name for b in get_storage().list(""))


def test_a_consistent_store_reports_nothing_and_exits_0():
    stored()
    output = run()
    assert "missing_blobs=0" in output
    assert "orphan_blobs=0" in output


def test_a_row_without_its_bytes_is_listed_and_exits_1():
    doc = stored()
    get_storage().delete(doc.blob_name)
    out = StringIO()
    with pytest.raises(SystemExit) as ei:
        call_command("reconcile_documents", stdout=out)
    assert ei.value.code == 1
    assert "missing_blobs=1" in out.getvalue()
    assert f"missing_document={doc.pk}" in out.getvalue()


def test_a_soft_deleted_row_still_inside_the_grace_period_should_have_bytes():
    doc = stored()
    Document.all_objects.filter(pk=doc.pk).update(deleted_at=timezone.now())
    get_storage().delete(doc.blob_name)
    with pytest.raises(SystemExit):
        run()


def test_a_purged_row_is_not_expected_to_have_bytes():
    doc = stored()
    Document.all_objects.filter(pk=doc.pk).update(
        deleted_at=timezone.now(), blob_purged_at=timezone.now()
    )
    get_storage().delete(doc.blob_name)
    assert "missing_blobs=0" in run()


def test_an_orphan_is_listed_but_does_not_fail_the_run():
    name = orphan()
    output = run()
    assert "orphan_blobs=1" in output
    assert f"orphan_blob={name}" in output


def test_only_orphans_newer_than_the_restore_point_are_counted_as_lost_uploads():
    orphan()
    newer = orphan(
        "applications/22222222-2222-2222-2222-222222222222/doctor/other-2.png",
        RESTORED_TO + timedelta(minutes=5),
    )
    output = run("--restored-to", RESTORED_TO.isoformat())
    assert "orphan_blobs=2" in output
    assert "orphans_newer_than_restore_point=1" in output
    assert f"newer_orphan={newer}" in output


def test_without_a_restore_point_the_newer_orphans_are_not_reported():
    orphan()
    assert "orphans_newer_than_restore_point" not in run()


@pytest.mark.parametrize("value", ["yesterday", "2026-11-05T08:00:00"])
def test_a_bad_restore_point_is_refused(value):
    with pytest.raises(CommandError, match="restored-to"):
        run("--restored-to", value)


def test_it_changes_nothing():
    doc, name = stored(), orphan()
    before = blobs()
    run("--restored-to", RESTORED_TO.isoformat())
    assert blobs() == before
    assert name in before
    assert Document.all_objects.get(pk=doc.pk).blob_purged_at is None


def test_the_limit_shortens_the_list_but_never_the_total():
    for number in range(3):
        orphan(f"applications/33333333-3333-3333-3333-333333333333/doctor/other-{number}.png")
    output = run("--limit", "1")
    assert "orphan_blobs=3" in output
    assert output.count("orphan_blob=") == 1


def test_orphans_are_found_across_batches(monkeypatch):
    monkeypatch.setattr(reconcile, "BATCH", 2)
    doc = stored()
    for number in range(5):
        orphan(f"applications/44444444-4444-4444-4444-444444444444/doctor/other-{number}.png")
    report = reconcile.reconcile_documents(get_storage())
    assert len(report.orphan_blobs) == 5
    assert doc.blob_name not in report.orphan_blobs
    assert report.missing_documents == []


def test_blobs_outside_the_documents_prefix_are_ignored():
    # The release check's probe lives under another prefix and is never a document's orphan.
    get_storage().upload("release-check/probe.txt", b"x", content_type="text/plain")
    assert "orphan_blobs=0" in run()
