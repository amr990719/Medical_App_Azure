"""`alert_test` proves that an alert reaches a person, without any fault and without any data."""

import logging
from unittest import mock

from django.core.management import call_command

import manage


def test_it_writes_the_one_trace_the_alert_rule_looks_for(caplog):
    with caplog.at_level(logging.INFO, logger="apps.reference"):
        call_command("alert_test")
    assert [record.getMessage() for record in caplog.records] == ["ops_alert_test"]


def test_it_flushes_telemetry_before_the_container_exits():
    with mock.patch(
        "apps.reference.management.commands.alert_test.flush_telemetry"
    ) as flush_telemetry:
        call_command("alert_test")
    flush_telemetry.assert_called_once_with()


def test_it_starts_telemetry_like_the_scheduled_jobs():
    assert manage._starts_telemetry(["manage.py", "alert_test"])
