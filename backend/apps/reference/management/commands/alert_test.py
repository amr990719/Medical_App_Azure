"""Controlled alert test (docs/production-acceptance.md): one harmless trace that the alert rule
`ops-alert-test` turns into an email, proving the path from the app to a person."""

import logging

from django.core.management.base import BaseCommand

from config.telemetry import flush_telemetry

logger = logging.getLogger("apps.reference")


class Command(BaseCommand):
    help = (
        "Emit the trace the ops-alert-test rule alerts on. Changes no data, sends no notification."
    )

    def handle(self, *args, **options):
        logger.info("ops_alert_test")
        flush_telemetry()
        self.stdout.write(
            "alert_test: trace emitted; the alert email should arrive within 15 minutes"
        )
