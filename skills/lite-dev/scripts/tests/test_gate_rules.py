"""Gate rules: risk paths demand a design, dependency files fall back, and a
stale full level is called out without blocking."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import flow  # noqa: E402
from flowlib import gate_log  # noqa: E402
from flowlib import profile as profile_mod  # noqa: E402

ITEM_ID = "20261126-REQ-234567"
SLUG = f"{ITEM_ID}-touch-schema"

PROFILE = """\
[project]
name = "gate-project"
language = "en"
docs_dir = "docs"
work_dir = "docs/work"

[flow]
requires = ">=0.7.0,<1.0"

[id]
format = "{date}-{type}-{time}"

[gate]
l1 = ["test"]
l3 = ["test"]
fallback_paths = ["deps.txt"]
fresh_days = 5

[commands]
test = "echo ok"

[design]
required_for = ["L"]
risk_paths = ["db/"]
risk_exempt = ["db/README.md"]
risk_gate = "block"

[docs]
required = ["README.md"]
"""

# The profile above without l3: `full_level` then falls back to l1, and the
# tool must say which level `done` will actually close on.
L1_ONLY = PROFILE.replace('l3 = ["test"]\n', '')

REPORT = """\
---
item: {item_id}
---

## Result

- Verdict: PASS
- Reason: ran the tests

## Evidence

| AC | Command | Output / artefact |
|---|---|---|
| AC01 | python3 -m unittest | OK |
"""

ITEM = """\
---
id: {item_id}
title: Touch schema
type: REQ
priority: P2
size: M
mode: one-shot
owner: alice
created: 2026-11-26
closed:
---

## Clarify

- Status: clarified

## AC

- [ ] AC01 the schema change works
"""


class GateCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.profile_path = self.root / "docs/flow/profile.toml"
        self.write("README.md", "# project\n")
        self.write("docs/flow/profile.toml", PROFILE)
        self.write(f"docs/work/2026-11/{SLUG}/item.md", ITEM.format(item_id=ITEM_ID))
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

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

    def git(self, *args: str) -> str:
        process = subprocess.run(
            ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        return process.stdout.strip()

    def commit_all(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def noise_commits(self, count: int) -> None:
        """`count` unrelated commits with the current tree, via plumbing.

        Real `git commit` would run hooks and rewrite the index `count` times; a
        commit-tree chain over one tree produces the same history in one pass.
        """
        tree = self.git("rev-parse", "HEAD^{tree}")
        parent = self.git("rev-parse", "HEAD")
        for index in range(count):
            parent = self.git(
                "commit-tree", tree, "-p", parent, "-m", f"chore: unrelated {index}"
            )
        self.git("update-ref", "HEAD", parent)

    def ledger(self) -> Path:
        profile = profile_mod.load(self.profile_path)
        return gate_log.path_for(profile)


class GateRulesTest(GateCase):
    def test_risk_path_without_design_blocks_when_configured(self) -> None:
        self.write("db/schema.sql", "create table t (id int);\n")
        code, output = self.run_flow("gate", "--level", "l1", "--work", ITEM_ID)
        self.assertEqual(code, 1, output)
        self.assertIn("changes a risk path without a ready design", output)
        self.assertIn("db/schema.sql (worktree)", output)
        self.assertIn("design-ready", output)

    def test_risk_path_in_a_commit_beyond_any_window_is_still_reported(self) -> None:
        """The scan is the whole history, not the last N commits.

        A 200-commit window used to drop the early commits of a long item, so
        the gate reported nothing and passed. Bury the item's commit under 300
        unrelated ones and the risk path must still be named.
        """
        self.write("db/schema.sql", "create table t (id int);\n")
        self.commit_all(f"feat: {ITEM_ID} touches the schema")
        self.noise_commits(300)

        code, output = self.run_flow("gate", "--level", "l1", "--work", ITEM_ID)
        self.assertEqual(code, 1, output)
        self.assertIn("changes a risk path without a ready design", output)
        self.assertIn("db/schema.sql (committed)", output)

    def test_risk_gate_can_warn_instead_of_block(self) -> None:
        self.write(
            "docs/flow/profile.toml",
            PROFILE.replace('risk_gate = "block"', 'risk_gate = "warn"'),
        )
        self.write("db/schema.sql", "create table t (id int);\n")
        code, output = self.run_flow("gate", "--level", "l1", "--work", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertIn("warn:", output)
        self.assertIn("changes a risk path", output)

    def test_exempt_path_does_not_trip_the_risk_gate(self) -> None:
        self.write("db/README.md", "# db\n")
        code, output = self.run_flow("gate", "--level", "l1", "--work", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertNotIn("changes a risk path", output)

    def test_worktree_only_fallback_says_the_path_is_in_the_worktree(self) -> None:
        """Dirty files count, but the warning must say where it saw the path."""
        self.write("deps.txt", "pkg==1.0\n")
        code, output = self.run_flow("gate", "--level", "l1", "--work", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertIn("changed deps.txt (worktree) invalidates l1", output)
        self.assertIn("gate --level l3", output)

        code, output = self.run_flow("gate", "--level", "l3", "--work", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertNotIn("invalidates l3", output)

    def test_a_committed_dependency_change_is_labelled_as_committed(self) -> None:
        self.write("deps.txt", "pkg==1.0\n")
        self.commit_all(f"feat: {ITEM_ID} bumps the lock file")
        code, output = self.run_flow("gate", "--level", "l1", "--work", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertIn("changed deps.txt (committed) invalidates l1", output)

    def ledger(self) -> Path:
        profile = profile_mod.load(self.profile_path)
        return gate_log.path_for(profile)

    def test_gate_records_into_the_ledger_outside_the_worktree(self) -> None:
        code, _ = self.run_flow("gate", "--level", "l3")
        self.assertEqual(code, 0)
        ledger = self.ledger()
        self.assertTrue(ledger.is_file())
        entry = json.loads(ledger.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(entry["level"], "l3")
        self.assertTrue(entry["ok"])
        # The ledger must never show up as a changed path.
        status = self.run_flow("check")
        self.assertEqual(status[0], 0)

    def test_stale_full_level_is_reported(self) -> None:
        ledger = self.ledger()
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            json.dumps({"date": "2000-01-01", "level": "l3", "ok": True, "item": ""}) + "\n",
            encoding="utf-8",
        )
        code, output = self.run_flow("status")
        self.assertEqual(code, 0)
        # A clarified item is not closeable yet; status stays quiet. The cheaper
        # gate still surfaces the stale full-level PASS.
        self.assertNotIn("l3 last passed", output)

        code, output = self.run_flow("gate", "--level", "l1", "--work", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertIn("l3 last passed", output)


class FullLevelTest(GateCase):
    """`done` closes on the strictest defined level; say which one that is."""

    def use_l1_only_profile(self) -> None:
        self.write("docs/flow/profile.toml", L1_ONLY)
        self.write(
            f"docs/work/2026-11/{SLUG}/item.md",
            ITEM.format(item_id=ITEM_ID).replace("- [ ] AC01", "- [x] AC01"),
        )
        self.write(f"docs/work/2026-11/{SLUG}/test-report.md", REPORT.format(item_id=ITEM_ID))

    def test_done_warns_when_the_strictest_level_is_l1(self) -> None:
        self.use_l1_only_profile()
        gate = self.run_flow("gate", "--level", "l1", "--work", ITEM_ID)
        self.assertEqual(gate[0], 0, gate[1])

        code, output = self.run_flow("done", ITEM_ID, "--owner", "alice")
        self.assertEqual(code, 0, output)
        self.assertIn("the strictest gate is l1; done will close on l1", output)
        self.assertIn("[gate] l3", output)

    def test_status_warns_when_the_strictest_level_is_l1(self) -> None:
        self.use_l1_only_profile()
        code, output = self.run_flow("status")
        self.assertEqual(code, 0, output)
        self.assertIn("the strictest gate is l1; done will close on l1", output)

    def test_status_prints_the_running_version(self) -> None:
        code, output = self.run_flow("status")
        self.assertEqual(code, 0, output)
        self.assertIn(f"lite-dev {flow.__version__}", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
