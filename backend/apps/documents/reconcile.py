"""Database rows against blob bytes, in both directions. Reads only (PROMPT.md §19, §48).

After a database restore the two can disagree: a row may point at bytes that are gone, and an
upload made after the restore point has bytes but no row. `cleanup_blobs` would delete the second
kind as orphans, which is why the recovery runbook keeps it paused until this report is reviewed.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from itertools import islice
from uuid import UUID

from .models import Document
from .naming import BLOB_PREFIX
from .storage import BlobStorage

BATCH = 500


def batches(iterable: Iterable, size: int) -> Iterator[list]:
    iterator = iter(iterable)
    while batch := list(islice(iterator, size)):
        yield batch


def unknown_blob_names(names: Iterable[str]) -> Iterator[str]:
    """The names no Document row holds, soft-deleted rows included. Checked in batches."""
    for names_batch in batches(names, BATCH):
        known = set(
            Document.all_objects.filter(blob_name__in=names_batch).values_list(
                "blob_name", flat=True
            )
        )
        yield from (name for name in names_batch if name not in known)


@dataclass
class DocumentReport:
    missing_documents: list[UUID] = field(default_factory=list)
    orphan_blobs: list[str] = field(default_factory=list)
    newer_orphans: list[str] = field(default_factory=list)


def reconcile_documents(
    storage: BlobStorage, *, restored_to: datetime | None = None
) -> DocumentReport:
    """Compare every document row that should have bytes with the blobs under `applications/`.

    A blob in soft delete is not listed, so its row counts as missing until it is undeleted.
    """
    modified = {blob.name: blob.last_modified for blob in storage.list(BLOB_PREFIX)}
    report = DocumentReport()
    expected = Document.all_objects.filter(blob_purged_at__isnull=True)
    for pk, blob_name in expected.values_list("pk", "blob_name").iterator():
        if blob_name not in modified:
            report.missing_documents.append(pk)
    report.orphan_blobs = list(unknown_blob_names(modified))
    if restored_to is not None:
        report.newer_orphans = [
            name for name in report.orphan_blobs if modified[name] > restored_to
        ]
    return report
