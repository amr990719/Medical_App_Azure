"""Report rows without bytes and bytes without rows after a restore. Changes nothing.

Exit 1 when a row's bytes are missing, so a script stops there. Orphans alone exit 0: they are
listed for the operator, and `cleanup_blobs` stays paused until they have been reviewed.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from apps.documents.reconcile import reconcile_documents
from apps.documents.storage import get_storage

DEFAULT_LIMIT = 200


def _restore_point(value: str):
    try:
        parsed = parse_datetime(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        raise CommandError("--restored-to must be an ISO 8601 time with a timezone.")
    return parsed


class Command(BaseCommand):
    help = (
        "Compare document rows with blob bytes. Read-only: reports missing blobs and orphan "
        "blobs, and with --restored-to the orphans newer than the restore point (uploads the "
        "restored database lost, which cleanup_blobs would delete)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--restored-to", default=None, help="ISO 8601, with a timezone.")
        parser.add_argument(
            "--limit", type=int, default=DEFAULT_LIMIT, help="Most items listed per kind."
        )

    def handle(self, *args, restored_to=None, limit=DEFAULT_LIMIT, **options):
        restore_point = _restore_point(restored_to) if restored_to else None
        report = reconcile_documents(get_storage(), restored_to=restore_point)

        def section(total_label: str, item_label: str, items: list) -> None:
            self.stdout.write(f"reconcile_documents {total_label}={len(items)}")
            for item in items[:limit]:
                self.stdout.write(f"reconcile_documents {item_label}={item}")

        section("missing_blobs", "missing_document", report.missing_documents)
        section("orphan_blobs", "orphan_blob", report.orphan_blobs)
        if restore_point is not None:
            section("orphans_newer_than_restore_point", "newer_orphan", report.newer_orphans)
        if report.missing_documents:
            raise SystemExit(1)
