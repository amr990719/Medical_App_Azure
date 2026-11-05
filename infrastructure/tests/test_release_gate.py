"""The release gate decides what may reach production, so its refusals are tested on a real
throwaway Git repository and a fake GitHub API.

    python -m unittest discover -s infrastructure/tests -v
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infrastructure" / "scripts"))

import release_gate as gate  # noqa: E402


class FakeGitHub:
    """Answers the two endpoints the gate reads, from {(workflow, sha): (conclusion, jobs)}."""

    def __init__(self, runs: dict | None = None):
        self.runs = runs or {}
        self.requests: list[str] = []

    def get(self, path: str) -> dict:
        self.requests.append(path)
        if "/jobs" in path:
            run_id = int(path.split("/runs/")[1].split("/")[0])
            for number, (_, (_, jobs)) in enumerate(self.runs.items(), start=1):
                if number == run_id:
                    return {"jobs": [{"name": n, "conclusion": c} for n, c in jobs]}
            return {"jobs": []}
        workflow = path.split("/workflows/")[1].split("/")[0]
        sha = path.split("head_sha=")[1].split("&")[0]
        found = []
        for number, ((name, run_sha), (conclusion, _)) in enumerate(self.runs.items(), start=1):
            if name == workflow and run_sha == sha:
                found.append(
                    {
                        "id": number,
                        "status": "completed" if conclusion else "in_progress",
                        "conclusion": conclusion,
                        "html_url": f"https://example.test/run/{number}",
                    }
                )
        return {"workflow_runs": found}


class Repository(unittest.TestCase):
    """A main branch with merge commits, as the real repository has."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.test")
        self.git("config", "user.name", "test")
        self.git("config", "commit.gpgsign", "false")
        self.base = self.commit("backend/a.py", "frontend/a.ts", "infrastructure/a.bicep", "README.md")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.path, capture_output=True, text=True, check=True
        ).stdout.strip()

    def commit(self, *files: str) -> str:
        for name in files:
            target = self.path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.git("rev-list", "--all", "--count") + name, encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "change")
        return self.git("rev-parse", "HEAD")

    def merge(self, *files: str) -> str:
        self.git("checkout", "-q", "-b", "topic")
        self.commit(*files)
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--no-ff", "-m", "merge", "topic")
        self.git("branch", "-q", "-D", "topic")
        return self.git("rev-parse", "HEAD")

    def clean(self, sha: str, *names: str) -> dict:
        """Every evidence run for `sha` succeeded, each with its dev deploy job where it has one."""
        jobs = {
            "backend.yml": [("deploy-dev / deploy to dev", "success")],
            "frontend.yml": [("deploy-dev / deploy to dev", "success")],
            "infrastructure.yml": [("deploy-dev / deploy dev", "success")],
            "e2e.yml": [("playwright", "success")],
        }
        return {(name, sha): ("success", jobs[name]) for name in (names or jobs)}


class ComponentResolution(Repository):
    def test_each_component_resolves_to_the_last_merge_that_changed_it(self):
        backend = self.merge("backend/b.py")
        frontend = self.merge("frontend/b.ts")
        docs = self.merge("docs/notes.md")
        resolved = gate.resolve_commits(docs, cwd=self.path)
        self.assertEqual(resolved["backend"], backend)
        self.assertEqual(resolved["frontend"], frontend)
        self.assertEqual(resolved["e2e"], frontend)
        self.assertEqual(resolved["infrastructure"], self.base)

    def test_a_workflow_file_counts_as_part_of_its_component(self):
        changed = self.merge(".github/workflows/reusable-deploy-backend.yml")
        self.assertEqual(gate.resolve_commits(changed, cwd=self.path)["backend"], changed)

    def test_e2e_follows_both_application_parts_and_compose(self):
        backend = self.merge("backend/c.py")
        self.assertEqual(gate.resolve_commits(backend, cwd=self.path)["e2e"], backend)
        compose = self.merge("docker-compose.yml")
        self.assertEqual(gate.resolve_commits(compose, cwd=self.path)["e2e"], compose)


class CandidateChecks(Repository):
    def test_a_malformed_sha_is_refused(self):
        for value in ("main", "abc123", "A" * 40, "$(whoami)" + "a" * 31, ""):
            with self.assertRaises(gate.GateError):
                gate.require_main_commit(value, main_ref="main", cwd=self.path)

    def test_a_commit_only_on_a_branch_is_refused(self):
        self.git("checkout", "-q", "-b", "untrusted")
        branch_only = self.commit("backend/evil.py")
        self.git("checkout", "-q", "main")
        with self.assertRaisesRegex(gate.GateError, "not on main"):
            gate.require_main_commit(branch_only, main_ref="main", cwd=self.path)

    def test_a_main_commit_passes(self):
        sha = self.merge("backend/ok.py")
        self.assertEqual(gate.require_main_commit(sha, main_ref="main", cwd=self.path), sha)


class EvidenceChecks(Repository):
    def evidence(self, sha: str, runs: dict) -> dict:
        return gate.collect_evidence(sha, FakeGitHub(runs), repo="o/r", cwd=self.path)

    def test_all_green_returns_the_artifact_commits_and_run_links(self):
        sha = self.merge("backend/x.py", "frontend/x.ts", "infrastructure/x.bicep")
        evidence = self.evidence(sha, self.clean(sha))
        self.assertEqual(evidence["backend"]["commit"], sha)
        self.assertTrue(evidence["e2e"]["run_url"].startswith("https://"))

    def test_a_docs_only_commit_uses_the_evidence_of_the_commits_it_contains(self):
        code = self.merge("backend/x.py", "frontend/x.ts", "infrastructure/x.bicep")
        docs = self.merge("docs/only.md")
        evidence = self.evidence(docs, self.clean(code))
        self.assertEqual(evidence["backend"]["commit"], code)

    def test_a_missing_e2e_run_blocks_an_application_release(self):
        sha = self.merge("backend/x.py", "frontend/x.ts", "infrastructure/x.bicep")
        runs = self.clean(sha, "backend.yml", "frontend.yml", "infrastructure.yml")
        with self.assertRaisesRegex(gate.GateError, "e2e"):
            self.evidence(sha, runs)

    def test_a_failed_or_unfinished_run_blocks(self):
        sha = self.merge("backend/x.py", "frontend/x.ts", "infrastructure/x.bicep")
        for conclusion in ("failure", "cancelled", None):
            runs = self.clean(sha)
            runs[("backend.yml", sha)] = (conclusion, [("deploy-dev / deploy to dev", "success")])
            with self.assertRaisesRegex(gate.GateError, "backend"):
                self.evidence(sha, runs)

    def test_a_green_run_whose_dev_deploy_was_skipped_blocks(self):
        sha = self.merge("backend/x.py", "frontend/x.ts", "infrastructure/x.bicep")
        runs = self.clean(sha)
        runs[("frontend.yml", sha)] = ("success", [("deploy-dev / deploy to dev", "skipped")])
        with self.assertRaisesRegex(gate.GateError, "dev deployment"):
            self.evidence(sha, runs)

    def test_a_later_success_outweighs_an_earlier_failure(self):
        sha = self.merge("backend/x.py", "frontend/x.ts", "infrastructure/x.bicep")
        github = FakeGitHub(self.clean(sha))
        original = github.get

        def with_failed_first_attempt(path):
            response = original(path)
            if "workflows/backend.yml" in path:
                response["workflow_runs"] = [
                    {"id": 99, "status": "completed", "conclusion": "failure", "html_url": "x"},
                    *response["workflow_runs"],
                ]
            return response

        github.get = with_failed_first_attempt
        evidence = gate.collect_evidence(sha, github, repo="o/r", cwd=self.path)
        self.assertEqual(evidence["backend"]["commit"], sha)


class MonotonicChecks(Repository):
    def setUp(self):
        super().setUp()
        self.old = self.merge("backend/1.py")
        self.new = self.merge("backend/2.py")

    def check(self, candidate, current, mode):
        gate.check_release_order(candidate=candidate, current=current, mode=mode, cwd=self.path)

    def test_a_newer_commit_may_be_released(self):
        self.check(self.new, self.old, "release")

    def test_rerunning_the_same_release_is_allowed(self):
        self.check(self.new, self.new, "release")

    def test_an_older_queued_release_cannot_replace_a_newer_one(self):
        with self.assertRaisesRegex(gate.GateError, "older"):
            self.check(self.old, self.new, "release")

    def test_a_diverged_commit_is_refused(self):
        self.git("checkout", "-q", "-b", "side", self.old)
        side = self.commit("backend/side.py")
        self.git("checkout", "-q", "main")
        with self.assertRaisesRegex(gate.GateError, "not a descendant"):
            self.check(side, self.new, "release")

    def test_a_release_needs_an_existing_production(self):
        with self.assertRaisesRegex(gate.GateError, "bootstrap"):
            self.check(self.new, "", "release")

    def test_bootstrap_only_runs_before_the_first_release(self):
        self.check(self.new, "", "bootstrap")
        with self.assertRaisesRegex(gate.GateError, "already"):
            self.check(self.new, self.old, "bootstrap")

    def test_a_failed_release_can_go_back_to_the_release_still_on_record(self):
        # The record is written last, so a release that failed part way leaves it on the old one.
        self.check(self.new, self.new, "rollback")

    def test_rollback_must_go_backwards(self):
        self.check(self.old, self.new, "rollback")
        with self.assertRaisesRegex(gate.GateError, "older"):
            self.check(self.new, self.old, "rollback")
        with self.assertRaisesRegex(gate.GateError, "nothing to roll back"):
            self.check(self.old, "", "rollback")


class MigrationReport(Repository):
    def test_it_lists_new_migrations_and_flags_contract_operations(self):
        start = self.merge("backend/start.py")
        expand = self.path / "backend/apps/x/migrations/0002_add.py"
        expand.parent.mkdir(parents=True)
        expand.write_text("migrations.AddField(model_name='x', name='y')\n", encoding="utf-8")
        contract = self.path / "backend/apps/x/migrations/0003_drop.py"
        contract.write_text("migrations.RemoveField(model_name='x', name='z')\n", encoding="utf-8")
        end = self.merge("backend/end.py")
        report = gate.migration_report(start, end, cwd=self.path)
        self.assertEqual(
            report["added"],
            ["backend/apps/x/migrations/0002_add.py", "backend/apps/x/migrations/0003_drop.py"],
        )
        self.assertEqual(report["needs_review"], ["backend/apps/x/migrations/0003_drop.py"])

    def test_a_first_release_has_nothing_to_compare_with(self):
        end = self.merge("backend/end.py")
        self.assertEqual(gate.migration_report("", end, cwd=self.path)["added"], [])


class PullRequestGate(Repository):
    def setUp(self):
        super().setUp()
        self.head = self.merge("docs/start.md")

    def required(self, *files):
        base = self.git("rev-parse", "HEAD")
        head = self.merge(*files)
        return gate.required_workflows(base, head, cwd=self.path), head

    def test_a_docs_change_needs_nothing(self):
        required, _ = self.required("docs/x.md")
        self.assertEqual(required, [])

    def test_a_backend_change_needs_backend_and_e2e(self):
        required, _ = self.required("backend/x.py")
        self.assertEqual(sorted(required), ["backend.yml", "e2e.yml"])

    def test_an_infrastructure_change_needs_infrastructure_only(self):
        required, _ = self.required("infrastructure/x.bicep")
        self.assertEqual(required, ["infrastructure.yml"])

    def test_the_gate_passes_only_when_every_required_run_succeeded(self):
        required, head = self.required("frontend/x.ts")
        runs = {("frontend.yml", head): ("success", []), ("e2e.yml", head): ("success", [])}
        state = gate.pull_request_state(head, required, FakeGitHub(runs), repo="o/r")
        self.assertEqual(state, ("passed", []))

    def test_the_gate_waits_for_a_missing_or_running_workflow(self):
        required, head = self.required("frontend/x.ts")
        runs = {("frontend.yml", head): (None, [])}
        status, pending = gate.pull_request_state(head, required, FakeGitHub(runs), repo="o/r")
        self.assertEqual(status, "waiting")
        self.assertEqual(sorted(pending), ["e2e.yml", "frontend.yml"])

    def test_the_gate_fails_at_once_on_a_failed_run(self):
        required, head = self.required("frontend/x.ts")
        runs = {("frontend.yml", head): ("failure", []), ("e2e.yml", head): (None, [])}
        status, failed = gate.pull_request_state(head, required, FakeGitHub(runs), repo="o/r")
        self.assertEqual((status, failed), ("failed", ["frontend.yml"]))


class Manifest(unittest.TestCase):
    def test_it_records_the_identity_of_a_release_and_nothing_secret(self):
        evidence = {
            name: {"commit": "c" * 40, "run_url": "https://example.test/run"}
            for name in gate.COMPONENTS
        }
        manifest = gate.build_manifest(
            mode="release",
            source_sha="a" * 40,
            backend_digest="sha256:" + "b" * 64,
            frontend_digest="sha256:" + "d" * 64,
            frontend_content_sha256="e" * 64,
            previous_sha="f" * 40,
            dev_acceptance="docs/progress.md#2026-11-05",
            evidence=evidence,
            run_url="https://example.test/release",
            actor="someone",
            created_at="2026-11-05T00:00:00Z",
        )
        self.assertEqual(manifest["source_sha"], "a" * 40)
        self.assertEqual(manifest["backend"]["digest"], "sha256:" + "b" * 64)
        self.assertEqual(manifest["backend"]["build_sha"], "c" * 40)
        self.assertEqual(manifest["frontend"]["content_sha256"], "e" * 64)
        self.assertEqual(manifest["previous_sha"], "f" * 40)
        rendered = json.dumps(manifest).lower()
        for word in ("password", "token", "email", "subscription", "tenant"):
            self.assertNotIn(word, rendered)

    def test_a_digest_that_is_not_a_digest_is_refused(self):
        with self.assertRaises(gate.GateError):
            gate.build_manifest(
                mode="release",
                source_sha="a" * 40,
                backend_digest="latest",
                frontend_digest="sha256:" + "d" * 64,
                frontend_content_sha256="e" * 64,
                previous_sha="",
                dev_acceptance="record",
                evidence={},
                run_url="u",
                actor="a",
                created_at="t",
            )


class WorkflowDrift(unittest.TestCase):
    """The gate's path map must say exactly what the workflows' own filters say."""

    def test_the_path_map_matches_the_workflow_filters(self):
        self.assertEqual(gate.path_filter_drift(ROOT), [])


if __name__ == "__main__":
    unittest.main()
