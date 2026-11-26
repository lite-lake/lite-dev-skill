"""End-to-end acceptance: run the real CLI against a copy of examples/minimal.

Covers both execution modes:
  S item: new -> clarify -> check -> gate -> done
  L item: new -> design -> design-ready -> gate -> done
and the multi-clone case: two clones create items on the same day without
talking to each other, and neither id collides after they merge.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SKILL = REPO / "skills/lite-dev"
FLOW = SKILL / "scripts/flow.py"
EXAMPLE = REPO / "examples/minimal"
TODAY = date.today().isoformat()


def item_id(directory: Path) -> str:
    text = (directory / "item.md").read_text(encoding="utf-8")
    match = re.search(r"^id:\s*(\S+)\s*$", text, re.M)
    assert match, f"no id in {directory}/item.md"
    return match.group(1)


class AcceptanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = (Path(self._tmp.name) / "project").resolve()
        shutil.copytree(EXAMPLE, self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_flow(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        env = dict(os.environ, LITE_DEV_OWNER="acceptance")
        return subprocess.run(
            [sys.executable, str(FLOW), *args],
            cwd=cwd or self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

    def created_id(self, result: subprocess.CompletedProcess) -> str:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        match = re.search(r"^created (\S+)$", result.stdout, re.M)
        self.assertIsNotNone(match, result.stdout)
        return match.group(1)

    def item_dir(self, item_id: str, root: Path | None = None) -> Path:
        """Find <work_dir>/<YYYY-MM>/<id>-<slug> for the given id."""
        base = (root or self.root) / "docs/work"
        matches = [
            directory
            for bucket in base.iterdir()
            if bucket.is_dir()
            for directory in bucket.iterdir()
            if directory.is_dir() and directory.name.startswith(item_id)
        ]
        self.assertEqual(len(matches), 1, matches)
        return matches[0]

    def month_of(self, item_id: str) -> str:
        """'20261126-REQ-...' -> '2026-11'."""
        return f"{item_id[0:4]}-{item_id[4:6]}"

    def clarify_and_fill_ac(self, directory: Path, first: str, second: str) -> None:
        path = directory / "item.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("- Status: pending", "- Status: clarified")
        text = text.replace("- [ ] AC01 <observable outcome>", f"- [ ] AC01 {first}")
        text = text.replace("- [ ] AC02 <observable outcome>", f"- [ ] AC02 {second}")
        path.write_text(text, encoding="utf-8")

    def tick_all_ac(self, directory: Path) -> None:
        path = directory / "item.md"
        path.write_text(
            path.read_text(encoding="utf-8")
            .replace("- [ ] AC01", "- [x] AC01")
            .replace("- [ ] AC02", "- [x] AC02"),
            encoding="utf-8",
        )

    def test_full_loop(self) -> None:
        status = self.run_flow("status")
        self.assertEqual(status.returncode, 0)
        self.assertIn("no work items", status.stdout)

        # --- S item: one-shot ---
        small_id = self.created_id(
            self.run_flow("new", "--title", "Export CSV", "--type", "REQ", "--size", "S")
        )
        small = self.item_dir(small_id)
        self.clarify_and_fill_ac(
            small,
            "exporting a list returns a CSV file",
            "an empty list returns a header-only file",
        )

        check = self.run_flow("check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

        gate = self.run_flow("gate", "--level", "l1")
        self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
        self.assertIn("PASS", gate.stdout)

        early = self.run_flow("done", small_id)
        self.assertEqual(early.returncode, 1)
        self.assertIn("unchecked AC", early.stdout)

        self.tick_all_ac(small)
        done = self.run_flow("done", small_id)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

        # --- L item: two-phase ---
        large_id = self.created_id(
            self.run_flow("new", "--title", "Add Audit Log", "--type", "REQ", "--size", "L")
        )
        large = self.item_dir(large_id)
        self.clarify_and_fill_ac(
            large, "every write emits an audit line", "the audit log is queryable"
        )

        design = (SKILL / "templates/design.md").read_text(encoding="utf-8")
        replacements = {
            "<ID>": large_id,
            "- Goal:": "- Goal: add an audit log",
            "- Scope:": "- Scope: one module",
            "- Out:": "- Out: no retention policy",
            "- Verify:": "- Verify: unit tests",
            "- Rollback:": "- Rollback: revert the commit",
            "- Confirmed: no": "- Confirmed: yes",
            "- Date:": f"- Date: {TODAY}",
            "| B1 | | . | AC01 | — |": "| B1 | write store | . | AC01 | — |",
            "| B2 | | . | AC02 | — |": "| B2 | read API | . | AC02 | B1 |",
            "| AC01 | | | |": "| AC01 | unit test | local | output |\n| AC02 | unit test | local | output |",
            "<components and data flow, or the key user journey: current -> changed>":
                "writer -> store -> reader",
            "TBD\n\n## Batches": "Add a store and a reader, covered by unit tests.\n\n## Batches",
            "## Rollback\n\nTBD": "## Rollback\n\nRevert the single commit.",
        }
        for token, value in replacements.items():
            design = design.replace(token, value)
        (large / "design.md").write_text(design, encoding="utf-8")

        ready = self.run_flow("design-ready", large_id)
        self.assertEqual(ready.returncode, 0, ready.stdout)
        self.assertIn("ready", ready.stdout)

        lgate = self.run_flow("gate", "--level", "l3", "--work", large_id)
        self.assertEqual(lgate.returncode, 0, lgate.stdout)

        self.tick_all_ac(large)
        ldone = self.run_flow("done", large_id)
        self.assertEqual(ldone.returncode, 0, ldone.stdout)

        final = self.run_flow("status")
        self.assertEqual(final.returncode, 0)
        self.assertIn("done 2", final.stdout)
        self.assertIn("acceptance", final.stdout)

        check = self.run_flow("check")
        self.assertEqual(check.returncode, 0, check.stdout)

    def test_two_clones_allocate_distinct_ids(self) -> None:
        first_id = self.created_id(
            self.run_flow("new", "--title", "Same Title", "--type", "REQ", "--size", "S")
        )
        other = (Path(self._tmp.name) / "other").resolve()
        shutil.copytree(EXAMPLE, other)
        second_id = self.created_id(
            self.run_flow(
                "new", "--title", "Same Title", "--type", "REQ", "--size", "S", cwd=other
            )
        )
        self.assertNotEqual(first_id, second_id)

        # Merge the second clone's work item into the first, as git would.
        month = self.month_of(second_id)
        shutil.copytree(
            other / "docs/work" / month / f"{second_id}-Same-Title",
            self.root / "docs/work" / month / f"{second_id}-Same-Title",
        )
        check = self.run_flow("check")
        self.assertEqual(check.returncode, 0, check.stdout)

        for root, created in ((self.root, first_id), (self.root, second_id)):
            directory = self.item_dir(created, root=root)
            self.clarify_and_fill_ac(directory, "one", "two")
            self.tick_all_ac(directory)
            done = self.run_flow("done", created)
            self.assertEqual(done.returncode, 0, done.stdout)
            self.assertNotIn("ambiguous", done.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
