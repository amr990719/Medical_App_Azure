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


# --- Email-first operation: each secret group appears only when its feature is on -------------


def _module() -> str:
    return MODULE.read_text(encoding="utf-8")


def test_whatsapp_references_exist_only_with_enable_whatsapp():
    source = _module()
    assert "var whatsAppSecrets = enableNotifications && enableWhatsApp" in source
    assert "var whatsAppEnv = enableNotifications && enableWhatsApp" in source
    assert "enableWhatsApp bool = false" in MAIN.read_text(encoding="utf-8")


def test_the_allowlist_reference_exists_only_in_allowlist_mode():
    source = _module()
    assert (
        "var allowlistSecrets = enableNotifications && notificationsMode == 'allowlist'" in source
    )
    assert "var allowlistEnv = enableNotifications && notificationsMode == 'allowlist'" in source


def test_the_aws_keys_are_opt_in_and_reach_only_the_app_and_the_notify_job():
    source = _module()
    assert "var awsKeyEnv = enableNotifications && sesAccessKeyFromKeyVault" in source
    for container in ("migrate", "cleanup"):
        env = _container_env(source, container)
        assert "AWS_" not in env and "awsKey" not in env
    assert "sesAccessKeyFromKeyVault bool = false" in MAIN.read_text(encoding="utf-8")


def test_whatsapp_plain_settings_and_the_switch_are_gated():
    main = MAIN.read_text(encoding="utf-8")
    block = main[main.index("var whatsAppSettings") : main.index("var notificationSettings")]
    assert "enableWhatsApp" in block and "WHATSAPP_ENABLED: 'true'" in block
    assert block.count("WHATSAPP_") == 4  # the switch plus three plain settings, all gated
