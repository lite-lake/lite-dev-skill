"""Bundled extensions: `{skill}` substitution, the security scan, deploy manifests."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SKILL = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import flow  # noqa: E402
from flowlib import profile as profile_mod  # noqa: E402
from flowlib.profile import SKILL_ROOT  # noqa: E402

SCAN = SKILL / "extensions/security-scan/scan.py"
DEPLOY = SKILL / "extensions/deploy-lane/deploy_check.py"

PROFILE = """\
[project]
name = "ext-project"
language = "en"

[flow]
requires = ">=0.3.5,<0.4"

[id]
format = "{date}-{type}-{time}"

[gate]
l1 = ["test"]

[commands]
test = "echo ok"

[docs]
required = []

[extensions]
enabled = ["security-scan"]
dir = "docs/flow/extensions"
"""

VALID_MANIFEST = {
    "environment": "test",
    "deployed_at": "2026-11-26T09:30:00Z",
    "operator": "alice",
    "git": {"core": "abc1234"},
    "images": [
        {
            "repo": "registry.example/app",
            "tag": "test-abc1234",
            "digest": "sha256:" + "a" * 64,
        }
    ],
    "rollback": "test-abc0000",
}


class BundledExtensionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def test_skill_token_resolves_to_the_installed_skill(self) -> None:
        self.write("docs/flow/profile.toml", PROFILE)
        profile = profile_mod.load(self.root / "docs/flow/profile.toml")
        command = profile.commands["security_scan"]
        self.assertIn(str(SKILL_ROOT), command)
        self.assertNotIn("{skill}", command)
        self.assertIn("security_scan", profile.gate["l3"])

    def test_flow_gate_runs_a_bundled_extension_command(self) -> None:
        self.write("docs/flow/profile.toml", PROFILE)
        self.git("init", "-q")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = flow.main(
                ["--profile", str(self.root / "docs/flow/profile.toml"), "gate", "--level", "l3"]
            )
        self.assertEqual(code, 0, output.getvalue())
        self.assertIn("security_scan", output.getvalue())

    def run_scan(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCAN)],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_security_scan_fails_on_a_tracked_credential(self) -> None:
        self.git("init", "-q")
        self.write("src/config.py", 'aws = "AKIAABCDEFGHIJKLMNOP"\n')
        self.git("add", "-A")
        result = self.run_scan()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("cloud-access-key", result.stdout)

        self.write("docs/flow/security-allow.txt", "src/config.py  # test fixture\n")
        self.git("add", "-A")
        result = self.run_scan()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_security_scan_refuses_outside_a_repository(self) -> None:
        result = self.run_scan()
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a git repository", result.stdout)

    def test_security_scan_flags_a_tracked_sensitive_file(self) -> None:
        self.git("init", "-q")
        self.write(".env", "OK=1\n")
        self.git("add", "-A")
        result = self.run_scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("sensitive file is tracked", result.stdout)

    def run_deploy(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(DEPLOY), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_deploy_check_passes_a_complete_manifest(self) -> None:
        self.write("docs/releases/manifests/test-deployment.json", json.dumps(VALID_MANIFEST))
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("PASS", result.stdout)

    def test_deploy_check_refuses_placeholders_and_floating_tags(self) -> None:
        manifest = dict(VALID_MANIFEST)
        manifest["operator"] = "<name>"
        manifest["images"] = [
            {
                "repo": "registry.example/app",
                "tag": "latest",
                "digest": "sha256:" + "b" * 64,
            }
        ]
        self.write("docs/releases/manifests/test-deployment.json", json.dumps(manifest))
        result = self.run_deploy()
        self.assertEqual(result.returncode, 1)
        self.assertIn("placeholder", result.stdout)
        self.assertIn("floating tag", result.stdout)

    def test_deploy_check_requires_an_explicit_first_deploy(self) -> None:
        manifest = dict(VALID_MANIFEST)
        manifest["rollback"] = "none"
        self.write("docs/releases/manifests/test-deployment.json", json.dumps(manifest))
        result = self.run_deploy()
        self.assertEqual(result.returncode, 1)
        self.assertIn("first_deploy", result.stdout)

        manifest["first_deploy"] = True
        self.write("docs/releases/manifests/test-deployment.json", json.dumps(manifest))
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_deploy_check_enforces_the_requested_environment(self) -> None:
        self.write("docs/releases/manifests/prod-deployment.json", json.dumps(VALID_MANIFEST))
        result = self.run_deploy("--env", "prod")
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected 'prod'", result.stdout)

    def test_deploy_check_passes_when_the_lane_has_not_started(self) -> None:
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("nothing to check", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
