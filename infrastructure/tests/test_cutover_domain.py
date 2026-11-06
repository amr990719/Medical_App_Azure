"""cutover-domain.sh with az, gh, python and curl stubbed: which paths reach Windows programs, and
which validation token the operator is shown. A binding made with `--no-wait` has no token at
first, and a rebinding issues a new one, so an empty or stale token would leave the domain
unvalidated in the middle of the window. Needs bash."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "infrastructure" / "scripts" / "cutover-domain.sh"
BASH = shutil.which("bash")
DEV_HOST = "dev-site.1.azurestaticapps.net"
PROD_HOST = "prod-site.2.azurestaticapps.net"

# One stub for every program, by the name it is called with. Each call is one line: the name and
# its arguments, tab-separated.
STUB = r"""#!/bin/sh
name="$(basename "$0")"
{ printf '%s' "$name"; for arg in "$@"; do printf '\t%s' "$arg"; done; printf '\n'; } >> "$STUB_CALLS"
case "$name $*" in
  "az staticwebapp list -g dev-rg"*) echo swa-dev ;;
  "az staticwebapp list -g prod-rg"*) echo swa-prod ;;
  "az staticwebapp show -n swa-dev"*) echo "$STUB_DEV_HOST" ;;
  "az staticwebapp show -n swa-prod"*) echo "$STUB_PROD_HOST" ;;
  "az staticwebapp hostname list"*"length(@)"*) echo 1 ;;
  "az staticwebapp hostname list"*) printf 'neqabacare.com\tReady\n' ;;
  "az staticwebapp hostname show"*"validationToken"*)
    polls=$(cat "$STUB_POLLS" 2>/dev/null || echo 0)
    polls=$((polls + 1))
    echo "$polls" > "$STUB_POLLS"
    [ "$polls" -le "$STUB_EMPTY_POLLS" ] || echo "$STUB_TOKEN" ;;
  "gh variable list"*) echo PUBLIC_HOSTNAME ;;
esac
exit 0
"""


@unittest.skipUnless(BASH, "bash not installed")
class CutoverDomain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        for name in ("az", "gh", "python", "curl"):
            stub = self.dir / name
            stub.write_text(STUB, encoding="utf-8", newline="\n")
            stub.chmod(0o755)
        self.calls_file = self.dir / "calls.txt"

    def run_step(self, *args: str, empty_polls: int = 0, timeout: int = 30):
        env = {
            **os.environ,
            "PATH": f"{self.dir}{os.pathsep}{os.environ['PATH']}",
            "STUB_CALLS": str(self.calls_file),
            "STUB_POLLS": str(self.dir / "polls"),
            "STUB_EMPTY_POLLS": str(empty_polls),
            "STUB_TOKEN": "token-from-azure",
            "STUB_DEV_HOST": DEV_HOST,
            "STUB_PROD_HOST": PROD_HOST,
            "CUTOVER_TOKEN_TIMEOUT": str(timeout),
            "CUTOVER_TOKEN_INTERVAL": "0",
        }
        result = subprocess.run(
            [
                BASH,
                str(SCRIPT),
                "--repo", "o/r",
                "--dev-group", "dev-rg",
                "--prod-group", "prod-rg",
                *args,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )
        # Proves the stubs answered, not a real az or gh.
        self.assertTrue(self.calls_file.exists(), result.stdout + result.stderr)
        return result

    def calls(self, name: str) -> list[list[str]]:
        rows = [line.split("\t") for line in self.calls_file.read_text(encoding="utf-8").splitlines()]
        return [row[1:] for row in rows if row[0] == name]

    def token_polls(self) -> list[list[str]]:
        return [c for c in self.calls("az") if "hostname" in c and "show" in c and "validationToken" in c]

    def assert_windows_can_open(self, path: str) -> None:
        # `/c/Users/...` is not absolute to a Windows program, which is the whole bug.
        self.assertTrue(Path(path).is_absolute(), path)
        self.assertTrue(Path(path).exists(), path)

    # Paths

    def test_preflight_gives_python_paths_windows_can_open(self):
        self.run_step("preflight")
        [record] = self.calls("python")
        self.assertTrue(record[0].endswith("acceptance_record.py"), record)
        self.assert_windows_can_open(record[0])
        self.assert_windows_can_open(record[1])
        self.assertEqual(record[2:], ["--stage", "before-cutover"])

    def test_preflight_asks_curl_to_write_no_posix_path(self):
        result = self.run_step("preflight")
        records = self.calls("curl")
        self.assertTrue(records)
        for record in records:
            self.assertNotIn("/dev/null", record)
            for flag in ("-o", "--output"):
                if flag in record:
                    self.assertTrue(Path(record[record.index(flag) + 1]).is_absolute(), record)
        self.assertNotIn("does not answer", result.stdout)

    def test_preflight_checks_both_sites_are_ready(self):
        # Dev is where a rollback lands, so it must be healthy before the window too.
        result = self.run_step("preflight")
        urls = [arg for record in self.calls("curl") for arg in record if arg.startswith("https://")]
        self.assertEqual(urls, [f"https://{PROD_HOST}/api/ready/", f"https://{DEV_HOST}/api/ready/"])
        self.assertIn(f"production answers on https://{PROD_HOST}/api/ready/", result.stdout)
        self.assertIn(f"dev answers on https://{DEV_HOST}/api/ready/", result.stdout)

    def test_verify_gives_python_a_path_windows_can_open(self):
        self.run_step("verify")
        [record] = self.calls("python")
        self.assertTrue(record[0].endswith("acceptance_smoke.py"), record)
        self.assert_windows_can_open(record[0])
        self.assertIn("https://neqabacare.com", record)

    # attach-prod

    def test_attach_prod_waits_for_the_token_of_a_no_wait_binding(self):
        result = self.run_step("attach-prod", "--execute", empty_polls=2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.token_polls()), 3)
        self.assertTrue(all("prod-rg" in poll for poll in self.token_polls()))
        self.assertRegex(result.stdout, r"TXT\s+_dnsauth\s+token-from-azure")

    def test_attach_prod_says_so_when_no_token_comes(self):
        result = self.run_step("attach-prod", "--execute", empty_polls=1000, timeout=0)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No validation token", result.stderr)
        self.assertIn("--query validationToken", result.stderr)
        self.assertNotIn("token-from-azure", result.stdout)
        self.assertRegex(result.stdout, r"TXT\s+_dnsauth\s+<not issued yet")

    def test_attach_prod_dry_run_does_not_poll(self):
        result = self.run_step("attach-prod")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.token_polls(), [])

    # rollback

    def test_rollback_prints_the_new_dev_token_after_rebinding_dev(self):
        result = self.run_step("rollback", "--execute", empty_polls=1)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = self.calls("az")
        rebind = next(
            i for i, c in enumerate(rows) if c[:3] == ["staticwebapp", "hostname", "set"] and "dev-rg" in c
        )
        polls = [i for i, c in enumerate(rows) if c in self.token_polls()]
        self.assertEqual(len(polls), 2)
        self.assertTrue(all(i > rebind for i in polls))
        self.assertTrue(all("dev-rg" in rows[i] for i in polls))
        self.assertRegex(result.stdout, r"TXT\s+_dnsauth\s+token-from-azure")
        self.assertRegex(result.stdout, rf"CNAME\s+@\s+{DEV_HOST}")
        self.assertRegex(result.stdout, rf"CNAME\s+www\s+{DEV_HOST}")
        self.assertNotIn("restore the old TXT", result.stdout)

    def test_rollback_leaves_the_mail_records_alone(self):
        result = self.run_step("rollback", "--execute")
        for record in ("SPF", "MX", "DMARC", "DKIM"):
            self.assertIn(record, result.stdout)
        self.assertIn("Do not touch", result.stdout)

    def test_rollback_without_a_token_still_gives_dev_the_name_back(self):
        result = self.run_step("rollback", "--execute", empty_polls=1000, timeout=0)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No validation token", result.stderr)
        variables = [c for c in self.calls("gh") if c[:2] == ["variable", "set"]]
        expected = ["variable", "set", "PUBLIC_HOSTNAME", "--env", "dev"]
        self.assertEqual(variables, [[*expected, "--repo", "o/r", "--body", "neqabacare.com"]])
        runs = [c for c in self.calls("gh") if c[:2] == ["workflow", "run"]]
        self.assertEqual([c[c.index("-f") + 1] for c in runs], ["environment=prod", "environment=dev"])

    def test_rollback_dry_run_does_not_poll(self):
        result = self.run_step("rollback")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.token_polls(), [])
        self.assertIn("_dnsauth", result.stdout)


if __name__ == "__main__":
    unittest.main()
