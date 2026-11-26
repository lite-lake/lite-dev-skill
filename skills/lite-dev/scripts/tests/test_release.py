import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import flow  # noqa: E402

TODAY = date.today().isoformat()

PROFILE = """\
[project]
name = "release-project"
language = "en"

[id]
format = "{date}-{type}-{seq:02d}"

[gate]
l1 = ["test"]
l3 = ["test"]

[commands]
test = "echo ok"

[release]
channels = ["staging"]
dir = "docs/releases"
gate_level = "l1"

[reconcile]
risk_paths = ["migrations/"]

[docs]
required = ["README.md"]
"""

ITEM = """\
---
id: 20260101-REQ-01
title: Demo
type: REQ
priority: P2
size: S
mode: one-shot
created: 2026-01-01
closed:
---

## Clarify

- Status: clarified
- Questions: none
- Confirmed assumptions: none

## AC

- [ ] AC01 works

## Notes

- Rollback: revert
"""


class ReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.write("docs/flow/profile.toml", PROFILE)
        self.write("README.md", "# release project\n")
        self.write("docs/work/20260101-REQ-01-demo/item.md", ITEM)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        self.commit("chore: initial import")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return result.stdout

    def commit(self, message: str, path: str | None = None, content: str = "") -> str:
        if path:
            self.write(path, content)
        self.git("add", "-A")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD").strip()

    def run_flow(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = flow.main(
                ["--profile", str(self.root / "docs/flow/profile.toml"), *args]
            )
        return code, output.getvalue()

    def record_paths(self) -> list[Path]:
        directory = self.root / "docs/releases"
        return sorted(directory.glob("*.md")) if directory.is_dir() else []

    def test_reconcile_reports_debt_and_exits_zero(self) -> None:
        self.commit("feat: wire x (20260101-REQ-99)", "src/x.py", "x = 1\n")
        code, output = self.run_flow("reconcile", "--channel", "staging", "--json")
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["no_item"]), 1)
        self.assertEqual(data["missing_item"][0]["item"], "20260101-REQ-99")
        self.assertTrue(data["blocking"])

    def test_release_refuses_without_note_when_debt_exists(self) -> None:
        code, output = self.run_flow(
            "release", "--channel", "staging", "--record", "--rollback", "revert"
        )
        self.assertEqual(code, 1)
        self.assertIn("without work items", output)
        self.assertEqual(self.record_paths(), [])

    def test_release_requires_rollback(self) -> None:
        code, output = self.run_flow(
            "release", "--channel", "staging", "--record", "--note", "debt"
        )
        self.assertEqual(code, 1)
        self.assertIn("--rollback is required", output)

    def test_release_records_gate_and_commits(self) -> None:
        self.commit("feat: wire x (20260101-REQ-99)", "src/x.py", "x = 1\n")
        code, output = self.run_flow(
            "release",
            "--channel",
            "staging",
            "--record",
            "--rollback",
            "revert the commit",
            "--note",
            "chore: initial import has no item",
        )
        self.assertEqual(code, 0, output)
        record = self.root / "docs/releases" / f"staging-{TODAY}.md"
        self.assertTrue(record.is_file(), output)
        text = record.read_text(encoding="utf-8")
        self.assertIn("channel: staging", text)
        self.assertIn("previous: none", text)
        self.assertIn(self.git("rev-parse", "HEAD").strip(), text)
        self.assertIn("PASS l1", text)
        self.assertIn("revert the commit", text)
        self.assertIn("chore: initial import has no item", text)
        self.assertIn("20260101-REQ-99", text)

    def test_dry_run_is_read_only(self) -> None:
        code, output = self.run_flow("release", "--channel", "staging")
        self.assertEqual(code, 0)
        self.assertIn("gate: l1 (runs on --record)", output)
        self.assertFalse((self.root / "docs/releases").exists())

    def test_second_release_uses_previous_watermark(self) -> None:
        first_code, first_output = self.run_flow(
            "release",
            "--channel",
            "staging",
            "--record",
            "--rollback",
            "revert",
            "--note",
            "initial debt",
        )
        self.assertEqual(first_code, 0, first_output)
        first = (self.root / "docs/releases" / f"staging-{TODAY}.md").read_text(
            encoding="utf-8"
        )
        first_source = re.search(r"^source: (\S+)$", first, re.M).group(1)

        self.commit("docs: record release", "notes.txt", "one\n")
        self.commit("chore: follow-up", "follow.txt", "two\n")
        code, output = self.run_flow(
            "release",
            "--channel",
            "staging",
            "--record",
            "--rollback",
            "revert",
            "--note",
            "follow-up has no item",
        )
        self.assertEqual(code, 0, output)
        second_path = self.root / "docs/releases" / f"staging-{TODAY}-2.md"
        self.assertTrue(second_path.is_file(), output)
        second = second_path.read_text(encoding="utf-8")
        self.assertIn(f"previous: {first_source}", second)
        self.assertIn("chore: follow-up", second)
        self.assertNotIn("initial import", second)

    def test_dirty_tree_is_refused(self) -> None:
        self.write("scratch.txt", "x\n")
        code, output = self.run_flow(
            "release",
            "--channel",
            "staging",
            "--record",
            "--rollback",
            "revert",
            "--note",
            "debt",
        )
        self.assertEqual(code, 1)
        self.assertIn("dirty", output)

    def test_channel_branch_is_refused(self) -> None:
        self.git("checkout", "-q", "-b", "staging")
        code, output = self.run_flow(
            "release",
            "--channel",
            "staging",
            "--record",
            "--rollback",
            "revert",
            "--note",
            "debt",
        )
        self.assertEqual(code, 1)
        self.assertIn("release channel", output)

    def test_release_lists_channels_and_last_record(self) -> None:
        code, output = self.run_flow("release")
        self.assertEqual(code, 0)
        self.assertIn("channels: staging", output)
        self.assertIn("no record", output)

        self.run_flow(
            "release",
            "--channel",
            "staging",
            "--record",
            "--rollback",
            "revert",
            "--note",
            "debt",
        )
        code, output = self.run_flow("release")
        self.assertIn("last", output)
        self.assertIn(self.git("rev-parse", "HEAD").strip()[:7], output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
