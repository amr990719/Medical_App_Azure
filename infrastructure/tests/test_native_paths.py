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


if __name__ == "__main__":
    unittest.main()
