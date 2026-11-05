"""Recovery refusals, with `az` and `gh` stubbed. The stakes: marking a live outbox as superseded,
or running reconciliation against the wrong database, cannot be undone. Needs bash."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "infrastructure" / "scripts" / "recovery.sh"
BASH = shutil.which("bash")
RESTORED = "psql-restored"
HOLD_CRON = "0 0 1 1 *"

STUB = r"""#!/bin/sh
# Answers from the state file, by the words of the command line.
state="$STUB_STATE"
read_state() { sed -n "s/^$1=//p" "$state"; }
case "$*" in
  *"variable list"*) read_state variables ;;
  *"job execution list"*"-n caj-notify"*) read_state notify_running ;;
  *"job execution list"*"-n caj-cleanup"*) read_state cleanup_running ;;
  *"job show"*"-n caj-migrate"*"DATABASE_URL"*) read_state database_url ;;
  *"job show"*"-n caj-notify"*"NOTIFICATIONS_MODE"*) read_state notify_mode ;;
  *"job show"*"-n caj-notify"*"cronExpression"*) read_state notify_cron ;;
  *"job show"*"-n caj-cleanup"*"cronExpression"*) read_state cleanup_cron ;;
  *"flexible-server show"*) read_state geo ;;
  *) echo "stub: unexpected: $*" >&2; exit 9 ;;
esac
"""


@unittest.skipUnless(BASH, "bash not installed")
class RecoveryGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        for name in ("az", "gh"):
            stub = self.dir / name
            stub.write_text(STUB, encoding="utf-8", newline="\n")
            stub.chmod(0o755)
        self.state = {
            "RECOVERY_HOLD": "true",
            "POSTGRES_SERVER_NAME_OVERRIDE": RESTORED,
            "notify_job": "caj-notify",
            "database_url": f"postgres://id-medsyn-prd@{RESTORED}.postgres.database.azure.com:5432/medical",
            "notify_mode": "off",
            "notify_cron": HOLD_CRON,
            "cleanup_cron": HOLD_CRON,
            "notify_running": "",
            "cleanup_running": "",
            "geo": "Enabled",
        }

    def run_step(self, *args: str) -> subprocess.CompletedProcess:
        variables = {
            "RECOVERY_HOLD": self.state["RECOVERY_HOLD"],
            "POSTGRES_SERVER_NAME_OVERRIDE": self.state["POSTGRES_SERVER_NAME_OVERRIDE"],
            "CONTAINER_APP_NAME": "ca-app",
            "MIGRATE_JOB_NAME": self.state.get("migrate_job", "caj-migrate"),
            "CLEANUP_JOB_NAME": "caj-cleanup",
            "NOTIFY_JOB_NAME": self.state["notify_job"],
            "NOTIFICATIONS_MODE": "off",
        }
        listed = [{"name": name, "value": value} for name, value in variables.items()]
        lines = {**self.state, "variables": json.dumps(listed)}
        (self.dir / "state").write_text(
            "".join(f"{key}={value}\n" for key, value in lines.items()),
            encoding="utf-8",
            newline="\n",
        )
        env = {
            **os.environ,
            "PATH": f"{self.dir}{os.pathsep}{os.environ['PATH']}",
            "STUB_STATE": str(self.dir / "state"),
        }
        return subprocess.run(
            [
                BASH,
                str(SCRIPT),
                "--environment", "prod",
                "--repo", "o/r",
                "--resource-group", "rg",
                *args,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )

    def reconcile(self, *extra: str) -> subprocess.CompletedProcess:
        return self.run_step(
            "reconcile", "--restored-name", RESTORED, "--restore-time", "2026-11-05T08:00:00Z", *extra
        )

    def assert_refused(self, result, text):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(text, result.stdout + result.stderr)

    def test_with_everything_paused_and_selected_it_proceeds(self):
        result = self.reconcile()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("reconcile_documents", result.stdout)
        self.assertIn("reconcile_notifications", result.stdout)
        commands = [line for line in result.stdout.splitlines() if "would run:" in line]
        self.assertEqual(len(commands), 2)
        self.assertFalse([command for command in commands if "--apply" in command])

    def test_the_restored_name_is_required(self):
        result = self.run_step("reconcile", "--restore-time", "2026-11-05T08:00:00Z")
        self.assert_refused(result, "--restored-name")

    def test_a_job_still_on_the_original_server_is_refused(self):
        # select-db only queues a deployment: it may still be waiting for approval, or have failed.
        self.state["database_url"] = "postgres://id@psql-original.postgres.database.azure.com:5432/medical"
        self.assert_refused(self.reconcile("--apply"), "psql-original")

    def test_a_server_whose_name_only_starts_alike_is_refused(self):
        self.state["database_url"] = f"postgres://id@{RESTORED}-2.postgres.database.azure.com:5432/medical"
        self.assert_refused(self.reconcile(), "Refused")

    def test_an_override_for_another_server_is_refused(self):
        self.state["POSTGRES_SERVER_NAME_OVERRIDE"] = "psql-other"
        self.assert_refused(self.reconcile(), "POSTGRES_SERVER_NAME_OVERRIDE")

    def test_no_hold_is_refused(self):
        self.state["RECOVERY_HOLD"] = "false"
        self.assert_refused(self.reconcile(), "hold")

    def test_a_scheduled_notify_job_is_refused(self):
        self.state["notify_cron"] = "*/5 * * * *"
        self.assert_refused(self.reconcile(), "notify")

    def test_a_sending_mode_is_refused(self):
        self.state["notify_mode"] = "live"
        self.assert_refused(self.reconcile(), "notify")

    def test_a_scheduled_cleanup_is_refused(self):
        self.state["cleanup_cron"] = "30 1 * * *"
        self.assert_refused(self.reconcile(), "cleanup")

    def test_an_execution_still_running_is_refused(self):
        for key, job in (("notify_running", "caj-notify"), ("cleanup_running", "caj-cleanup")):
            self.state[key] = "execution-1"
            self.assert_refused(self.reconcile(), job)
            self.state[key] = ""

    def test_no_notify_job_means_nothing_can_send(self):
        self.state["notify_job"] = ""
        self.assertEqual(self.reconcile().returncode, 0)

    def test_migrate_on_the_restored_server_has_the_same_guards(self):
        self.assertEqual(self.run_step("migrate", "--restored-name", RESTORED).returncode, 0)
        self.state["database_url"] = "postgres://id@psql-original.postgres.database.azure.com:5432/m"
        self.assert_refused(self.run_step("migrate", "--restored-name", RESTORED), "psql-original")

    def test_a_restore_keeps_the_source_servers_geo_redundancy(self):
        # The CLI defaults to Disabled, and Bicep declares Enabled; it cannot change after creation.
        result = self.run_step(
            "restore-db", "--restored-name", RESTORED, "--restore-time", "2026-11-05T08:00:00Z"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--geo-redundant-backup Enabled", result.stdout)

    def test_missing_job_names_stop_it_rather_than_acting_on_nothing(self):
        self.state["migrate_job"] = ""
        self.assert_refused(self.reconcile(), "no name for the migrate")


if __name__ == "__main__":
    unittest.main()
