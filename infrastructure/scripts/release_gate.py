#!/usr/bin/env python3
"""What may reach production, and what a pull request must pass (docs/production-runbook.md).

    release_gate.py verify      --sha <sha> --mode release|bootstrap|rollback   (release evidence)
    release_gate.py order       --sha <sha> --current <sha> --mode <mode>       (no older release)
    release_gate.py migrations  --current <sha> --sha <sha>                     (what the schema does)
    release_gate.py manifest    ...                                             (release record)
    release_gate.py pr-gate     --base <sha> --head <sha>                       (pull request gate)
    release_gate.py check-paths                                                 (path map vs workflows)

The backend, frontend, infrastructure and e2e workflows are path filtered, so a selected commit
often has no run of its own. Each component's evidence therefore comes from the last commit on
main, at or before the selected one, that changed that component: its artifact and its checks are
what the selected commit contains. Standard library only; run from a full-depth checkout.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")

# Component -> its workflow, the paths that trigger it, and the job proving the dev deployment.
# `check-paths` compares this with the workflows' own filters.
COMPONENTS: dict[str, dict] = {
    "backend": {
        "workflow": "backend.yml",
        "paths": [
            "backend/**",
            ".github/workflows/backend.yml",
            ".github/workflows/reusable-deploy-backend.yml",
        ],
        "deploy_job": "deploy to dev",
    },
    "frontend": {
        "workflow": "frontend.yml",
        "paths": [
            "frontend/**",
            ".github/workflows/frontend.yml",
            ".github/workflows/reusable-deploy-frontend.yml",
        ],
        "deploy_job": "deploy to dev",
    },
    "infrastructure": {
        "workflow": "infrastructure.yml",
        "paths": [
            "infrastructure/**",
            ".github/workflows/infrastructure.yml",
            ".github/workflows/reusable-infrastructure.yml",
        ],
        "deploy_job": "deploy dev",
    },
    "e2e": {
        "workflow": "e2e.yml",
        "paths": [
            "frontend/**",
            "backend/**",
            "docker-compose.yml",
            ".github/workflows/e2e.yml",
        ],
        "deploy_job": None,
    },
}

# Operations that an image still running the previous code may not survive: review them by hand.
CONTRACT_OPERATIONS = re.compile(
    r"\b(RemoveField|DeleteModel|RenameField|RenameModel|AlterField|RemoveConstraint|RunSQL)\b"
)


class GateError(Exception):
    """A release or pull request is refused. The message is safe to print."""


def git(*args: str, cwd: Path | str | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout.strip()


def is_ancestor(older: str, newer: str, cwd: Path | str | None = None) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer], cwd=cwd, capture_output=True, check=False
    )
    return completed.returncode == 0


def _pathspecs(paths: Sequence[str]) -> list[str]:
    return [path.removesuffix("/**") for path in paths]


class GitHub:
    def __init__(self, token: str, api: str = "https://api.github.com"):
        self.token = token
        self.api = api

    def get(self, path: str) -> dict:
        request = urllib.request.Request(
            f"{self.api}{path}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https host
            return json.load(response)


# --- Candidate ---------------------------------------------------------------------------------


def require_main_commit(sha: str, *, main_ref: str, cwd: Path | str | None = None) -> str:
    if not SHA.fullmatch(sha or ""):
        raise GateError("The release must name a full 40-character lowercase commit SHA.")
    if not is_ancestor(sha, main_ref, cwd=cwd):
        raise GateError(f"{sha} is not on main: only a commit from the protected branch can release.")
    return sha


def resolve_commits(sha: str, *, cwd: Path | str | None = None) -> dict[str, str]:
    """The last commit on the first-parent history at or before `sha` that changed each component."""
    resolved = {}
    for name, component in COMPONENTS.items():
        commit = git(
            "log", "-1", "--first-parent", "--format=%H", sha, "--", *_pathspecs(component["paths"]),
            cwd=cwd,
        )
        if not commit:
            raise GateError(f"No commit at or before {sha} changed {name}.")
        resolved[name] = commit
    return resolved


# --- Evidence ----------------------------------------------------------------------------------


def _runs(github, repo: str, workflow: str, sha: str, event: str) -> list[dict]:
    response = github.get(
        f"/repos/{repo}/actions/workflows/{workflow}/runs?head_sha={sha}&event={event}&per_page=30"
    )
    return response.get("workflow_runs", [])


def _evidence_for(name: str, commit: str, github, repo: str) -> dict:
    component = COMPONENTS[name]
    workflow = component["workflow"]
    runs = _runs(github, repo, workflow, commit, "push")
    if not runs:
        raise GateError(
            f"{name}: no {workflow} run on main for {commit}. Commits merged before push-triggered "
            "e2e existed cannot release; merge a new commit that changes this component."
        )
    successes = [run for run in runs if run.get("conclusion") == "success"]
    if not successes:
        state = runs[0].get("conclusion") or runs[0].get("status")
        raise GateError(f"{name}: {workflow} for {commit} is '{state}', not success.")
    if component["deploy_job"] is None:
        return {"commit": commit, "run_url": successes[0].get("html_url", "")}
    for run in successes:
        jobs = github.get(f"/repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100").get("jobs", [])
        if any(
            component["deploy_job"] in job.get("name", "") and job.get("conclusion") == "success"
            for job in jobs
        ):
            return {"commit": commit, "run_url": run.get("html_url", "")}
    raise GateError(f"{name}: {workflow} for {commit} passed without a dev deployment.")


def collect_evidence(sha: str, github, *, repo: str, cwd: Path | str | None = None) -> dict:
    return {
        name: _evidence_for(name, commit, github, repo)
        for name, commit in resolve_commits(sha, cwd=cwd).items()
    }


# --- Order -------------------------------------------------------------------------------------


def check_release_order(
    *, candidate: str, current: str, mode: str, cwd: Path | str | None = None
) -> None:
    """Runs with the deployment lock held, so an older queued release cannot win a race."""
    if mode == "bootstrap":
        if current:
            raise GateError(f"Production has already released {current}: use mode 'release'.")
        return
    if not current:
        if mode == "rollback":
            raise GateError("Production has no release yet: nothing to roll back to.")
        raise GateError("Production has no release yet: run mode 'bootstrap' first.")
    if mode == "rollback":
        # The current record is allowed too. The record is the last step of a release, so after one
        # that failed part way it still names what last worked, and re-promoting that is the rollback.
        if candidate != current and not is_ancestor(candidate, current, cwd=cwd):
            raise GateError(f"A rollback must name {current} or a release older than it.")
        return
    if mode != "release":
        raise GateError(f"Unknown mode '{mode}'.")
    if candidate == current:
        return  # re-running the same release is safe: every step converges
    if is_ancestor(candidate, current, cwd=cwd):
        raise GateError(
            f"{candidate} is older than the current release {current}. An older queued release "
            "cannot replace a newer one; use mode 'rollback' if this is deliberate."
        )
    if not is_ancestor(current, candidate, cwd=cwd):
        raise GateError(f"{candidate} is not a descendant of the current release {current}.")


# --- Migrations --------------------------------------------------------------------------------


def migration_report(current: str, candidate: str, *, cwd: Path | str | None = None) -> dict:
    """New migrations since the current release. While they run the old image keeps serving."""
    if not current:
        return {"added": [], "needs_review": []}
    added = git(
        "diff", "--name-only", "--diff-filter=A", current, candidate, "--",
        "backend/apps/*/migrations/*.py",
        cwd=cwd,
    ).splitlines()
    needs_review = [
        path for path in added if CONTRACT_OPERATIONS.search(git("show", f"{candidate}:{path}", cwd=cwd))
    ]
    return {"added": added, "needs_review": needs_review}


# --- Manifest ----------------------------------------------------------------------------------


def build_manifest(
    *,
    mode: str,
    source_sha: str,
    backend_digest: str,
    frontend_digest: str,
    frontend_content_sha256: str,
    previous_sha: str,
    dev_acceptance: str,
    evidence: dict,
    run_url: str,
    actor: str,
    created_at: str,
) -> dict:
    for digest in (backend_digest, frontend_digest):
        if not DIGEST.fullmatch(digest):
            raise GateError("A release manifest needs image digests, never tags.")
    return {
        "schema_version": 1,
        "environment": "prod",
        "mode": mode,
        "source_sha": source_sha,
        "backend": {
            "digest": backend_digest,
            "build_sha": evidence.get("backend", {}).get("commit", ""),
        },
        "frontend": {
            "digest": frontend_digest,
            "build_sha": evidence.get("frontend", {}).get("commit", ""),
            "content_sha256": frontend_content_sha256,
        },
        "previous_sha": previous_sha,
        "dev_acceptance": dev_acceptance,
        "evidence": evidence,
        "run_url": run_url,
        "actor": actor,
        "created_at": created_at,
    }


# --- Pull request gate -------------------------------------------------------------------------


def required_workflows(base: str, head: str, *, cwd: Path | str | None = None) -> list[str]:
    """The path-filtered workflows this change triggers."""
    required = []
    for component in COMPONENTS.values():
        if git("diff", "--name-only", f"{base}...{head}", "--", *_pathspecs(component["paths"]), cwd=cwd):
            required.append(component["workflow"])
    return required


def pull_request_state(head: str, required: Sequence[str], github, *, repo: str) -> tuple[str, list]:
    """("passed", []), ("failed", [workflows]) or ("waiting", [workflows])."""
    failed, waiting = [], []
    for workflow in required:
        runs = _runs(github, repo, workflow, head, "pull_request")
        conclusions = {run.get("conclusion") for run in runs}
        if "success" in conclusions:
            continue
        if conclusions & {"failure", "timed_out", "startup_failure", "action_required"}:
            failed.append(workflow)
        else:
            waiting.append(workflow)
    if failed:
        return "failed", failed
    if waiting:
        return "waiting", waiting
    return "passed", []


def wait_for_pull_request(head: str, required, github, *, repo: str, minutes: int) -> None:
    deadline = time.monotonic() + minutes * 60
    while True:
        status, workflows = pull_request_state(head, required, github, repo=repo)
        if status == "passed":
            print(f"ci gate: passed ({', '.join(required) or 'no path-filtered workflow needed'})")
            return
        if status == "failed":
            raise GateError(f"Required workflow failed: {', '.join(workflows)}")
        if time.monotonic() > deadline:
            raise GateError(f"Timed out after {minutes} minutes waiting for: {', '.join(workflows)}")
        print(f"ci gate: waiting for {', '.join(workflows)}", flush=True)
        time.sleep(30)


# --- Path map against the workflows ------------------------------------------------------------


def _trigger_paths(workflow_text: str) -> dict[str, list[str]]:
    """The `paths:` list under each trigger, read without a YAML library (the runner has none)."""
    found: dict[str, list[str]] = {}
    trigger = None
    in_paths = False
    for line in workflow_text.splitlines():
        match = re.fullmatch(r"  (push|pull_request|workflow_dispatch|schedule):.*", line)
        if match:
            trigger = match.group(1)
            in_paths = False
        elif re.fullmatch(r"\S.*", line) and not line.startswith("on:"):
            trigger = None
            in_paths = False
        elif trigger and re.fullmatch(r"    paths:\s*", line):
            in_paths = True
            found[trigger] = []
        elif in_paths:
            item = re.fullmatch(r"\s+- [\"']?(.+?)[\"']?\s*", line)
            if item:
                found[trigger].append(item.group(1))
            else:
                in_paths = False
    return found


def path_filter_drift(root: Path | str) -> list[str]:
    problems = []
    for name, component in COMPONENTS.items():
        path = Path(root) / ".github" / "workflows" / component["workflow"]
        triggers = _trigger_paths(path.read_text(encoding="utf-8"))
        for trigger in ("push", "pull_request"):
            actual = triggers.get(trigger)
            if actual is None:
                problems.append(f"{name}: {component['workflow']} has no paths under {trigger}")
            elif sorted(actual) != sorted(component["paths"]):
                problems.append(
                    f"{name}: {trigger} paths {sorted(actual)} differ from {sorted(component['paths'])}"
                )
    return problems


# --- Command line ------------------------------------------------------------------------------


def _github() -> GitHub:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise GateError("GITHUB_TOKEN is required.")
    return GitHub(token, os.environ.get("GITHUB_API_URL", "https://api.github.com"))


def _output(values: dict[str, str]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    lines = "".join(f"{key}={value}\n" for key, value in values.items())
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(lines)
    else:
        print(lines, end="")


def _cmd_verify(args) -> int:
    sha = require_main_commit(args.sha, main_ref=args.main_ref)
    resolved = resolve_commits(sha)
    evidence: dict = {name: {"commit": commit, "run_url": ""} for name, commit in resolved.items()}
    if args.mode != "rollback":
        # A rollback re-promotes artifacts that already passed this check when they were released.
        evidence = collect_evidence(sha, _github(), repo=args.repo)
    print(json.dumps(evidence, indent=2))
    if args.evidence_file:
        Path(args.evidence_file).write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    _output(
        {
            "source_sha": sha,
            "backend_build_sha": resolved["backend"],
            "frontend_build_sha": resolved["frontend"],
        }
    )
    return 0


def _cmd_order(args) -> int:
    check_release_order(candidate=args.sha, current=args.current, mode=args.mode)
    print(f"release order: {args.mode} of {args.sha} over '{args.current}' is allowed")
    return 0


def _cmd_migrations(args) -> int:
    report = migration_report(args.current, args.sha)
    print(f"New migrations since the current release: {len(report['added'])}")
    for path in report["added"]:
        flag = "  REVIEW: contract operation" if path in report["needs_review"] else ""
        print(f"- {path}{flag}")
    if report["needs_review"]:
        print(
            "\nThe previous image keeps serving while migrations run, and a rollback reuses this "
            "schema. Confirm the flagged files are expand/contract safe before approving."
        )
    return 0


def _cmd_manifest(args) -> int:
    evidence = json.loads(Path(args.evidence_file).read_text(encoding="utf-8"))
    manifest = build_manifest(
        mode=args.mode,
        source_sha=args.sha,
        backend_digest=args.backend_digest,
        frontend_digest=args.frontend_digest,
        frontend_content_sha256=args.frontend_content_sha256,
        previous_sha=args.previous,
        dev_acceptance=args.dev_acceptance,
        evidence=evidence,
        run_url=args.run_url,
        actor=args.actor,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    Path(args.output).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


def _cmd_pr_gate(args) -> int:
    required = required_workflows(args.base, args.head)
    wait_for_pull_request(args.head, required, _github(), repo=args.repo, minutes=args.minutes)
    return 0


def _cmd_check_paths(args) -> int:
    problems = path_filter_drift(args.root)
    for problem in problems:
        print(f"DRIFT: {problem}")
    print(f"path map: {len(problems)} problem(s)")
    return 1 if problems else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    repo = os.environ.get("GITHUB_REPOSITORY", "")

    verify = commands.add_parser("verify")
    verify.add_argument("--sha", required=True)
    verify.add_argument("--mode", required=True, choices=["release", "bootstrap", "rollback"])
    verify.add_argument("--main-ref", default="origin/main")
    verify.add_argument("--repo", default=repo)
    verify.add_argument("--evidence-file", default="")
    verify.set_defaults(handler=_cmd_verify)

    order = commands.add_parser("order")
    order.add_argument("--sha", required=True)
    order.add_argument("--current", default="")
    order.add_argument("--mode", required=True)
    order.set_defaults(handler=_cmd_order)

    migrations = commands.add_parser("migrations")
    migrations.add_argument("--sha", required=True)
    migrations.add_argument("--current", default="")
    migrations.set_defaults(handler=_cmd_migrations)

    manifest = commands.add_parser("manifest")
    manifest.add_argument("--sha", required=True)
    manifest.add_argument("--mode", required=True)
    manifest.add_argument("--backend-digest", required=True)
    manifest.add_argument("--frontend-digest", required=True)
    manifest.add_argument("--frontend-content-sha256", required=True)
    manifest.add_argument("--previous", default="")
    manifest.add_argument("--dev-acceptance", required=True)
    manifest.add_argument("--evidence-file", required=True)
    manifest.add_argument("--run-url", required=True)
    manifest.add_argument("--actor", required=True)
    manifest.add_argument("--output", required=True)
    manifest.set_defaults(handler=_cmd_manifest)

    pr_gate = commands.add_parser("pr-gate")
    pr_gate.add_argument("--base", required=True)
    pr_gate.add_argument("--head", required=True)
    pr_gate.add_argument("--repo", default=repo)
    pr_gate.add_argument("--minutes", type=int, default=50)
    pr_gate.set_defaults(handler=_cmd_pr_gate)

    check_paths = commands.add_parser("check-paths")
    check_paths.add_argument("--root", default=".")
    check_paths.set_defaults(handler=_cmd_check_paths)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except GateError as error:
        print(f"::error::{error}")
        return 1
    except urllib.error.HTTPError as error:
        print(f"::error::GitHub API answered {error.code}; the check could not complete.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
