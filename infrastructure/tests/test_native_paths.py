"""On Windows, `az` is a Windows program. These scripts set MSYS_NO_PATHCONV=1 so Git Bash leaves
/subscriptions/... alone, which also stops it translating file paths, so each script must hand `az`
a path Windows can open. Found by the first real run of the bootstrap on 2026-11-05."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "infrastructure" / "scripts"
BASH = shutil.which("bash")


@unittest.skipUnless(BASH, "bash not installed")
class FilesHandedToAz(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.calls = self.dir / "calls.txt"
        self.stub(
            "az",
            'echo "$*" >> "$STUB_CALLS"\n'
            'case "$*" in\n'
            '  *"job show"*) echo /subscriptions/s/job ;;\n'
            '  *"--url"*"/start"*) echo execution-1 ;;\n'
            '  *"execution show"*) echo Succeeded ;;\n'
            'esac\n',
        )

    def stub(self, name: str, body: str) -> None:
        path = self.dir / name
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
        path.chmod(0o755)

    def test_run_job_command_posts_a_body_windows_can_open(self):
        # `az rest --method get` writes to stdout; the wrapper redirects it, so give it valid JSON.
        self.stub(
            "az",
            'echo "$*" >> "$STUB_CALLS"\n'
            'case "$*" in\n'
            '  *"job show"*) echo /subscriptions/s/job ;;\n'
            '  *"--method get"*) echo \'{"containers": [{"name": "migrate"}]}\' ;;\n'
            '  *"--method post"*) echo execution-1 ;;\n'
            '  *"execution show"*) echo Succeeded ;;\n'
            'esac\n',
        )
        result = subprocess.run(
            [
                BASH,
                str(SCRIPTS / "run-job-command.sh"),
                "--job", "caj-migrate",
                "--resource-group", "rg",
                "--", "python", "manage.py", "release_check",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={
                **os.environ,
                "PATH": f"{self.dir}{os.pathsep}{os.environ['PATH']}",
                "STUB_CALLS": str(self.calls),
            },
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        post = [
            line for line in self.calls.read_text(encoding="utf-8").splitlines() if "--method post" in line
        ]
        self.assertEqual(len(post), 1)
        body = re.search(r"--body @(\S+)", post[0]).group(1)
        # `/tmp/...` is not absolute to a Windows program, which is the whole bug.
        self.assertTrue(Path(body).is_absolute(), body)


class EveryScriptConverts(unittest.TestCase):
    """A file argument added later must not bring the bug back."""

    PATTERN = re.compile(r'(--file|--template-file|--parameters|--body|--role-definition|-claims|-accesses)\s+"?@?\$')

    def test_each_file_given_to_az_is_converted(self):
        for name in (
            "bootstrap-production.sh",
            "run-job-command.sh",
            "setup-github-oidc.sh",
            "create-entra-app.sh",
            "cutover-domain.sh",
        ):
            source = (SCRIPTS / name).read_text(encoding="utf-8")
            self.assertIn("native_path()", source, name)
            for line in source.splitlines():
                if not line.lstrip().startswith(("az ", "act az", "--")) and " az " not in line:
                    continue
                if "gh " in line or not self.PATTERN.search(line):
                    continue
                # Converted once, where they are defined.
                if "$TEMPLATE" in line or "$PARAM_FILE" in line:
                    continue
                self.assertIn("native_path", line, f"{name}: {line.strip()}")


class CutoverHandsWindowsPaths(unittest.TestCase):
    """python and curl are Windows programs under Git Bash too. The first dry run of the cutover,
    on 2026-11-07, failed on `C:\\c\\Users\\...` and on `curl -o /dev/null` (exit 23)."""

    SOURCE = (SCRIPTS / "cutover-domain.sh").read_text(encoding="utf-8")

    def test_it_has_the_helper_of_its_siblings(self):
        self.assertIn("native_path() {\n    if command -v cygpath >/dev/null 2>&1; then", self.SOURCE)

    def test_each_path_given_to_python_is_converted(self):
        lines = [line for line in self.SOURCE.splitlines() if re.match(r"\s*(if !\s+)?python\b", line)]
        self.assertTrue(lines)
        for line in lines:
            paths = list(re.finditer(r'"\$\{(?:SCRIPT_DIR|REPO_ROOT)\}', line))
            self.assertTrue(paths, line.strip())
            for path in paths:
                self.assertTrue(
                    line[: path.start()].endswith("native_path "), f"not converted: {line.strip()}"
                )

    def test_curl_writes_no_file_by_a_posix_path(self):
        self.assertNotRegex(self.SOURCE, r"(-o|--output)\s+/dev/null")
        for line in self.SOURCE.splitlines():
            if re.search(r"\bcurl\b", line) and re.search(r"\s(-o|--output)\s", line):
                self.assertIn("native_path", line, line.strip())


if __name__ == "__main__":
    unittest.main()
