"""The handoff prompt is assembled from artifacts, not retyped by the model."""

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
SLUG = f"{ITEM_ID}-export-csv"

PROFILE = """\
[project]
name = "handoff-project"
language = "{language}"
docs_dir = "docs"
work_dir = "docs/work"

[flow]
requires = ">=0.3.5,<0.4"

[id]
format = "{{date}}-{{type}}-{{time}}"

[gate]
l1 = ["test"]
l3 = ["test"]

[commands]
test = "echo ok"

[docs]
required = ["README.md"]
"""

ITEM = """\
---
id: {item_id}
title: Export CSV
type: REQ
priority: P2
size: L
mode: two-phase
owner: alice
created: 2026-11-26
closed:
---

## Clarify

- Status: clarified
- Questions: none

## AC

- [ ] AC01 rows come out as CSV
- [ ] AC02 the route returns the file

## Implementation

| Batch | Status | Commit | Notes |
|---|---|---|---|
| B1 | done | abc1234 | — |
| B2 | pending | — | — |
"""

DESIGN = """\
---
item: {item_id}
status: ready
---

# {item_id} design

## Handoff

- Goal: export rows as CSV
- Scope: one endpoint
- Out: no streaming
- Verify: unit tests
- Rollback: revert the commit

## Diagram

```text
api -> csv
```

## Confirmation

- Confirmed: yes
- Date: 2026-11-26

## Approach

Add an exporter.

## Batches

| Batch | Goal | Repo | AC | Depends |
|---|---|---|---|---|
| B1 | exporter | . | AC01 | — |
| B2 | route | . | AC02 | B1 |

## Impact

- Contracts: none

## Verification

| AC | Command | Environment | Evidence |
|---|---|---|---|
| AC01 | unit | local | output |
| AC02 | unit | local | output |

## Rollback

Revert the commit.

## Open Decisions

None
"""


class HandoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.profile_path = self.root / "docs/flow/profile.toml"
        self.directory = self.root / "docs/work/2026-11" / SLUG
        self.write("README.md", "# r\n")
        self.write("docs/flow/profile.toml", PROFILE.format(language="en"))
        self.write("docs/work/2026-11/" + SLUG + "/item.md", ITEM.format(item_id=ITEM_ID))
        self.write("docs/work/2026-11/" + SLUG + "/design.md", DESIGN.format(item_id=ITEM_ID))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_flow(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = flow.main(["--profile", str(self.profile_path), *args])
        return code, output.getvalue()

    def test_handoff_names_paths_progress_and_next_batch(self) -> None:
        code, output = self.run_flow("handoff", ITEM_ID)
        self.assertEqual(code, 0)
        self.assertIn(f"Continue work item {ITEM_ID}", output)
        self.assertIn(f"docs/work/2026-11/{SLUG}/item.md", output)
        self.assertIn(f"docs/work/2026-11/{SLUG}/design.md", output)
        self.assertIn("Batches: B1 done, B2 pending", output)
        self.assertIn("Next: B2 — route", output)
        self.assertIn("gate --level l1 --work", output)
        # The handoff section is copied verbatim, not paraphrased.
        self.assertIn("- Goal: export rows as CSV", output)
        self.assertIn("confirmed 2026-11-26", output)

    def test_batch_dispatch_is_scoped(self) -> None:
        code, output = self.run_flow("handoff", ITEM_ID, "--batch", "B2")
        self.assertEqual(code, 0)
        self.assertIn(f"implement role for work item {ITEM_ID}, batch B2", output)
        self.assertIn("Batch B2: route; repo .; covers AC02; depends on B1.", output)
        self.assertIn("Do not commit", output)
        self.assertIn("Return at most 30 lines", output)

    def test_unknown_batch_lists_the_defined_ones(self) -> None:
        code, output = self.run_flow("handoff", ITEM_ID, "--batch", "B9")
        self.assertEqual(code, 2)
        self.assertIn("B1, B2", output)

    def test_blocked_batch_is_surfaced_and_not_dispatched(self) -> None:
        path = self.directory / "item.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "| B2 | pending | — | — |",
                "| B2 | blocked | — | waiting on contract |",
            ),
            encoding="utf-8",
        )
        code, output = self.run_flow("handoff", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertIn("B2 blocked", output)
        self.assertIn("BLOCKED", output)
        code, output = self.run_flow("handoff", ITEM_ID, "--batch", "B2")
        self.assertEqual(code, 2)
        self.assertIn("blocked", output)

    def test_draft_design_is_not_announced_as_confirmed(self) -> None:
        path = self.directory / "design.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("status: ready", "status: draft").replace(
            "- Confirmed: yes", "- Confirmed: no"
        )
        path.write_text(text, encoding="utf-8")
        code, output = self.run_flow("handoff", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertIn("not ready or not confirmed", output)
        self.assertNotIn("plan is confirmed", output)

    def test_batch_with_an_unfinished_dependency_is_refused(self) -> None:
        path = self.directory / "item.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "| B1 | done | abc1234 | — |", "| B1 | pending | — | — |"
            ),
            encoding="utf-8",
        )
        code, output = self.run_flow("handoff", ITEM_ID, "--batch", "B2")
        self.assertEqual(code, 2)
        self.assertIn("not done", output)
        self.assertIn("B1", output)

    def test_done_batch_cannot_be_dispatched_again(self) -> None:
        code, output = self.run_flow("handoff", ITEM_ID, "--batch", "B1")
        self.assertEqual(code, 2)
        self.assertIn("already done", output)
        self.assertIn("B2", output)

    def test_design_without_batches_says_so(self) -> None:
        path = self.directory / "design.md"
        text = path.read_text(encoding="utf-8")
        start = text.index("## Batches")
        end = text.index("## Impact")
        path.write_text(
            text[:start] + "## Batches\n\nNone.\n\n" + text[end:], encoding="utf-8"
        )
        code, output = self.run_flow("handoff", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertIn("has no ## Batches table", output)
        self.assertNotIn("no design.md yet", output)

    def test_commit_gate_is_named_separately(self) -> None:
        code, output = self.run_flow("handoff", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertIn("Commit gate:", output)
        self.assertIn("--level l3", output)

    def test_ready_but_invalid_design_is_not_confirmed(self) -> None:
        path = self.directory / "design.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("## Handoff", "## 交接摘要"),
            encoding="utf-8",
        )
        code, output = self.run_flow("handoff", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertIn("not ready or not confirmed", output)
        self.assertNotIn("plan is confirmed", output)
        code, output = self.run_flow("handoff", ITEM_ID, "--batch", "B2")
        self.assertEqual(code, 2)
        self.assertIn("marked ready but invalid", output)

    def test_missing_progress_row_is_surfaced(self) -> None:
        path = self.directory / "item.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "| B2 | pending | — | — |", ""
            ),
            encoding="utf-8",
        )
        code, output = self.run_flow("handoff", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertIn("design defines B2", output)

    def test_chinese_project_gets_chinese_instructions(self) -> None:
        self.write("docs/flow/profile.toml", PROFILE.format(language="zh"))
        code, output = self.run_flow("handoff", ITEM_ID)
        self.assertEqual(code, 0)
        self.assertIn("继续本仓库的工作项", output)
        self.assertIn("批次：B1 完成, B2 待开始", output)
        self.assertIn("下一步：B2 — route", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
