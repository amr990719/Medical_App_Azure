import sys

import pytest

import manage


@pytest.fixture
def calls(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        "config.telemetry.configure_telemetry", lambda: recorded.append("telemetry")
    )
    monkeypatch.setattr(
        "django.core.management.execute_from_command_line", lambda argv: recorded.append("django")
    )
    return recorded


def test_send_notifications_starts_telemetry_before_django(monkeypatch, calls):
    monkeypatch.setattr(sys, "argv", ["manage.py", "send_notifications"])
    manage.main()
    assert calls == ["telemetry", "django"]


def test_other_commands_do_not_start_telemetry(monkeypatch, calls):
    monkeypatch.setattr(sys, "argv", ["manage.py", "migrate"])
    manage.main()
    assert calls == ["django"]


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["manage.py", "send_notifications"], True),
        (["manage.py", "send_notifications", "--verbosity", "2"], True),
        (["manage.py"], False),
        ([], False),
        (["manage.py", "runserver"], False),
        (["manage.py", "help", "send_notifications"], False),
    ],
)
def test_starts_telemetry_only_for_the_sender_command(argv, expected):
    assert manage._starts_telemetry(argv) is expected
