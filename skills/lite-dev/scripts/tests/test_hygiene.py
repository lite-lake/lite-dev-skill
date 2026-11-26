"""Document hygiene checks and the archive move."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import flow  # noqa: E402

ITEM_ID = "20261126-REQ-234567"
SLUG = f"{ITEM_ID}-demo"

PROFILE = """\
[project]
name = "hygiene-project"
language = "en"
docs_dir = "docs"
work_dir = "docs/work"

[flow]
requires = ">=0.3.5,<0.4"

[id]
format = "{{date}}-{{type}}-{{time}}"

[gate]
l1 = ["test"]

[commands]
test = "echo ok"

[design]
required_for = ["L"]

[docs]
required = ["README.md", "docs/README.md"]
{extra_docs}
[release]
dir = "docs/releases"
"""

ITEM = """\
---
id: {item_id}
title: Demo
type: REQ
priority: P2
size: S
mode: one-shot
owner: alice
created: 2026-11-26
closed: {closed}
---

## Clarify

- Status: clarified

## AC

- [{tick}] AC01 something observable

## Implementation

| Batch | Status | Commit | Notes |
|---|---|---|---|
| B1 | done | abc1234 | — |
"""


class HygieneTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.profile_path = self.root / "docs/flow/profile.toml"
        self.write("README.md", "# project\n\nSee [docs](docs/README.md).\n")
        self.write("docs/README.md", "# docs\n")
        self.write("docs/flow/profile.toml", PROFILE.format(extra_docs=""))
        self.item_dir = self.root / "docs/work/2026-11" / SLUG
        self.write_item(closed="")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_item(self, closed: str) -> None:
        self.write(
            f"docs/work/2026-11/{SLUG}/item.md",
            ITEM.format(item_id=ITEM_ID, closed=closed, tick="x" if closed else " "),
        )

    def run_flow(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = flow.main(["--profile", str(self.profile_path), *args])
        return code, output.getvalue()

    def test_broken_link_fails_check(self) -> None:
        self.write("docs/README.md", "# docs\n\n[missing](nope.md)\n")
        code, output = self.run_flow("check")
        self.assertEqual(code, 1)
        self.assertIn("link target does not exist: nope.md", output)

    def test_fenced_examples_are_not_links(self) -> None:
        self.write("docs/README.md", "# docs\n\n```\n[a](nope.md)\n```\n")
        code, output = self.run_flow("check")
        self.assertEqual(code, 0, output)

    def test_file_missing_from_its_index_is_a_warning(self) -> None:
        self.write("docs/guide.md", "# guide\n")
        code, output = self.run_flow("check")
        self.assertEqual(code, 0, output)
        self.assertIn("docs/guide.md: not linked from docs/README.md", output)

    def test_entry_document_may_not_pin_a_version_port_or_date(self) -> None:
        self.write(
            "README.md",
            "# project\n\nRuns on Python 3.11 at localhost:8080 since 2026-11-01.\n",
        )
        code, output = self.run_flow("check")
        self.assertEqual(code, 0, output)
        self.assertIn("pins a version (Python 3.11)", output)
        self.assertIn("hardcodes a port (localhost:8080)", output)
        self.assertIn("hardcodes a date (2026-11-01)", output)

    def test_duplicate_heading_in_a_release_record_is_an_error(self) -> None:
        self.write(
            "docs/releases/r1.md",
            "# Release\n\n## Gate\n\nPASS\n\n## Gate\n\nFAIL\n",
        )
        code, output = self.run_flow("check")
        self.assertEqual(code, 1)
        self.assertIn("duplicate '## Gate'", output)

    def test_decisions_directory_must_exist_and_be_indexed(self) -> None:
        self.write("docs/flow/profile.toml", PROFILE.format(extra_docs="decisions = \"docs/decisions\"\n"))
        code, output = self.run_flow("check")
        self.assertEqual(code, 1)
        self.assertIn("missing directory: docs/decisions", output)

        self.write("docs/decisions/README.md", "# Decisions\n")
        self.write("docs/decisions/ADR-0001-why.md", "# Why\n")
        code, output = self.run_flow("check")
        self.assertEqual(code, 0, output)
        self.assertIn("ADR-0001-why.md: not linked from docs/decisions/README.md", output)

    def test_archive_refuses_an_open_item(self) -> None:
        code, output = self.run_flow("archive", ITEM_ID)
        self.assertEqual(code, 2)
        self.assertIn("is not closed", output)
        self.assertTrue(self.item_dir.is_dir())

    def test_archive_moves_records_and_restores(self) -> None:
        self.write_item(closed="2026-11-26")
        code, output = self.run_flow("archive", ITEM_ID, "--reason", "shipped")
        self.assertEqual(code, 0, output)

        moved = self.root / "docs/work/_archive/2026-11" / SLUG
        self.assertFalse(self.item_dir.exists())
        self.assertTrue((moved / "item.md").is_file())

        index = (self.root / "docs/work/_archive/README.md").read_text(encoding="utf-8")
        self.assertIn(ITEM_ID, index)
        self.assertIn("shipped", index)

        code, output = self.run_flow("status")
        self.assertEqual(code, 0)
        self.assertIn("no work items", output)
        self.assertIn("1 archived", output)

        code, output = self.run_flow("check")
        self.assertEqual(code, 0, output)

        # A live document must reach history through the archive index.
        self.write(
            "docs/README.md",
            f"# docs\n\n[old](work/_archive/2026-11/{SLUG}/item.md)\n",
        )
        code, output = self.run_flow("check")
        self.assertEqual(code, 0, output)
        self.assertIn("links into _archive/", output)

        code, output = self.run_flow("unarchive", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertTrue((self.item_dir / "item.md").is_file())
        index = (self.root / "docs/work/_archive/README.md").read_text(encoding="utf-8")
        self.assertNotIn(ITEM_ID, index)


if __name__ == "__main__":
    unittest.main(verbosity=2)
