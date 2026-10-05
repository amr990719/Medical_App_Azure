"""Remove blob bytes nobody references any more (PROMPT.md §19). Runnable as a scheduled
Container Apps job.

1. Documents soft-deleted more than `--grace-hours` ago: delete the blob, stamp `blob_purged_at`.
2. Orphan blobs under `applications/` with no metadata row at all (upload crashed before the
   database commit) and older than the grace period: delete.
"""

from datetime import timedelta
from itertools import islice

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.documents.models import Document
from apps.documents.naming import BLOB_PREFIX
from apps.documents.storage import get_storage

BATCH = 500


def _batches(iterable, size):
    iterator = iter(iterable)
    while batch := list(islice(iterator, size)):
        yield batch


class Command(BaseCommand):
    help = "Delete blobs of soft-deleted documents and orphan blobs older than the grace period."

    def add_arguments(self, parser):
        parser.add_argument("--grace-hours", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, grace_hours=None, dry_run=False, **options):
        hours = settings.BLOB_CLEANUP_GRACE_HOURS if grace_hours is None else grace_hours
        cutoff = timezone.now() - timedelta(hours=hours)
        storage = get_storage()

        purged = 0
        expired = Document.all_objects.filter(deleted_at__lt=cutoff, blob_purged_at__isnull=True)
        for document in expired.only("pk", "blob_name").iterator():
            purged += 1
            if not dry_run:
                storage.delete(document.blob_name)
                Document.all_objects.filter(pk=document.pk).update(blob_purged_at=timezone.now())

        orphans = 0
        old_blobs = (b.name for b in storage.list(BLOB_PREFIX) if b.last_modified < cutoff)
        for names in _batches(old_blobs, BATCH):
            known = set(
                Document.all_objects.filter(blob_name__in=names).values_list("blob_name", flat=True)
            )
            for name in names:
                if name not in known:
                    orphans += 1
                    if not dry_run:
                        storage.delete(name)

        mode = " (dry run)" if dry_run else ""
        self.stdout.write(f"cleanup_blobs{mode}: purged={purged} orphans={orphans}")
