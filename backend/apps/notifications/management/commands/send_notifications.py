"""Scheduled job: sweep old notifications and send the due ones (`entrypoint.sh notify`)."""

import logging

from django.core.management.base import BaseCommand
from opentelemetry._logs import get_logger_provider

from apps.notifications.sender import run_once

logger = logging.getLogger("apps.notifications")


def _flush_telemetry() -> None:
    """Push buffered logs out before the container exits. Never raises."""
    try:
        flush = getattr(get_logger_provider(), "force_flush", None)
        if callable(flush):
            flush()
    except Exception:  # noqa: S110 - a telemetry failure must not fail the job
        pass


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
            _flush_telemetry()
