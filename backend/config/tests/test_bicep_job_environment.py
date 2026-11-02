"""The migrate and cleanup jobs must never receive the notification settings (infrastructure).

`NOTIFICATIONS_MODE=allowlist` / `NOTIFICATION_PROVIDERS=real` without the notification secrets
makes production settings refuse to import, which would fail every migrate and cleanup run.
"""

import re
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[3] / "infrastructure" / "modules" / "container-app.bicep"
MAIN = MODULE.parent.parent / "main.bicep"

pytestmark = pytest.mark.skipif(not MODULE.exists(), reason="infrastructure/ is not in this image")


def _container_env(source: str, name: str) -> str:
    match = re.search(rf"name: '{name}'\n.*?env: (concat\(.*?\n\s+\]\))", source, re.DOTALL)
    assert match, f"container {name} not found"
    return match.group(1)


@pytest.mark.parametrize("container", ["migrate", "cleanup"])
def test_one_off_jobs_get_no_notification_environment(container):
    env = _container_env(MODULE.read_text(encoding="utf-8"), container)
    assert "notificationPlainEnv" not in env and "notificationSecretEnv" not in env


@pytest.mark.parametrize("container", ["django", "notify"])
def test_the_app_and_the_notify_job_get_the_notification_environment(container):
    env = _container_env(MODULE.read_text(encoding="utf-8"), container)
    assert "notificationPlainEnv" in env and "notificationSecretEnv" in env


def test_the_notification_settings_are_not_in_the_shared_settings():
    main = MAIN.read_text(encoding="utf-8")
    assert "settings: union(baseSettings, telemetrySettings, ocrSettings)" in main
    assert "notificationEnv: notificationSettings" in main
