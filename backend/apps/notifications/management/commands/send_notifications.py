"""Scheduled job: sweep old notifications and send the due ones (`entrypoint.sh notify`)."""

import logging

from django.core.management.base import BaseCommand

from apps.notifications.sender import run_once
from config.telemetry import flush_telemetry

logger = logging.getLogger("apps.notifications")


class Command(BaseCommand):
    help = "Expire, recover and send due doctor notifications (WhatsApp, then email fallback)."

    def handle(self, *args, **options):
        try:
            run_once()
        except Exception as exc:
            # Class name only: the message or a traceback could hold a recipient.
            logger.error("notify_run_failed", extra={"error_type": type(exc).__name__})
            # Exit 1 so the job shows as failed, without a traceback that could hold a recipient.
            raise SystemExit(1) from None
        finally:
            flush_telemetry()
