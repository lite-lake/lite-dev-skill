import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import flow  # noqa: E402
from flowlib import artifacts, checks, commands  # noqa: E402
from flowlib import profile as profile_mod  # noqa: E402

ITEM_ID = "20260101-REQ-k7m2pa"

PROFILE = """\
[project]
name = "test-project"
language = "en"
docs_dir = "docs"
work_dir = "docs/work"

[flow]
requires = ">=0.5.0,<0.6"

[id]
format = "{date}-{type}-{time}"

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

REPORT = """\
---
item: {item_id}
batch: B1
---

## Scope

- Batch: B1
- What was verified: the AC

## Result

- Verdict: {verdict}
- Reason: ran the tests

## Evidence

| AC | Command | Output / artefact |
|---|---|---|
{rows}

## Defects

- None
"""


class BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        # Resolve once: on macOS /var is a symlink to /private/var and
        # profile.load() resolves the same way.
        self.root = Path(self._tmp.name).resolve()
        self.profile_path = self.root / "docs/flow/profile.toml"
        self._write(self.profile_path, PROFILE)
        for relative in ("README.md", "AGENTS.md", "docs/README.md"):
            self._write(self.root / relative, "# doc\n")
        # The gate ledger lives in .git; a repo (even without a commit) is what
        # makes a gate PASS available to `done`.
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
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
        # Each test starts from a fresh allocator, so a mocked clock is not
        # pushed forward by a previous test in the same process.
        flow._CLOCK = flow.stamp.Clock()

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
        bucket: str = "2026-01",
        slug: str = "demo",
    ):
        directory = self.root / f"docs/work/{bucket}/{item_id}-{slug}"
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

    def write_design(
        self,
        text: str | None = None,
        ac_cell: str = "AC01",
        item_id: str = ITEM_ID,
        bucket: str = "2026-01",
    ):
        directory = self.root / f"docs/work/{bucket}/{item_id}-demo"
        self._write(
            directory / "design.md",
            text or DESIGN.format(ac_cell=ac_cell, item_id=item_id),
        )
        return artifacts.load_item(directory)

    def write_report(
        self,
        rows: str = "| AC01 | python3 -m unittest | OK |",
        verdict: str = "PASS",
        item_id: str = ITEM_ID,
        bucket: str = "2026-01",
        slug: str = "demo",
    ) -> Path:
        path = self.root / f"docs/work/{bucket}/{item_id}-{slug}/test-report.md"
        self._write(
            path,
            REPORT.format(item_id=item_id, verdict=verdict, rows=rows),
        )
        return path

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

    def test_unknown_gate_level_is_rejected(self) -> None:
        self._write(
            self.profile_path,
            PROFILE.replace('l1 = ["test"]', 'l1 = ["test"]\nl4 = ["test"]'),
        )
        with self.assertRaises(profile_mod.ProfileError) as caught:
            profile_mod.load(self.profile_path)
        self.assertIn("unknown key", str(caught.exception))

    def test_id_format_requires_a_time_token(self) -> None:
        self._write(
            self.profile_path,
            PROFILE.replace('format = "{date}-{type}-{time}"', 'format = "{date}-{type}-{seq:02d}"'),
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
            PROFILE.replace('requires = ">=0.5.0,<0.6"', 'requires = ">=9,<10"'),
        )
        with self.assertRaises(profile_mod.ProfileError) as raised:
            profile_mod.load(self.profile_path)
        self.assertIn("requires lite-dev", str(raised.exception))

    def test_flow_table_is_required(self) -> None:
        self._write(
            self.profile_path,
            PROFILE.replace('[flow]\nrequires = ">=0.5.0,<0.6"\n\n', ""),
        )
        with self.assertRaises(profile_mod.ProfileError) as raised:
            profile_mod.load(self.profile_path)
        self.assertIn("[flow] table is required", str(raised.exception))


class StampTest(unittest.TestCase):
    """The time code in an id: fixed width, sortable, bounded to one day."""

    def test_code_is_fixed_width_and_zero_padded(self) -> None:
        zero = profile_mod.TIME_ALPHABET[0] * profile_mod.TIME_LEN
        self.assertEqual(flow.stamp.encode(0), zero)
        for ms in (0, 1, 999, 12_345_678, flow.stamp.MS_PER_DAY - 1):
            self.assertEqual(len(flow.stamp.encode(ms)), profile_mod.TIME_LEN)

    def test_codes_sort_in_time_order(self) -> None:
        samples = [0, 1, 1_000, 61_001, 3_600_000, flow.stamp.MS_PER_DAY - 1]
        codes = [flow.stamp.encode(ms) for ms in samples]
        self.assertEqual(codes, sorted(codes))

    def test_out_of_range_is_rejected(self) -> None:
        for ms in (-1, flow.stamp.MS_PER_DAY):
            with self.assertRaises(ValueError):
                flow.stamp.encode(ms)

    def test_every_character_comes_from_the_profile_alphabet(self) -> None:
        for ms in (0, 7, 61_001, 12_345_678, flow.stamp.MS_PER_DAY - 1):
            code = flow.stamp.encode(ms)
            self.assertTrue(set(code) <= set(profile_mod.TIME_ALPHABET), code)
            self.assertEqual(len(code), profile_mod.TIME_LEN)

    def test_clock_never_hands_out_the_same_code(self) -> None:
        clock = flow.stamp.Clock()
        moment = datetime(2026, 1, 1, 6, 0, 0)
        first = clock.allocate("2026-01-01", moment)
        clock.commit("2026-01-01", first)
        self.assertEqual(clock.allocate("2026-01-01", moment), first + 1)
        self.assertEqual(clock.allocate("2026-01-02", moment), first)


class SlugTest(unittest.TestCase):
    """The slug follows the title's script, not the project's language."""

    def test_chinese_title_keeps_its_characters(self) -> None:
        self.assertEqual(flow._slugify("修复登录超时"), "修复登录超时")

    def test_english_title_joins_words_with_dashes(self) -> None:
        self.assertEqual(flow._slugify("Fix Login Bug"), "Fix-Login-Bug")

    def test_mixed_title_keeps_both_scripts(self) -> None:
        self.assertEqual(flow._slugify("修复 login 超时"), "修复-login-超时")

    def test_chinese_slug_caps_at_thirty_characters(self) -> None:
        self.assertEqual(len(flow._slugify("修复" * 20)), artifacts.SLUG_WIDE_MAX)

    def test_english_slug_keeps_the_thirty_two_character_cap(self) -> None:
        self.assertEqual(len(flow._slugify("word " * 20)), artifacts.SLUG_ASCII_MAX)

    def test_a_cut_never_leaves_a_trailing_dash(self) -> None:
        # 29 Chinese characters then a space: the cut lands right after the dash.
        slug = flow._slugify("修" * 29 + " x")
        self.assertEqual(len(slug), artifacts.SLUG_WIDE_MAX - 1)
        self.assertFalse(slug.endswith("-"))

    def test_punctuation_only_title_has_no_slug(self) -> None:
        self.assertEqual(flow._slugify("!!! ???"), "")


class NewTest(BaseCase):
    def test_new_allocates_id_and_renders_template(self) -> None:
        code, output = self.run_flow(
            "new", "--title", "Fix Login Bug", "--type", "BUG", "--size", "S"
        )
        self.assertEqual(code, 0, output)
        self.assertIn("created", output)
        items = artifacts.all_items(self.profile)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertIsNotNone(self.profile.id_pattern.search(item.id))
        self.assertIn("BUG", item.id)
        self.assertEqual(item.meta["title"], "Fix Login Bug")
        self.assertEqual(item.meta["mode"], "one-shot")
        self.assertEqual(item.meta["owner"], "alice")
        self.assertEqual(item.ac_total, 2)

    def test_new_files_the_item_under_its_month(self) -> None:
        moment = datetime(2026, 3, 4, 9, 30, 15, 123_000)
        with mock.patch.object(flow.stamp, "now", return_value=moment):
            code, output = self.run_flow("new", "--title", "March", "--type", "REQ", "--size", "S")
        self.assertEqual(code, 0, output)
        item_id = output.split()[1]
        bucket = self.root / "docs/work/2026-03"
        self.assertTrue(bucket.is_dir(), bucket)
        self.assertEqual([p.name for p in bucket.iterdir()], [f"{item_id}-March"])

    def test_new_keeps_a_chinese_title_in_the_directory(self) -> None:
        code, output = self.run_flow(
            "new", "--title", "修复登录超时", "--type", "BUG", "--size", "S"
        )
        self.assertEqual(code, 0, output)
        item = artifacts.all_items(self.profile)[0]
        self.assertTrue(item.directory.name.endswith("-修复登录超时"), item.directory.name)
        self.assertEqual(item.meta["title"], "修复登录超时")

    def test_ids_are_unique_for_identical_input(self) -> None:
        for _ in range(5):
            code, output = self.run_flow("new", "--title", "Same Title", "--type", "REQ")
            self.assertEqual(code, 0, output)
        ids = [item.id for item in artifacts.all_items(self.profile)]
        self.assertEqual(len(ids), 5)
        self.assertEqual(len(ids), len(set(ids)))

    def test_new_requires_identity(self) -> None:
        with mock.patch.dict(os.environ, {"LITE_DEV_OWNER": ""}):
            code, output = self.run_flow("new", "--title", "No identity")
        self.assertEqual(code, 2)
        self.assertIn("no identity", output)
        self.assertFalse((self.root / "docs/work").exists())

    def test_new_accepts_an_explicit_owner(self) -> None:
        code, output = self.run_flow("new", "--title", "Owned", "--owner", "bob")
        self.assertEqual(code, 0, output)
        self.assertEqual(artifacts.all_items(self.profile)[0].meta["owner"], "bob")


class IdStampTest(BaseCase):
    """`new` derives the date and the time code from one clock read."""

    def test_id_encodes_the_millisecond_of_the_local_day(self) -> None:
        moment = datetime(2026, 3, 4, 9, 30, 15, 123_000)
        with mock.patch.object(flow.stamp, "now", return_value=moment):
            code, output = self.run_flow(
                "new", "--title", "Clock", "--type", "REQ", "--size", "S"
            )
        self.assertEqual(code, 0, output)
        ms = flow.stamp.ms_since_midnight(moment)
        self.assertIn(f"created 20260304-REQ-{flow.stamp.encode(ms)}", output)

    def test_same_millisecond_gets_the_next_code(self) -> None:
        moment = datetime(2026, 3, 4, 9, 30, 15, 123_000)
        ms = flow.stamp.ms_since_midnight(moment)
        ids = []
        with mock.patch.object(flow.stamp, "now", return_value=moment):
            for _ in range(2):
                code, output = self.run_flow(
                    "new", "--title", "Twin", "--type", "REQ", "--size", "S"
                )
                self.assertEqual(code, 0, output)
                ids.append(output.split()[1])
        self.assertEqual(ids[0], f"20260304-REQ-{flow.stamp.encode(ms)}")
        self.assertEqual(ids[1], f"20260304-REQ-{flow.stamp.encode(ms + 1)}")

    def test_generated_id_matches_the_profile_pattern(self) -> None:
        for ms in (0, 61_001, flow.stamp.MS_PER_DAY - 1):
            item_id = f"20261126-REQ-{flow.stamp.encode(ms)}"
            match = self.profile.id_pattern.search(item_id)
            self.assertIsNotNone(match, item_id)
            self.assertEqual(match.group(0), item_id)

    def test_last_millisecond_stays_in_the_same_day(self) -> None:
        moment = datetime(2026, 12, 31, 23, 59, 59, 999_000)
        with mock.patch.object(flow.stamp, "now", return_value=moment):
            code, output = self.run_flow(
                "new", "--title", "Midnight", "--type", "REQ", "--size", "S"
            )
        self.assertEqual(code, 0, output)
        last = flow.stamp.encode(flow.stamp.MS_PER_DAY - 1)
        self.assertIn(f"created 20261231-REQ-{last}", output)


class LayoutTest(BaseCase):
    """Items live at <work_dir>/<YYYY-MM>/<id>-<slug>; a wrong bucket is loud."""

    def test_item_outside_its_month_is_an_error(self) -> None:
        self.make_item(bucket="2026-02")
        errors, _ = checks.check_project(self.profile)
        self.assertTrue(
            any("month directory must be 2026-01" in error for error in errors), errors
        )

    def test_flat_item_directory_is_reported(self) -> None:
        # A pre-month item: it must not disappear from `check` silently.
        self._write(self.root / "docs/work/20260101-REQ-aaaaaa-demo/item.md", "---\n---\n")
        errors, _ = checks.check_project(self.profile)
        self.assertTrue(any("items live in" in error for error in errors), errors)

    def test_stray_directory_in_a_month_warns(self) -> None:
        (self.root / "docs/work/2026-01/empty").mkdir(parents=True)
        errors, warnings = checks.check_project(self.profile)
        self.assertFalse([error for error in errors if "empty" in error], errors)
        self.assertTrue(
            any("2026-01/empty: no item.md" in warning for warning in warnings), warnings
        )

    def test_long_chinese_slug_warns_but_does_not_block(self) -> None:
        title = "支付回调重试时出现重复扣款并且用户余额显示不一致的问题排查"
        self.make_item(slug=flow._slugify(title), title=title, size="S")
        errors, warnings = checks.check_project(self.profile)
        self.assertFalse([error for error in errors if "slug" in error], errors)
        self.assertTrue(
            any("keep Chinese titles within 20" in warning for warning in warnings), warnings
        )

    def test_find_item_resolves_an_id_inside_a_month(self) -> None:
        item = self.make_item(size="S")
        self.assertEqual(artifacts.find_item(self.profile, item.id).id, item.id)
        self.assertEqual(artifacts.find_item(self.profile, "20260101-REQ").id, item.id)


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

    def _git(self, *args: str, env: dict | None = None) -> None:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def _commit_all(self, when: str) -> None:
        self._git("add", "-A")
        env = dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
        self._git(
            "-c", "user.name=Test", "-c", "user.email=t@example.com",
            "-c", "commit.gpgsign=false", "commit", "-qm", "init", env=env,
        )

    def test_stale_lists_open_items_untouched_for_days(self) -> None:
        item = self.make_item(size="S")
        self._git("init", "-q")
        self._commit_all("2026-01-01T12:00:00")

        code, output = self.run_flow("status", "--stale", "--days", "30")
        self.assertEqual(code, 0, output)
        self.assertIn("stale open items (>30 days", output)
        self.assertIn(item.id, output)
        self.assertIn("2026-01-01", output)

        code, output = self.run_flow("status", "--stale", "--days", "10000")
        self.assertEqual(code, 0, output)
        self.assertIn("stale: none older than 10000 days", output)

    def test_status_does_not_warn_about_the_gate_before_an_item_is_ready(self) -> None:
        self.make_item()
        code, output = self.run_flow("status")
        self.assertEqual(code, 0, output)
        self.assertNotIn("has no PASS recorded", output)

        self.write_design()
        self.assertEqual(self.run_flow("design-ready", ITEM_ID)[0], 0)
        code, output = self.run_flow("status")
        self.assertIn("has no PASS recorded", output)

    def test_status_shows_required_and_invalid_designs(self) -> None:
        self._write(
            self.profile_path,
            PROFILE.replace('required_for = ["L"]', 'required_for = ["L", "M"]'),
        )
        self.make_item(item_id="20260101-REQ-aaaaaa", size="M")
        code, output = self.run_flow("status")
        self.assertEqual(code, 0, output)
        self.assertIn("required", output)

        item = self.make_item(item_id="20260101-REQ-bbbbbb", size="M")
        self.write_design(
            text=DESIGN.format(ac_cell="AC01", item_id=item.id), item_id=item.id
        )
        design = item.directory / "design.md"
        design.write_text(
            design.read_text(encoding="utf-8").replace("status: draft", "status: ready"),
            encoding="utf-8",
        )
        design.write_text(
            design.read_text(encoding="utf-8").replace("## Handoff", "## 交接摘要"),
            encoding="utf-8",
        )
        code, output = self.run_flow("status")
        self.assertIn("ready!", output)
        self.assertIn("marked ready but invalid", output)

    def test_stale_json_carries_the_report(self) -> None:
        item = self.make_item(size="S")
        self._git("init", "-q")
        self._commit_all("2026-01-01T12:00:00")

        code, output = self.run_flow("status", "--stale", "--days", "30", "--json")
        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        self.assertEqual(payload["stale"]["days"], 30)
        self.assertEqual([row["id"] for row in payload["stale"]["items"]], [item.id])
        self.assertGreater(payload["stale"]["items"][0]["days"], 30)


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

    def test_translated_heading_is_named_in_the_error(self) -> None:
        self.make_item()
        text = DESIGN.format(ac_cell="AC01", item_id=ITEM_ID).replace(
            "## Handoff", "## 交接摘要"
        )
        item = self.write_design(text=text)
        errors = checks.design_errors(item, self.profile)
        self.assertTrue(
            any("the parsed heading must stay '## Handoff'" in error for error in errors),
            errors,
        )

    def test_design_ready_refuses_a_wrong_item_frontmatter(self) -> None:
        self.make_item()
        self.write_design(text=DESIGN.format(ac_cell="AC01", item_id="WRONG-ID"))
        code, output = self.run_flow("design-ready", ITEM_ID)
        self.assertEqual(code, 1)
        self.assertIn("frontmatter 'item'", output)

    def test_forward_batch_dependency_is_refused(self) -> None:
        self.make_item()
        text = DESIGN.format(ac_cell="AC01", item_id=ITEM_ID).replace(
            "| B1 | add handler | . | AC01 | — |",
            "| B1 | one | . | AC01 | B2 |\n| B2 | two | . | AC01 | — |",
        )
        item = self.write_design(text=text)
        errors = checks.design_errors(item, self.profile)
        self.assertTrue(
            any("not an earlier batch" in error for error in errors), errors
        )

    def test_batch_cycle_is_refused(self) -> None:
        self.make_item()
        text = DESIGN.format(ac_cell="AC01", item_id=ITEM_ID).replace(
            "| B1 | add handler | . | AC01 | — |",
            "| B1 | one | . | AC01 | B2 |\n| B2 | two | . | AC01 | B1 |",
        )
        item = self.write_design(text=text)
        errors = checks.design_errors(item, self.profile)
        self.assertTrue(any("not an earlier batch" in error for error in errors), errors)

    def test_non_contiguous_batches_are_refused(self) -> None:
        self.make_item()
        text = DESIGN.format(ac_cell="AC01", item_id=ITEM_ID).replace(
            "| B1 | add handler | . | AC01 | — |",
            "| B1 | one | . | AC01 | — |\n| B3 | three | . | AC01 | B1 |",
        )
        item = self.write_design(text=text)
        errors = checks.design_errors(item, self.profile)
        self.assertTrue(any("B1..Bn in order" in error for error in errors), errors)


class DesignCommandTest(BaseCase):
    def test_design_scaffolds_from_the_template(self) -> None:
        item = self.make_item(size="L")
        code, output = self.run_flow("design", item.id)
        self.assertEqual(code, 0, output)
        text = (item.directory / "design.md").read_text(encoding="utf-8")
        self.assertIn(f"item: {item.id}", text)
        self.assertIn("status: draft", text)
        again = self.run_flow("design", item.id)
        self.assertEqual(again[0], 2)
        self.assertIn("already has design.md", again[1])

    def test_design_refuses_an_unclarified_item(self) -> None:
        item = self.make_item(size="L", clarify="pending")
        code, output = self.run_flow("design", item.id)
        self.assertEqual(code, 2)
        self.assertIn("not clarified", output)


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

    def test_gate_requires_a_design_for_m_when_the_profile_says_so(self) -> None:
        self._write(
            self.profile_path,
            PROFILE.replace('required_for = ["L"]', 'required_for = ["L", "M"]'),
        )
        self.make_item(ac="- [x] AC01 works", size="M")
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
        self.write_report()
        gate = self.run_flow("gate", "--level", "l3", "--work", ITEM_ID)
        self.assertEqual(gate[0], 0, gate[1])
        code, output = self.run_flow("done", ITEM_ID)
        self.assertEqual(code, 0, output)
        item = artifacts.find_item(self.profile, ITEM_ID)
        self.assertTrue(item.meta["closed"])
        self.assertEqual(item.status, "done")
        self.assertIn("test-report.md", item.path.read_text(encoding="utf-8"))

    def test_done_refuses_a_designed_item_without_a_report(self) -> None:
        self.make_item(ac="- [x] AC01 works")
        self.write_design()
        self.assertEqual(self.run_flow("design-ready", ITEM_ID)[0], 0)
        code, output = self.run_flow("done", ITEM_ID)
        self.assertEqual(code, 1)
        self.assertIn("requires test-report.md", output)

    def test_done_refuses_a_failing_verdict(self) -> None:
        self.make_item(ac="- [x] AC01 works")
        self.write_design()
        self.assertEqual(self.run_flow("design-ready", ITEM_ID)[0], 0)
        self.write_report(verdict="FAIL")
        code, output = self.run_flow("done", ITEM_ID)
        self.assertEqual(code, 1)
        self.assertIn("verdict is 'FAIL'", output)

    def test_done_refuses_a_missing_evidence_row(self) -> None:
        self.make_item(ac="- [x] AC01 works\n- [x] AC02 works")
        design = DESIGN.format(ac_cell="AC01, AC02", item_id=ITEM_ID).replace(
            "| AC01 | python3 -m unittest | local | test output |",
            "| AC01 | python3 -m unittest | local | test output |\n"
            "| AC02 | python3 -m unittest | local | test output |",
        )
        self.write_design(text=design)
        self.assertEqual(self.run_flow("design-ready", ITEM_ID)[0], 0)
        self.write_report(rows="| AC01 | python3 -m unittest | OK |")
        code, output = self.run_flow("done", ITEM_ID)
        self.assertEqual(code, 1)
        self.assertIn("AC02 has no evidence row", output)

    def test_done_refuses_empty_evidence_cells(self) -> None:
        self.make_item(ac="- [x] AC01 works")
        self.write_design()
        self.assertEqual(self.run_flow("design-ready", ITEM_ID)[0], 0)
        self.write_report(rows="| AC01 | python3 -m unittest | |")
        code, output = self.run_flow("done", ITEM_ID)
        self.assertEqual(code, 1)
        self.assertIn("AC01 has no Output evidence", output)

    def test_check_reports_a_partial_report_as_a_warning(self) -> None:
        self.make_item(ac="- [x] AC01 works")
        self.write_design()
        self.assertEqual(self.run_flow("design-ready", ITEM_ID)[0], 0)
        self.write_report(verdict="FAIL")
        code, output = self.run_flow("check")
        self.assertEqual(code, 0, output)
        self.assertIn("verdict is 'FAIL'", output)

    def test_done_requires_a_report_for_an_s_item(self) -> None:
        item = self.make_item(ac="- [x] AC01 works", size="S")
        gate = self.run_flow("gate", "--level", "l3", "--work", item.id)
        self.assertEqual(gate[0], 0, gate[1])
        code, output = self.run_flow("done", item.id)
        self.assertEqual(code, 1)
        self.assertIn("requires test-report.md", output)

    def test_angle_brackets_are_evidence_not_placeholders(self) -> None:
        item = self.make_item(ac="- [x] AC01 works", size="S")
        self.write_report(
            item_id=item.id,
            rows="| AC01 | python3 <skill>/scripts/flow.py status | <ok> |",
        )
        gate = self.run_flow("gate", "--level", "l3", "--work", item.id)
        self.assertEqual(gate[0], 0, gate[1])
        code, output = self.run_flow("done", item.id)
        self.assertEqual(code, 0, output)

    def test_done_requires_a_recorded_gate_pass(self) -> None:
        item = self.make_item(ac="- [x] AC01 works", size="S")
        self.write_report(item_id=item.id)
        code, output = self.run_flow("done", item.id)
        self.assertEqual(code, 1)
        self.assertIn("no l3 PASS recorded", output)
        gate = self.run_flow("gate", "--level", "l3", "--work", item.id)
        self.assertEqual(gate[0], 0, gate[1])
        code, output = self.run_flow("done", item.id)
        self.assertEqual(code, 0, output)

    def test_done_refuses_a_draft_design(self) -> None:
        item = self.make_item(ac="- [x] AC01 works", size="S")
        text = DESIGN.format(ac_cell="AC01", item_id=ITEM_ID).replace(
            "- Confirmed: yes", "- Confirmed: no"
        )
        self.write_design(text=text)
        self.write_report(item_id=item.id)
        gate = self.run_flow("gate", "--level", "l3", "--work", item.id)
        self.assertEqual(gate[0], 0, gate[1])
        code, output = self.run_flow("done", item.id)
        self.assertEqual(code, 1)
        self.assertIn("not ready", output)

    def test_done_refuses_an_archived_item(self) -> None:
        item = self.make_item(ac="- [x] AC01 works", size="S")
        archived = self.run_flow(
            "archive", item.id, "--force", "--reason", "abandoned probe"
        )
        self.assertEqual(archived[0], 0, archived[1])
        code, output = self.run_flow("done", item.id)
        self.assertEqual(code, 2)
        self.assertIn("archived", output)

    def test_done_writes_lf_endings(self) -> None:
        item = self.make_item(ac="- [x] AC01 works", size="S")
        self.write_report(item_id=item.id)
        self.assertEqual(self.run_flow("gate", "--level", "l3", "--work", item.id)[0], 0)
        code, output = self.run_flow("done", item.id)
        self.assertEqual(code, 0, output)
        data = item.path.read_bytes()
        self.assertNotIn(b"\r\n", data)


class IdentityTest(BaseCase):
    def test_claim_refuses_another_persons_active_item(self) -> None:
        item = self.make_item()
        code, output = self.run_flow("claim", item.id, "--owner", "bob")
        self.assertEqual(code, 2)
        self.assertIn("owned by alice", output)
        self.assertIn("--takeover", output)
        self.assertEqual(artifacts.find_item(self.profile, item.id).meta["owner"], "alice")

    def test_claim_reassigns_with_takeover(self) -> None:
        item = self.make_item()
        code, output = self.run_flow(
            "claim", item.id, "--owner", "bob", "--takeover", "--reason", "on-call"
        )
        self.assertEqual(code, 0, output)
        self.assertIn("alice -> bob", output)
        claimed = artifacts.find_item(self.profile, item.id)
        self.assertEqual(claimed.meta["owner"], "bob")
        self.assertEqual(claimed.meta["takeover_reason"], "on-call")

    def test_takeover_without_a_reason_is_refused(self) -> None:
        item = self.make_item()
        code, output = self.run_flow("claim", item.id, "--owner", "bob", "--takeover")
        self.assertEqual(code, 2)
        self.assertIn("--reason", output)
        self.assertEqual(artifacts.find_item(self.profile, item.id).meta["owner"], "alice")

    def test_claim_of_an_unowned_item_needs_no_takeover(self) -> None:
        item = self.make_item(owner="")
        code, output = self.run_flow("claim", item.id, "--owner", "bob")
        self.assertEqual(code, 0, output)
        self.assertIn("unowned -> bob", output)

    def test_claim_of_a_closed_item_is_refused(self) -> None:
        item = self.make_item(owner="alice", closed="2026-01-02", size="S")
        code, output = self.run_flow("claim", item.id, "--owner", "bob")
        self.assertEqual(code, 2)
        self.assertIn("already closed", output)
        self.assertEqual(artifacts.find_item(self.profile, item.id).meta["owner"], "alice")

    def test_whoami_reports_the_source(self) -> None:
        code, output = self.run_flow("whoami")
        self.assertEqual(code, 0, output)
        self.assertIn("identity: alice", output)
        self.assertIn("source:   LITE_DEV_OWNER", output)

    def test_whoami_without_an_identity_explains_how_to_set_one(self) -> None:
        with mock.patch.dict(os.environ, {"LITE_DEV_OWNER": ""}):
            code, output = self.run_flow("whoami")
        self.assertEqual(code, 1)
        self.assertIn("identity: (none)", output)
        self.assertIn("git config --global lite-dev.owner", output)

    def test_done_records_who_closed_and_warns_on_a_different_owner(self) -> None:
        item = self.make_item(ac="- [x] AC01 works", size="S", owner="alice")
        self.write_report(item_id=item.id)
        self.assertEqual(self.run_flow("gate", "--level", "l3", "--work", item.id)[0], 0)
        with mock.patch.dict(os.environ, {"LITE_DEV_OWNER": "bob"}):
            code, output = self.run_flow("done", item.id)
        self.assertEqual(code, 0, output)
        self.assertIn("owned by alice; closing as bob", output)
        closed = artifacts.find_item(self.profile, item.id)
        self.assertEqual(closed.meta["closed_by"], "bob")
        self.assertTrue(closed.meta["closed"])

    def test_done_accepts_an_explicit_owner(self) -> None:
        item = self.make_item(ac="- [x] AC01 works", size="S")
        self.write_report(item_id=item.id)
        self.assertEqual(self.run_flow("gate", "--level", "l3", "--work", item.id)[0], 0)
        code, output = self.run_flow("done", item.id, "--owner", "bob")
        self.assertEqual(code, 0, output)
        self.assertEqual(
            artifacts.find_item(self.profile, item.id).meta["closed_by"], "bob"
        )

    def test_done_without_an_identity_is_refused(self) -> None:
        item = self.make_item(ac="- [x] AC01 works", size="S")
        self.write_report(item_id=item.id)
        self.assertEqual(self.run_flow("gate", "--level", "l3", "--work", item.id)[0], 0)
        with mock.patch.dict(os.environ, {"LITE_DEV_OWNER": ""}):
            code, output = self.run_flow("done", item.id)
        self.assertEqual(code, 2)
        self.assertIn("no identity", output)
        self.assertNotIn("closed_by: bob", artifacts.read_text(item.path))

    def test_status_mine_filters_by_identity(self) -> None:
        self.make_item(item_id="20260101-REQ-aaaaaa", owner="alice")
        self.make_item(item_id="20260101-REQ-bbbbbb", owner="bob")
        code, output = self.run_flow("status", "--mine")
        self.assertEqual(code, 0)
        self.assertIn("20260101-REQ-aaaaaa", output)
        self.assertNotIn("20260101-REQ-bbbbbb", output)
        with mock.patch.dict(os.environ, {"LITE_DEV_OWNER": "bob"}):
            code, output = self.run_flow("status", "--mine")
        self.assertIn("20260101-REQ-bbbbbb", output)


class DropTest(BaseCase):
    def test_drop_marks_dropped_and_records_the_reason(self) -> None:
        item = self.make_item(ac="- [ ] AC01 never delivered", size="S")
        code, output = self.run_flow("drop", item.id, "--reason", "scope cut")
        self.assertEqual(code, 0, output)
        dropped = artifacts.find_item(self.profile, item.id)
        self.assertEqual(dropped.status, "dropped")
        self.assertEqual(dropped.meta["closed"], "dropped")
        self.assertEqual(dropped.meta["closed_by"], "alice")
        self.assertEqual(dropped.meta["drop_reason"], "scope cut")
        check = self.run_flow("check")
        self.assertEqual(check[0], 0, check[1])
        self.assertNotIn("closed but AC", check[1])

    def test_drop_refuses_a_closed_item(self) -> None:
        item = self.make_item(size="S", closed="2026-01-02")
        code, output = self.run_flow("drop", item.id)
        self.assertEqual(code, 2)
        self.assertIn("already closed", output)


class TargetingTest(BaseCase):
    def test_ambiguous_prefix_is_an_error(self) -> None:
        self.make_item(item_id="20260101-REQ-aaaaaa")
        self.make_item(item_id="20260101-REQ-aaaaab")
        code, output = self.run_flow("done", "20260101-REQ-aaaa")
        self.assertEqual(code, 2)
        self.assertIn("ambiguous", output)
        self.assertIn("20260101-REQ-aaaaaa", output)
        self.assertIn("20260101-REQ-aaaaab", output)

    def test_unique_prefix_resolves(self) -> None:
        item = self.make_item(
            item_id="20260101-REQ-aaaaaa", ac="- [x] AC01 works", size="S"
        )
        self.write_report(item_id=item.id)
        self.assertEqual(self.run_flow("gate", "--level", "l3", "--work", item.id)[0], 0)
        code, output = self.run_flow("done", "20260101-REQ-aaaa")
        self.assertEqual(code, 0, output)

    def test_gate_prefix_records_the_full_id_for_done(self) -> None:
        item = self.make_item(
            item_id="20260101-REQ-aaaaaa", ac="- [x] AC01 works", size="S"
        )
        self.write_report(item_id=item.id)
        gate = self.run_flow("gate", "--level", "l3", "--work", "20260101-REQ-aaaa")
        self.assertEqual(gate[0], 0, gate[1])
        code, output = self.run_flow("done", item.id)
        self.assertEqual(code, 0, output)

    def test_id_must_match_the_format(self) -> None:
        self.make_item(item_id="20260101-REQ-01")
        errors, _ = checks.check_project(self.profile)
        self.assertTrue(any("does not match [id] format" in error for error in errors))

    def test_five_character_suffix_no_longer_matches_the_format(self) -> None:
        self.make_item(item_id="20260101-REQ-k7m2p")
        errors, _ = checks.check_project(self.profile)
        self.assertTrue(any("does not match [id] format" in error for error in errors))


class CheckScopeTest(BaseCase):
    def test_gate_work_ignores_another_broken_item(self) -> None:
        good = self.make_item(item_id="20260101-REQ-aaaaaa", size="S")
        broken = self.make_item(item_id="20260101-REQ-bbbbbb", owner="")
        self.assertTrue(broken.meta.get("owner", "") == "")

        code, output = self.run_flow("gate", "--level", "l1", "--work", good.id)
        self.assertEqual(code, 0, output)

        code, output = self.run_flow("check")
        self.assertEqual(code, 1)
        self.assertIn("missing frontmatter field 'owner'", output)

    def test_check_work_validates_only_the_named_item(self) -> None:
        self.make_item(item_id="20260101-REQ-aaaaaa", size="S")
        self.make_item(item_id="20260101-REQ-bbbbbb", owner="")
        code, output = self.run_flow("check", "--work", "20260101-REQ-aaaaaa")
        self.assertEqual(code, 0, output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
