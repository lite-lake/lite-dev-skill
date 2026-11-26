import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import flow  # noqa: E402

TODAY = date.today().isoformat()
ITEM_ID = "20260101-REQ-k7m2pa"
MISSING_ID = "20260101-REQ-zzzzzz"

PROFILE = """\
[project]
name = "release-project"
language = "en"

[flow]
requires = ">=0.3.2,<0.4"

[id]
format = "{date}-{type}-{time}"

[gate]
l1 = ["test"]
l3 = ["test"]

[commands]
test = "echo ok"

[release]
channels = ["staging"]
dir = "docs/releases"
gate_level = "l1"
mainline = "main"

[reconcile]
risk_paths = ["migrations/"]

[docs]
required = ["README.md"]
"""

ITEM = f"""\
---
id: {ITEM_ID}
title: Demo
type: REQ
priority: P2
size: S
mode: one-shot
owner: alice
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
        self.root = Path(self._tmp.name).resolve()
        self.write("docs/flow/profile.toml", PROFILE)
        self.write("README.md", "# release project\n")
        self.write(f"docs/work/2026-01/{ITEM_ID}-demo/item.md", ITEM)
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        self.commit("chore: initial import")
        self._env = mock.patch.dict(os.environ, {"LITE_DEV_OWNER": "releaser"})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
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

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").strip()

    def commit(self, message: str, path: str | None = None, content: str = "") -> str:
        if path:
            self.write(path, content)
        self.git("add", "-A")
        self.git("commit", "-qm", message)
        return self.head()

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

    def write_record(
        self,
        source: str,
        previous: str = "none",
        name: str | None = None,
        channel: str = "staging",
        day: str = "2026-01-01",
    ) -> Path:
        name = name or f"{channel}-2026-01-01-{source[:6]}.md"
        self.write(
            f"docs/releases/{name}",
            "---\n"
            f"channel: {channel}\n"
            f"date: {day}\n"
            f"source: {source}\n"
            f"previous: {previous}\n"
            "by: tester\n"
            f"tool: {flow.__version__}\n"
            "---\n\n# Release\n",
        )
        return self.root / "docs/releases" / name

    def record_release(self, *extra: str) -> tuple[int, str]:
        return self.run_flow(
            "release",
            "--channel",
            "staging",
            "--record",
            "--rollback",
            "revert",
            "--note",
            "no item for bootstrap commits",
            *extra,
        )

    def test_reconcile_reports_debt_and_exits_zero(self) -> None:
        self.commit(f"feat: wire x ({MISSING_ID})", "src/x.py", "x = 1\n")
        code, output = self.run_flow("reconcile", "--channel", "staging", "--json")
        self.assertEqual(code, 0, output)
        data = json.loads(output)
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["no_item"]), 1)
        self.assertEqual(data["missing_item"][0]["item"], MISSING_ID)
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
        self.commit(f"feat: wire x ({MISSING_ID})", "src/x.py", "x = 1\n")
        head = self.head()
        code, output = self.record_release()
        self.assertEqual(code, 0, output)
        records = self.record_paths()
        self.assertEqual(len(records), 1, output)
        record = records[0]
        self.assertTrue(record.name.startswith(f"staging-{TODAY}-"), record.name)
        self.assertIn(head[:6], record.name)
        text = record.read_text(encoding="utf-8")
        self.assertIn("channel: staging", text)
        self.assertIn("previous: none", text)
        self.assertIn("by: releaser", text)
        self.assertIn(f"tool: {flow.__version__}", text)
        self.assertIn(head, text)
        self.assertIn("PASS l1", text)
        self.assertIn("revert", text)
        self.assertIn("no item for bootstrap commits", text)
        self.assertIn(MISSING_ID, text)

    def test_dry_run_is_read_only(self) -> None:
        code, output = self.run_flow("release", "--channel", "staging")
        self.assertEqual(code, 0, output)
        self.assertIn("gate: l1 (runs on --record)", output)
        self.assertFalse((self.root / "docs/releases").exists())

    def test_second_release_uses_previous_watermark(self) -> None:
        first_code, first_output = self.record_release()
        self.assertEqual(first_code, 0, first_output)
        first_text = self.record_paths()[0].read_text(encoding="utf-8")
        first_source = re.search(r"^source: (\S+)$", first_text, re.M).group(1)

        self.commit("docs: record release", "notes.txt", "one\n")
        head = self.commit("chore: follow-up", "follow.txt", "two\n")
        code, output = self.record_release()
        self.assertEqual(code, 0, output)
        records = self.record_paths()
        self.assertEqual(len(records), 2, output)
        second = [path for path in records if head[:6] in path.name][0]
        text = second.read_text(encoding="utf-8")
        self.assertIn(f"previous: {first_source}", text)
        self.assertIn("chore: follow-up", text)
        self.assertNotIn("initial import", text)

    def test_dirty_tree_is_refused(self) -> None:
        self.write("scratch.txt", "x\n")
        code, output = self.record_release()
        self.assertEqual(code, 1)
        self.assertIn("dirty", output)

    def test_channel_branch_is_refused(self) -> None:
        self.git("checkout", "-q", "-b", "staging")
        code, output = self.record_release()
        self.assertEqual(code, 1)
        self.assertIn("not the mainline", output)

    def test_feature_branch_is_refused(self) -> None:
        self.git("checkout", "-q", "-b", "feature/x")
        self.commit("feat: x", "src/x.py", "x = 1\n")
        code, output = self.record_release()
        self.assertEqual(code, 1)
        self.assertIn("not the mainline", output)

    def test_detached_head_is_refused(self) -> None:
        self.git("checkout", "-q", "--detach")
        code, output = self.record_release()
        self.assertEqual(code, 1)
        self.assertIn("detached HEAD", output)

    def test_stale_clone_is_refused(self) -> None:
        # A record claims a commit from a side branch; main does not contain it.
        self.git("checkout", "-q", "-b", "side")
        side = self.commit("feat: side", "side.txt", "s\n")
        self.git("checkout", "-q", "main")
        self.write_record(side)
        self.commit("docs: import a foreign release record")
        code, output = self.record_release()
        self.assertEqual(code, 1)
        self.assertIn("not an ancestor of HEAD", output)

    def test_corrupt_record_stops_the_channel(self) -> None:
        self.write("docs/releases/staging-bad.md", "---\nchannel: staging\nsource: nope\n---\n")
        code, output = self.run_flow("reconcile", "--channel", "staging")
        self.assertEqual(code, 2)
        self.assertIn("not a full commit sha", output)

    def test_divergent_records_stop_the_channel(self) -> None:
        self.git("checkout", "-q", "-b", "side")
        side = self.commit("feat: side", "side.txt", "s\n")
        self.git("checkout", "-q", "main")
        main = self.commit("feat: main", "main.txt", "m\n")
        self.write_record(main, name="staging-2026-01-01-main.md")
        self.write_record(side, name="staging-2026-01-01-side.md")
        self.commit("docs: merge two release records")
        code, output = self.run_flow("reconcile", "--channel", "staging")
        self.assertEqual(code, 2)
        self.assertIn("divergent release records", output)

    def test_broken_previous_chain_is_an_error(self) -> None:
        older = self.head()
        newer = self.commit("feat: next", "next.txt", "n\n")
        self.write_record(older, name="staging-2026-01-01-old.md")
        self.write_record(newer, name="staging-2026-01-01-new.md")
        self.commit("docs: two records without a chain")
        code, output = self.run_flow("reconcile", "--channel", "staging")
        self.assertEqual(code, 2)
        self.assertIn("does not follow", output)

    def test_watermark_follows_ancestry_not_dates_or_filenames(self) -> None:
        older = self.head()
        newer = self.commit("feat: newer", "newer.txt", "n\n")
        # The ancestor record has the later date and the filename that sorts last.
        self.write_record(older, name="staging-2026-01-02-zzzzzz.md", day="2026-01-02")
        self.write_record(
            newer,
            previous=older,
            name="staging-2026-01-01-aaaaaa.md",
            day="2026-01-01",
        )
        self.commit("docs: two records in the misleading order")
        code, output = self.run_flow("release")
        self.assertEqual(code, 0, output)
        self.assertIn(f"last 2026-01-01 {newer[:7]}", output)
        self.assertNotIn(f"last 2026-01-02 {older[:7]}", output)

    def test_record_lists_artifacts(self) -> None:
        code, output = self.record_release("--artifact", "app@1.2.3", "--artifact", "db/001")
        self.assertEqual(code, 0, output)
        text = self.record_paths()[0].read_text(encoding="utf-8")
        self.assertIn("## Artifacts", text)
        self.assertIn("- app@1.2.3", text)
        self.assertIn("- db/001", text)

    def test_required_artifacts_are_enforced(self) -> None:
        self.write(
            "docs/flow/profile.toml",
            PROFILE.replace('mainline = "main"', 'mainline = "main"\nrequire_artifacts = true'),
        )
        code, output = self.record_release()
        self.assertEqual(code, 1)
        self.assertIn("--artifact is required", output)

    def test_non_ancestor_since_is_rejected(self) -> None:
        self.git("checkout", "-q", "-b", "side")
        side = self.commit("feat: side", "side.txt", "s\n")
        self.git("checkout", "-q", "main")
        code, output = self.run_flow(
            "reconcile", "--channel", "staging", "--since", side
        )
        self.assertEqual(code, 2)
        self.assertIn("not an ancestor of HEAD", output)

    def test_release_lists_channels_and_last_record(self) -> None:
        code, output = self.run_flow("release")
        self.assertEqual(code, 0)
        self.assertIn("channels: staging", output)
        self.assertIn("no record", output)

        head = self.head()
        self.record_release()
        code, output = self.run_flow("release")
        self.assertEqual(code, 0)
        self.assertIn("last", output)
        self.assertIn(head[:7], output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
