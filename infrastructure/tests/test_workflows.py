"""Promises the workflows make, checked on their text (the runner has no YAML library, and
actionlint covers the syntax). Each test is something that once went wrong or would be costly to
get wrong: docs/production-readiness-2026-11-05.md."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
SCRIPTS = ROOT / "infrastructure" / "scripts"
PARAMETERS = ROOT / "infrastructure" / "parameters"


def read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def job(text: str, name: str) -> str:
    """The body of one top-level job."""
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [\w-]+:\n|\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, f"job {name} not found"
    return match.group(1)


class NoStaging(unittest.TestCase):
    def test_no_active_workflow_mentions_staging_as_a_deployment_path(self):
        for path in WORKFLOWS.glob("*.yml"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("DEPLOY_STAGING", text, path.name)
            self.assertNotIn("deploy-staging", text, path.name)
            self.assertNotRegex(text, r"(?i)\bstaging\b", path.name)

    def test_a_merge_cannot_deploy_prod(self):
        for name in ("backend.yml", "frontend.yml", "infrastructure.yml"):
            text = read(name)
            self.assertNotIn("deploy-prod", text, name)
            self.assertNotIn("environment: prod", text, name)


class ReleaseWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read("release-production.yml")

    def test_it_runs_only_when_a_person_starts_it(self):
        triggers = self.text[self.text.index("\non:") : self.text.index("\npermissions:")]
        self.assertIn("workflow_dispatch:", triggers)
        for other in ("push:", "pull_request", "schedule:", "workflow_run", "repository_dispatch"):
            self.assertNotIn(other, triggers)

    def test_it_refuses_any_ref_but_main(self):
        self.assertIn('[ "$GITHUB_REF" != "refs/heads/main" ]', job(self.text, "verify"))

    def test_the_order_is_verify_export_preview_deploy(self):
        self.assertIn("needs: verify", job(self.text, "export"))
        self.assertIn("needs: [verify, export]", job(self.text, "preview"))
        self.assertIn("needs: [verify, export, preview]", job(self.text, "deploy"))

    def test_the_what_if_is_visible_before_the_approval_that_changes_production(self):
        preview = job(self.text, "preview")
        self.assertIn("what-if", preview)
        self.assertNotIn("deployment group create", preview)
        self.assertRegex(preview, r"environment:\n\s+name: prod")
        self.assertRegex(job(self.text, "deploy"), r"environment:\n\s+name: prod")

    def test_only_verify_and_export_can_run_without_a_reviewer(self):
        self.assertNotIn("id-token", job(self.text, "verify"))
        self.assertRegex(job(self.text, "export"), r"environment:\n\s+name: dev")
        self.assertNotIn("deployment group create", job(self.text, "export"))

    def test_deploy_never_runs_after_a_failed_validation(self):
        deploy = job(self.text, "deploy")
        self.assertNotIn("always()", deploy)
        self.assertIn("needs.verify.result == 'success'", deploy)
        self.assertIn("needs.export.result == 'success' && needs.preview.result == 'success'", deploy)

    def test_the_steps_keep_their_order(self):
        deploy = job(self.text, "deploy")
        steps = [
            "Refuse an older release",
            "Put the artifacts in the production registry",
            "Deploy the infrastructure, keeping the running image",
            "Run the migration job once",
            "Check what SELECT 1 cannot",
            "Point the jobs at the new image",
            "Create the new revision",
            "Upload to Static Web Apps",
            "Smoke test through the public host",
            "Record the release",
        ]
        positions = [deploy.index(step) for step in steps]
        self.assertEqual(positions, sorted(positions))

    def test_bootstrap_migrates_before_the_web_app_can_exist(self):
        deploy = job(self.text, "deploy")
        jobs_only = deploy.index("DEPLOY_WEB_APP=false")
        migrate = deploy.index("run-migrations", jobs_only)
        full = deploy.index("Deploy the infrastructure, keeping the running image")
        self.assertLess(jobs_only, migrate)
        self.assertLess(migrate, full)

    def test_a_deployment_holds_the_lock_shared_with_infrastructure(self):
        self.assertIn("group: deploy-azure-app-prod", job(self.text, "deploy"))
        self.assertIn("group: deploy-azure-app-${{ inputs.environment }}", read("reusable-infrastructure.yml"))

    def test_only_a_rollback_may_run_during_a_recovery_hold(self):
        self.assertIn('[ "$RECOVERY_HOLD" = "true" ] && [ "$MODE" != "rollback" ]', job(self.text, "deploy"))

    def test_a_smoke_test_is_not_expected_to_pass_through_a_closed_ingress(self):
        deploy = job(self.text, "deploy")
        smoke = deploy[deploy.index("Smoke test through the public host") :][:80]
        self.assertIn("if: vars.RECOVERY_HOLD != 'true'", smoke)

    def test_a_rollback_is_not_blocked_by_a_template_it_never_deploys(self):
        verify = job(self.text, "verify")
        build = verify[verify.index("Build the selected commit's template") :][:120]
        self.assertIn("if: inputs.mode != 'rollback'", build)

    def test_a_failed_preview_still_shows_the_reader_its_error(self):
        preview = job(self.text, "preview")
        self.assertIn('> "$report" 2>&1 || status=$?', preview)
        self.assertLess(preview.index('cat "$report"'), preview.index('exit "$status"'))

    def test_the_notify_job_cannot_silently_stay_on_an_old_image(self):
        self.assertIn('[ "$NOTIFICATIONS_ENABLED" = "true" ] && [ -z "$NOTIFY_JOB_NAME" ]', job(self.text, "deploy"))

    def test_a_free_text_record_cannot_be_read_as_a_flag(self):
        self.assertIn('--dev-acceptance="$DEV_ACCEPTANCE"', job(self.text, "deploy"))

    def test_it_requires_a_person_behind_the_alerts(self):
        self.assertIn('[ -z "$ALERT_EMAIL" ]', job(self.text, "deploy"))

    def test_images_run_by_digest(self):
        self.assertIn("medical-backend@${backend}", self.text)
        self.assertNotRegex(self.text, r"IMAGE=.*medical-backend:")

    def test_a_rollback_changes_neither_infrastructure_nor_schema(self):
        deploy = job(self.text, "deploy")
        infra = deploy[deploy.index("Deploy the infrastructure") :][:120]
        self.assertIn("if: inputs.mode != 'rollback'", infra)
        migrate = deploy[deploy.index("Run the migration job once") :][:120]
        self.assertIn("if: inputs.mode == 'release'", migrate)

    def test_user_input_never_reaches_a_shell_by_interpolation(self):
        for match in re.finditer(r"run: \|\n((?:\s{10,}.*\n)+)", self.text):
            self.assertNotIn("${{ inputs.", match.group(1))
        for match in re.finditer(r"run: (.*)\n", self.text):
            self.assertNotIn("${{ inputs.", match.group(1))


class EveryWorkflow(unittest.TestCase):
    def test_every_action_is_pinned_to_a_full_commit(self):
        for path in WORKFLOWS.glob("*.yml"):
            for reference in re.findall(r"uses: ([^\s#]+)", path.read_text(encoding="utf-8")):
                if reference.startswith("./"):
                    continue
                self.assertRegex(reference, r"@[0-9a-f]{40}$", f"{path.name}: {reference}")

    def test_azure_jobs_mask_the_subscription_before_signing_in(self):
        for name in (
            "reusable-deploy-backend.yml",
            "reusable-deploy-frontend.yml",
            "reusable-infrastructure.yml",
            "release-production.yml",
        ):
            text = read(name)
            first_login = text.index("azure/login@")
            first_mask = text.index('::add-mask::${AZURE_SUBSCRIPTION_ID}')
            self.assertLess(first_mask, first_login, name)

    def test_dev_stores_both_artifacts_for_the_release(self):
        self.assertIn("digest-of", read("reusable-deploy-backend.yml"))
        self.assertIn("store-frontend", read("reusable-deploy-frontend.yml"))

    def test_the_gate_does_not_depend_on_another_job(self):
        # A job skipped because its need failed reports success to branch protection.
        self.assertNotIn("needs:", job(read("ci-gate.yml"), "gate"))

    def test_e2e_runs_on_main_and_is_not_cancelled_there(self):
        text = read("e2e.yml")
        self.assertRegex(text, r"push:\n\s+branches: \[main\]")
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", text)


class ProductionConfigurationRuns(unittest.TestCase):
    """A manual infrastructure run on prod, as the hold, select-db and cutover use."""

    def setUp(self):
        self.text = read("reusable-infrastructure.yml")

    def test_it_deploys_the_released_template_not_mains(self):
        self.assertIn('git checkout --quiet --detach "$current"', self.text)
        self.assertIn("fetch-depth: 0", self.text)
        self.assertLess(self.text.index('--detach "$current"'), self.text.index("name: what-if"))

    def test_an_unreadable_app_is_an_error_not_a_first_phase_deployment(self):
        keep = self.text[self.text.index("name: Keep the running image") : self.text.index("name: what-if")]
        self.assertNotIn("|| true", keep)
        self.assertNotIn("2>/dev/null", keep)
        self.assertIn("refusing a first-phase deployment", keep)

    def test_production_outputs_stay_out_of_the_public_summary(self):
        deploy = self.text[self.text.index("name: Deploy") :]
        self.assertLess(deploy.index('"$ENVIRONMENT" = "prod"'), deploy.index("deployment outputs"))


class ParameterVariables(unittest.TestCase):
    """A variable the parameter file reads must actually reach it, in both deployment paths."""

    # Set by each step, a secret, or only ever set by a person at a terminal.
    NOT_GITHUB_VARIABLES = {
        "CONTAINER_IMAGE",
        "DEPLOY_WEB_APP",
        "ALERT_EMAIL",
        "KEY_VAULT_OPERATOR_OBJECT_ID",
        "KEY_VAULT_OPERATOR_TYPE",
    }

    def test_every_variable_prod_reads_is_exported(self):
        read_names = set(
            re.findall(
                r"readEnvironmentVariable\('([A-Z0-9_]+)'",
                (PARAMETERS / "prod.bicepparam").read_text(encoding="utf-8"),
            )
        )
        exported = set(
            re.findall(
                r'"([A-Z0-9_]+)"',
                re.search(r"PARAM_VARS='(.*)'", (SCRIPTS / "release-steps.sh").read_text("utf-8")).group(1),
            )
        )
        self.assertEqual(read_names - self.NOT_GITHUB_VARIABLES - exported, set())

    def test_both_paths_export_the_same_list(self):
        script = re.search(r"PARAM_VARS='(.*)'", (SCRIPTS / "release-steps.sh").read_text("utf-8")).group(1)
        reusable = re.search(r"keys='(.*)'", read("reusable-infrastructure.yml")).group(1)
        self.assertEqual(sorted(re.findall(r'"(\w+)"', script)), sorted(re.findall(r'"(\w+)"', reusable)))


if __name__ == "__main__":
    unittest.main()
