"""After a database restore: stop old outbox rows from sending a second time (`--apply`)."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from apps.notifications import services
from apps.notifications.modes import SENDING_MODES


def _check_restore_point(value: str) -> None:
    try:
        parsed = parse_datetime(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        raise CommandError("--restored-to must be an ISO 8601 time with a timezone.")


class Command(BaseCommand):
    help = (
        "Rows waiting or mid-send in a restored database may already have gone out. Without "
        "--apply this only counts them; with --apply each ends SUPERSEDED with "
        "RESTORE_RECONCILED and never sends. Refuses while NOTIFICATIONS_MODE can send. An admin "
        "can resend a row deliberately: POST /admin/applications/{id}/notifications/{nid}/resend/."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--restored-to", required=True, help="The restore point: ISO 8601, with a timezone."
        )
        parser.add_argument(
            "--apply", action="store_true", help="Change the rows (default: count)."
        )

    def handle(self, *args, restored_to, apply=False, **options):
        _check_restore_point(restored_to)
        if settings.NOTIFICATIONS_MODE in SENDING_MODES:
            raise CommandError(
                "NOTIFICATIONS_MODE must not be a sending mode: pause sending first."
            )

        mode = "apply" if apply else "dry-run"
        self.stdout.write(f"reconcile_notifications restored_to={restored_to} mode={mode}")
        rows = services.in_flight_counts()
        for row in rows:
            self.stdout.write(
                f"reconcile_notifications status={row['status']} event={row['event']} "
                f"count={row['count']}"
            )
        total = sum(row["count"] for row in rows)
        if apply:
            total = services.reconcile_after_restore()
        self.stdout.write(f"reconcile_notifications total={total}")
