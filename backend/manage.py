#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def _starts_telemetry(argv: list[str]) -> bool:
    """True for the commands that run as a scheduled job and must reach Application Insights."""
    return len(argv) > 1 and argv[1] == "send_notifications"


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    if _starts_telemetry(sys.argv):
        # Before Django builds LOGGING: `TelemetryLogHandler` binds its logger provider at that
        # moment, so calling this inside the command would be too late. No-op without
        # APPLICATIONINSIGHTS_CONNECTION_STRING.
        from config.telemetry import configure_telemetry

        configure_telemetry()
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
