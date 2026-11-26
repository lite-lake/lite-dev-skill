"""End-to-end acceptance: run the real CLI against a copy of examples/minimal.

Covers both execution modes:
  S item: new -> clarify -> check -> gate -> done
  L item: new -> design -> design-ready -> gate -> done
"""
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
        self.root = Path(self._tmp.name) / "project"
        shutil.copytree(EXAMPLE, self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_flow(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(FLOW), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def only_item(self, marker: str) -> Path:
        directories = sorted((self.root / "docs/work").glob(f"*{marker}*"))
        self.assertEqual(len(directories), 1, directories)
        return directories[0]

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
        created = self.run_flow("new", "--title", "Export CSV", "--type", "REQ", "--size", "S")
        self.assertEqual(created.returncode, 0, created.stderr)
        small = self.only_item("-REQ-01-")
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

        early = self.run_flow("done", item_id(small))
        self.assertEqual(early.returncode, 1)
        self.assertIn("unchecked AC", early.stdout)

        self.tick_all_ac(small)
        done = self.run_flow("done", item_id(small))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

        # --- L item: two-phase ---
        created = self.run_flow(
            "new", "--title", "Add Audit Log", "--type", "REQ", "--size", "L"
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        large = self.only_item("-REQ-02-")
        self.clarify_and_fill_ac(
            large, "every write emits an audit line", "the audit log is queryable"
        )
        large_id = item_id(large)

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

        check = self.run_flow("check")
        self.assertEqual(check.returncode, 0, check.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
