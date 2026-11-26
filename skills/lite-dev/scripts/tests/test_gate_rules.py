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
requires = ">=0.3.5,<0.4"

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


class GateRulesTest(unittest.TestCase):
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

    def test_risk_path_without_design_blocks_when_configured(self) -> None:
        self.write("db/schema.sql", "create table t (id int);\n")
        code, output = self.run_flow("gate", "--level", "l1", "--work", ITEM_ID)
        self.assertEqual(code, 1, output)
        self.assertIn("changes a risk path (db/schema.sql)", output)
        self.assertIn("design-ready", output)

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

    def test_dependency_change_falls_back_to_the_full_level(self) -> None:
        self.write("deps.txt", "pkg==1.0\n")
        code, output = self.run_flow("gate", "--level", "l1", "--work", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertIn("changed deps.txt invalidates l1", output)
        self.assertIn("gate --level l3", output)

        code, output = self.run_flow("gate", "--level", "l3", "--work", ITEM_ID)
        self.assertEqual(code, 0, output)
        self.assertNotIn("invalidates l3", output)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
