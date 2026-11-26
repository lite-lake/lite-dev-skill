import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import flow  # noqa: E402
from flowlib import artifacts, checks, commands  # noqa: E402
from flowlib import profile as profile_mod  # noqa: E402

ITEM_ID = "20260101-REQ-k7m2p"

PROFILE = """\
[project]
name = "test-project"
language = "en"
docs_dir = "docs"
work_dir = "docs/work"

[flow]
requires = ">=0.3,<0.4"

[id]
format = "{date}-{type}-{rand}"

[gate]
l1 = ["test"]
l2 = ["test", "lint"]
l3 = ["test", "lint", "e2e"]

[design]
required_for = ["L"]
require_confirmed = true

[commands]
test = "echo ok"
lint = "echo lint"
e2e = "echo e2e"

[docs]
required = ["README.md", "AGENTS.md", "docs/README.md"]
"""

ITEM = """\
---
id: {item_id}
title: {title}
type: REQ
priority: P2
size: {size}
mode: two-phase
owner: {owner}
created: 2026-01-01
closed: {closed}
---

## Problem

- Context: demo

## Clarify

- Status: {clarify}
- Questions: none
- Confirmed assumptions: none

## Scope

- In: demo
- Out: none

## AC

{ac}

## Implementation

| Batch | Status | Commit | Notes |
|---|---|---|---|
| B1 | pending | — | — |

## Notes

- Rollback: revert
"""

DESIGN = """\
---
item: {item_id}
status: draft
---

# {item_id} design

## Handoff

- Goal: demo goal
- Scope: one module
- Out: nothing else
- Verify: unit tests
- Rollback: revert the commit

## Diagram

```text
client -> handler -> store
```

## Confirmation

- Confirmed: yes
- Date: 2026-01-01
- Source: conversation

## Approach

Add the handler and one test.

## Batches

| Batch | Goal | Repo | AC | Depends |
|---|---|---|---|---|
| B1 | add handler | . | {ac_cell} | — |

## Impact

- Contracts: none
- Data / schema: none
- Permissions: none

## Verification

| AC | Command | Environment | Evidence |
|---|---|---|---|
| AC01 | python3 -m unittest | local | test output |

## Rollback

Revert the single commit.

## Open Decisions

None
"""


class BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.profile_path = self.root / "docs/flow/profile.toml"
        self._write(self.profile_path, PROFILE)
        for relative in ("README.md", "AGENTS.md", "docs/README.md"):
            self._write(self.root / relative, "# doc\n")
        self.profile = profile_mod.load(self.profile_path)
        self._env = mock.patch.dict(
            os.environ,
            {
                "LITE_DEV_OWNER": "alice",
                # Keep a developer's global git identity out of the fixture.
                "GIT_CONFIG_GLOBAL": str(self.root / "no-global-gitconfig"),
                "GIT_CONFIG_NOSYSTEM": "1",
            },
        )
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def make_item(
        self,
        clarify: str = "clarified",
        ac: str = "- [ ] AC01 works",
        closed: str = "",
        item_id: str = ITEM_ID,
        owner: str = "alice",
        title: str = "Demo item",
        size: str = "L",
    ):
        directory = self.root / f"docs/work/{item_id}-demo"
        self._write(
            directory / "item.md",
            ITEM.format(
                clarify=clarify,
                ac=ac,
                closed=closed,
                item_id=item_id,
                owner=owner,
                title=title,
                size=size,
            ),
        )
        return artifacts.load_item(directory)

    def write_design(self, text: str | None = None, ac_cell: str = "AC01", item_id: str = ITEM_ID):
        directory = self.root / f"docs/work/{item_id}-demo"
        self._write(
            directory / "design.md",
            text or DESIGN.format(ac_cell=ac_cell, item_id=item_id),
        )
        return artifacts.load_item(directory)

    def run_flow(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = flow.main(["--profile", str(self.profile_path), *args])
        return code, output.getvalue()


class ProfileTest(BaseCase):
    def test_profile_loads(self) -> None:
        self.assertEqual(self.profile.name, "test-project")
        self.assertEqual(self.profile.work_path, self.root / "docs/work")
        self.assertEqual(self.profile.gate["l1"], ["test"])

    def test_incomplete_profile_is_rejected(self) -> None:
        self._write(self.profile_path, '[project]\nname = "x"\n')
        with self.assertRaises(profile_mod.ProfileError):
            profile_mod.load(self.profile_path)

    def test_empty_command_is_rejected(self) -> None:
        self._write(self.profile_path, PROFILE.replace('test = "echo ok"', 'test = ""'))
        with self.assertRaises(profile_mod.ProfileError):
            profile_mod.load(self.profile_path)

    def test_id_format_requires_a_random_token(self) -> None:
        self._write(
            self.profile_path,
            PROFILE.replace('format = "{date}-{type}-{rand}"', 'format = "{date}-{type}-{seq:02d}"'),
        )
        with self.assertRaises(profile_mod.ProfileError) as raised:
            profile_mod.load(self.profile_path)
        self.assertIn("must contain", str(raised.exception))

    def test_release_mainline_is_required_with_channels(self) -> None:
        self._write(
            self.profile_path,
            PROFILE + '\n[release]\nchannels = ["staging"]\n',
        )
        with self.assertRaises(profile_mod.ProfileError) as raised:
            profile_mod.load(self.profile_path)
        self.assertIn("mainline", str(raised.exception))

    def test_flow_requires_pins_the_version(self) -> None:
        self._write(
            self.profile_path,
            PROFILE.replace('requires = ">=0.3,<0.4"', 'requires = ">=9,<10"'),
        )
        with self.assertRaises(profile_mod.ProfileError) as raised:
            profile_mod.load(self.profile_path)
        self.assertIn("requires lite-dev", str(raised.exception))

    def test_flow_table_is_required(self) -> None:
        self._write(
            self.profile_path,
            PROFILE.replace('[flow]\nrequires = ">=0.3,<0.4"\n\n', ""),
        )
        with self.assertRaises(profile_mod.ProfileError) as raised:
            profile_mod.load(self.profile_path)
        self.assertIn("[flow] table is required", str(raised.exception))


class NewTest(BaseCase):
    def test_new_allocates_id_and_renders_template(self) -> None:
        code, output = self.run_flow(
            "new", "--title", "Fix Login Bug", "--type", "BUG", "--size", "S"
        )
        self.assertEqual(code, 0, output)
        self.assertIn("created", output)
        directories = [path for path in (self.root / "docs/work").iterdir() if path.is_dir()]
        self.assertEqual(len(directories), 1)
        item = artifacts.load_item(directories[0])
        self.assertIsNotNone(self.profile.id_pattern.search(item.id))
        self.assertIn("BUG", item.id)
        self.assertEqual(item.meta["title"], "Fix Login Bug")
        self.assertEqual(item.meta["mode"], "one-shot")
        self.assertEqual(item.meta["owner"], "alice")
        self.assertEqual(item.ac_total, 2)

    def test_ids_are_unique_for_identical_input(self) -> None:
        for _ in range(5):
            code, output = self.run_flow("new", "--title", "Same Title", "--type", "REQ")
            self.assertEqual(code, 0, output)
        ids = [artifacts.load_item(path).id for path in (self.root / "docs/work").iterdir() if path.is_dir()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_new_requires_identity(self) -> None:
        with mock.patch.dict(os.environ, {"LITE_DEV_OWNER": ""}):
            code, output = self.run_flow("new", "--title", "No identity")
        self.assertEqual(code, 2)
        self.assertIn("no identity", output)
        work = self.root / "docs/work"
        directories = [path for path in work.iterdir() if path.is_dir()] if work.is_dir() else []
        self.assertEqual(directories, [])

    def test_new_accepts_an_explicit_owner(self) -> None:
        code, output = self.run_flow("new", "--title", "Owned", "--owner", "bob")
        self.assertEqual(code, 0, output)
        directory = [path for path in (self.root / "docs/work").iterdir() if path.is_dir()][0]
        self.assertEqual(artifacts.load_item(directory).meta["owner"], "bob")


class StatusTest(BaseCase):
    def test_derived_transitions(self) -> None:
        item = self.make_item(clarify="pending")
        self.assertEqual(item.status, "need-clarify")

        item = self.make_item(clarify="clarified")
        self.assertEqual(item.status, "clarified")

        item = self.write_design()
        self.assertEqual(item.status, "designing")

        artifacts.set_frontmatter_value(item.design_path, "status", "ready")
        self.assertEqual(artifacts.load_item(item.directory).status, "ready")

        artifacts.set_frontmatter_value(item.path, "closed", "2026-01-02")
        self.assertEqual(artifacts.load_item(item.directory).status, "done")


class CheckTest(BaseCase):
    def test_broken_link_is_an_error(self) -> None:
        self.make_item(ac="- [ ] AC01 works\n\nSee [missing](nope.md).")
        errors, _ = checks.check_project(self.profile)
        self.assertTrue(any("broken link nope.md" in error for error in errors))

    def test_unclarified_item_with_design_is_an_error(self) -> None:
        self.make_item(clarify="pending")
        self.write_design()
        errors, _ = checks.check_project(self.profile)
        self.assertTrue(any("not clarified" in error for error in errors))

    def test_required_document_missing_is_an_error(self) -> None:
        (self.root / "AGENTS.md").unlink()
        errors, _ = checks.check_project(self.profile)
        self.assertTrue(any("AGENTS.md" in error for error in errors))


class DesignTest(BaseCase):
    def test_valid_design_passes(self) -> None:
        self.make_item()
        item = self.write_design()
        self.assertEqual(checks.design_errors(item, self.profile), [])

    def test_batch_must_cover_every_ac(self) -> None:
        self.make_item(ac="- [ ] AC01 works\n- [ ] AC02 also works")
        item = self.write_design(ac_cell="AC01")
        errors = checks.design_errors(item, self.profile)
        self.assertTrue(any("AC02 is not covered" in error for error in errors))

    def test_unconfirmed_plan_fails(self) -> None:
        self.make_item()
        text = DESIGN.format(ac_cell="AC01", item_id=ITEM_ID).replace("Confirmed: yes", "Confirmed: no")
        errors = checks.design_errors(self.write_design(text), self.profile)
        self.assertTrue(any("Confirmed: yes" in error for error in errors))

    def test_tbd_fails(self) -> None:
        self.make_item()
        text = DESIGN.format(ac_cell="AC01", item_id=ITEM_ID).replace("Add the handler and one test.", "TBD")
        errors = checks.design_errors(self.write_design(text), self.profile)
        self.assertTrue(any("TBD" in error for error in errors))

    def test_empty_rollback_fails(self) -> None:
        self.make_item()
        text = DESIGN.format(ac_cell="AC01", item_id=ITEM_ID).replace("Revert the single commit.", "")
        errors = checks.design_errors(self.write_design(text), self.profile)
        self.assertTrue(any("Rollback" in error for error in errors))

    def test_placeholder_ac_fails(self) -> None:
        self.make_item(ac="- [ ] AC01 <observable outcome>")
        item = self.write_design()
        errors = checks.design_errors(item, self.profile)
        self.assertTrue(any("AC01 has no concrete description" in error for error in errors))

    def test_design_ready_marks_ready(self) -> None:
        self.make_item()
        self.write_design()
        code, output = self.run_flow("design-ready", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertEqual(artifacts.find_item(self.profile, ITEM_ID).design_status, "ready")


class GateTest(BaseCase):
    def test_gate_passes(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(commands.run_gate(self.profile, "l1"), 0)

    def test_gate_fails_on_command_exit(self) -> None:
        self.profile.commands["test"] = "exit 1"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(commands.run_gate(self.profile, "l1"), 1)

    def test_unknown_level_is_an_error(self) -> None:
        with self.assertRaises(profile_mod.ProfileError):
            with contextlib.redirect_stdout(io.StringIO()):
                commands.run_gate(self.profile, "l9")

    def test_gate_requires_ready_design_for_l(self) -> None:
        self.make_item(ac="- [x] AC01 works")
        code, output = self.run_flow("gate", "--level", "l1", "--work", ITEM_ID)
        self.assertEqual(code, 1)
        self.assertIn("needs a ready design", output)


class DoneTest(BaseCase):
    def test_done_refuses_unchecked_ac(self) -> None:
        self.make_item(ac="- [ ] AC01 works")
        code, output = self.run_flow("done", ITEM_ID)
        self.assertEqual(code, 1)
        self.assertIn("unchecked AC", output)

    def test_done_requires_ready_design_for_l(self) -> None:
        self.make_item(ac="- [x] AC01 works")
        code, output = self.run_flow("done", ITEM_ID)
        self.assertEqual(code, 1)
        self.assertIn("ready design", output)

    def test_done_after_design_ready(self) -> None:
        self.make_item(ac="- [x] AC01 works")
        self.write_design()
        code, output = self.run_flow("design-ready", ITEM_ID)
        self.assertEqual(code, 0, output)
        code, output = self.run_flow("done", ITEM_ID)
        self.assertEqual(code, 0, output)
        item = artifacts.find_item(self.profile, ITEM_ID)
        self.assertTrue(item.meta["closed"])
        self.assertEqual(item.status, "done")

    def test_done_writes_lf_endings(self) -> None:
        item = self.make_item(ac="- [x] AC01 works", size="S")
        code, output = self.run_flow("done", item.id)
        self.assertEqual(code, 0, output)
        data = item.path.read_bytes()
        self.assertNotIn(b"\r\n", data)


class IdentityTest(BaseCase):
    def test_claim_reassigns_the_owner(self) -> None:
        item = self.make_item()
        code, output = self.run_flow("claim", item.id, "--owner", "bob")
        self.assertEqual(code, 0, output)
        self.assertIn("alice -> bob", output)
        self.assertEqual(artifacts.find_item(self.profile, item.id).meta["owner"], "bob")

    def test_status_mine_filters_by_identity(self) -> None:
        self.make_item(item_id="20260101-REQ-aaaaa", owner="alice")
        self.make_item(item_id="20260101-REQ-bbbbb", owner="bob")
        code, output = self.run_flow("status", "--mine")
        self.assertEqual(code, 0)
        self.assertIn("20260101-REQ-aaaaa", output)
        self.assertNotIn("20260101-REQ-bbbbb", output)
        with mock.patch.dict(os.environ, {"LITE_DEV_OWNER": "bob"}):
            code, output = self.run_flow("status", "--mine")
        self.assertIn("20260101-REQ-bbbbb", output)


class TargetingTest(BaseCase):
    def test_ambiguous_prefix_is_an_error(self) -> None:
        self.make_item(item_id="20260101-REQ-aaaaa")
        self.make_item(item_id="20260101-REQ-aaaab")
        code, output = self.run_flow("done", "20260101-REQ-aaaa")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", output)
        self.assertIn("20260101-REQ-aaaaa", output)
        self.assertIn("20260101-REQ-aaaab", output)

    def test_unique_prefix_resolves(self) -> None:
        self.make_item(item_id="20260101-REQ-aaaaa", ac="- [x] AC01 works", size="S")
        code, output = self.run_flow("done", "20260101-REQ-aaaa")
        self.assertEqual(code, 0, output)

    def test_id_must_match_the_format(self) -> None:
        self.make_item(item_id="20260101-REQ-01")
        errors, _ = checks.check_project(self.profile)
        self.assertTrue(any("does not match [id] format" in error for error in errors))


class CheckScopeTest(BaseCase):
    def test_gate_work_ignores_another_broken_item(self) -> None:
        good = self.make_item(item_id="20260101-REQ-aaaaa", size="S")
        broken = self.make_item(item_id="20260101-REQ-bbbbb", owner="")
        self.assertTrue(broken.meta.get("owner", "") == "")

        code, output = self.run_flow("gate", "--level", "l1", "--work", good.id)
        self.assertEqual(code, 0, output)

        code, output = self.run_flow("check")
        self.assertEqual(code, 1)
        self.assertIn("missing frontmatter field 'owner'", output)

    def test_check_work_validates_only_the_named_item(self) -> None:
        self.make_item(item_id="20260101-REQ-aaaaa", size="S")
        self.make_item(item_id="20260101-REQ-bbbbb", owner="")
        code, output = self.run_flow("check", "--work", "20260101-REQ-aaaaa")
        self.assertEqual(code, 0, output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
