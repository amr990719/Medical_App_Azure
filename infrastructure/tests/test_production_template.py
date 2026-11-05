"""What the production parameters and the compiled template must do (needs `az bicep`).

    python -m unittest discover -s infrastructure/tests -v
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infrastructure"
AZ = shutil.which("az") or shutil.which("az.cmd")
sys.path.insert(0, str(INFRA / "scripts"))

# Everything the parameter files read, so a stale environment cannot change a result.
READ_NAMES = sorted(
    {
        name
        for file in (INFRA / "parameters").glob("*.bicepparam")
        for name in re.findall(r"readEnvironmentVariable\('([A-Z0-9_]+)'", file.read_text("utf-8"))
    }
)


def compile_params(environment: str, **env: str) -> dict:
    clean = {k: v for k, v in os.environ.items() if k not in READ_NAMES}
    result = subprocess.run(
        [
            AZ,
            "bicep",
            "build-params",
            "--file",
            str(INFRA / "parameters" / f"{environment}.bicepparam"),
            "--stdout",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**clean, **env},
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    # The CLI may print linter lines first; the document starts at the first brace.
    document = json.loads(result.stdout[result.stdout.index("{") :])
    return {k: v["value"] for k, v in json.loads(document["parametersJson"])["parameters"].items()}


def compile_template() -> dict:
    result = subprocess.run(
        [AZ, "bicep", "build", "--file", str(INFRA / "main.bicep"), "--stdout"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout[result.stdout.index("{") :])


def walk(template: dict):
    items = template.get("resources", [])
    for resource in items.values() if isinstance(items, dict) else items:
        if resource.get("type") == "Microsoft.Resources/deployments":
            yield from walk(resource["properties"]["template"])
        else:
            yield resource


@unittest.skipUnless(AZ, "Azure CLI not installed")
class ProductionParameters(unittest.TestCase):
    def test_a_first_phase_run_deploys_no_application_and_sends_nothing(self):
        params = compile_params("prod")
        self.assertFalse(params["deployApplication"])
        self.assertFalse(params["enableNotifications"])
        self.assertEqual(params["notificationsMode"], "off")
        self.assertEqual(params["alertEmail"], "")
        self.assertFalse(params["recoveryHold"])
        self.assertEqual(params["postgresServerNameOverride"], "")

    def test_the_owner_decisions_are_pinned_not_read_from_the_environment(self):
        params = compile_params(
            "prod", ENABLE_OCR="true", ENABLE_PRIVATE_NETWORKING="true", ENABLE_WHATSAPP="true"
        )
        self.assertFalse(params["enableOcr"])
        self.assertFalse(params["enablePrivateNetworking"])
        self.assertFalse(params["entraAdminRequireMfa"])
        self.assertNotIn("enableWhatsApp", params)  # parked: the default stays off

    def test_the_sizing_baseline_is_kept(self):
        params = compile_params("prod")
        self.assertEqual(params["postgresSkuName"], "Standard_D2ds_v5")
        self.assertEqual(params["postgresHighAvailabilityMode"], "Disabled")
        self.assertEqual(params["postgresBackupRetentionDays"], 35)
        self.assertTrue(params["postgresGeoRedundantBackup"])
        self.assertEqual(params["storageSkuName"], "Standard_ZRS")
        self.assertEqual((params["minReplicas"], params["maxReplicas"]), (1, 5))

    def test_the_notification_settings_follow_the_environment(self):
        params = compile_params(
            "prod",
            ENABLE_NOTIFICATIONS="true",
            NOTIFICATIONS_MODE="allowlist",
            SES_ACCESS_KEY_FROM_KEY_VAULT="true",
            SES_REGION="xx-test-1",
            SES_FROM_ADDRESS="notifications@example.test",
            ALERT_EMAIL="alerts@example.test",
        )
        self.assertTrue(params["enableNotifications"])
        self.assertEqual(params["notificationsMode"], "allowlist")
        self.assertTrue(params["sesAccessKeyFromKeyVault"])
        self.assertEqual(params["sesRegion"], "xx-test-1")
        self.assertEqual(params["sesFromAddress"], "notifications@example.test")
        self.assertEqual(params["alertEmail"], "alerts@example.test")

    def test_the_fiscal_year_is_explicit_in_every_active_environment(self):
        for environment in ("dev", "prod"):
            source = (INFRA / "parameters" / f"{environment}.bicepparam").read_text("utf-8")
            self.assertRegex(source, r"param currentFiscalYear = \d{4}")
            self.assertEqual(compile_params(environment)["currentFiscalYear"], 2026)

    def test_the_bootstrap_phase_creates_the_jobs_without_the_web_app(self):
        params = compile_params(
            "prod", CONTAINER_IMAGE="registry.example/medical-backend@sha256:0", DEPLOY_WEB_APP="false"
        )
        self.assertTrue(params["deployApplication"])
        self.assertFalse(params["deployWebApp"])
        self.assertTrue(compile_params("prod")["deployWebApp"])

    def test_a_restored_server_and_the_recovery_hold_survive_the_next_deployment(self):
        params = compile_params(
            "prod", POSTGRES_SERVER_NAME_OVERRIDE="psql-restored", RECOVERY_HOLD="true"
        )
        self.assertEqual(params["postgresServerNameOverride"], "psql-restored")
        self.assertTrue(params["recoveryHold"])

    def test_service_alerts_are_for_production_only(self):
        self.assertTrue(compile_params("prod")["enableServiceAlerts"])
        self.assertFalse(compile_params("dev").get("enableServiceAlerts", False))


@unittest.skipUnless(AZ, "Azure CLI not installed")
class CompiledTemplate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = compile_template()
        cls.resources = list(walk(cls.template))

    def of_type(self, resource_type: str) -> list[dict]:
        return [r for r in self.resources if r.get("type") == resource_type]

    def test_uptime_results_live_apart_from_the_entra_only_telemetry(self):
        components = self.of_type("Microsoft.Insights/components")
        self.assertEqual(len(components), 2)
        uptime = [c for c in components if c["properties"].get("DisableLocalAuth") is False]
        self.assertEqual(len(uptime), 1, "one literal local-auth component, only for web tests")
        tests = self.of_type("Microsoft.Insights/webtests")
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0]["properties"]["Kind"], "standard")
        self.assertTrue(tests[0]["properties"]["ValidationRules"]["SSLCheck"])

    def test_there_are_alerts_for_availability_database_and_restarts(self):
        # The rule values sit in the module's variables, so search the whole compiled template.
        self.assertTrue(self.of_type("Microsoft.Insights/metricAlerts"))
        rendered = json.dumps(self.template)
        for signal in (
            "WebtestLocationAvailabilityCriteria",
            "cpu_percent",
            "memory_percent",
            "storage_percent",
            "active_connections",
        ):
            self.assertIn(signal, rendered)

    def test_there_are_alerts_for_errors_latency_and_every_scheduled_job(self):
        self.assertTrue(self.of_type("Microsoft.Insights/scheduledQueryRules"))
        rendered = json.dumps(self.template)
        for signal in (
            "resultCode",
            "percentile(duration",
            "ContainerTerminated",
            "cleanup_run",
            "cleanup_run_failed",
        ):
            self.assertIn(signal, rendered)
        self.assertIn("ops_alert_test", rendered)

    def test_restarts_are_not_read_from_a_cumulative_counter(self):
        self.assertNotIn("RestartCount", json.dumps(self.template))

    def test_the_declined_aws_reputation_alarms_are_not_added_back(self):
        rendered = json.dumps(self.template)
        self.assertNotIn("Reputation.BounceRate", rendered)
        self.assertNotIn("Reputation.ComplaintRate", rendered)

    def test_the_fiscal_year_reaches_every_container(self):
        main = (INFRA / "main.bicep").read_text("utf-8")
        block = main[main.index("var baseSettings") : main.index("var telemetrySettings")]
        self.assertIn("CURRENT_FISCAL_YEAR: string(currentFiscalYear)", block)
        self.assertNotIn("defaultValue", self.template["parameters"]["currentFiscalYear"])

    def test_a_hold_closes_ingress_and_stops_both_schedules_and_sending(self):
        main = (INFRA / "main.bicep").read_text("utf-8")
        self.assertIn("recoveryHold ? 'off' : notificationsMode", main)
        self.assertIn("cleanupCron: recoveryHold ? recoveryHoldCron : cleanupCron", main)
        self.assertIn("notifyCron: recoveryHold ? recoveryHoldCron : notifyCron", main)
        self.assertIn("ipSecurityRestrictions: recoveryHold ? recoveryHoldRestrictions : []", main)

    def test_migrate_exists_in_the_jobs_only_phase_and_nothing_else_does(self):
        module = (INFRA / "modules" / "container-app.bicep").read_text("utf-8")
        self.assertRegex(module, r"resource app '[^']+' = if \(deployWebApp\)")
        self.assertRegex(module, r"resource cleanupJob '[^']+' = if \(deployWebApp\)")
        self.assertRegex(module, r"resource notifyJob '[^']+' = if \(enableNotifications && deployWebApp\)")
        self.assertRegex(module, r"resource migrateJob '[^']+' = \{")
        main = (INFRA / "main.bicep").read_text("utf-8")
        self.assertIn("if (deployApplication && deployWebApp)", main)


if __name__ == "__main__":
    unittest.main()
