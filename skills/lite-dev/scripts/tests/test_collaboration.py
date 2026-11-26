"""Multi-person and multi-machine behaviour: ids, locks, identity, warnings."""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import flow  # noqa: E402
from flowlib import artifacts, checks, fsio  # noqa: E402
from flowlib import profile as profile_mod  # noqa: E402
from flowlib.errors import FlowError  # noqa: E402

PROFILE = """\
[project]
name = "team-project"
language = "en"
docs_dir = "docs"
work_dir = "docs/work"

[flow]
requires = ">=0.3.2,<0.4"

[id]
format = "{date}-{type}-{time}"

[gate]
l1 = ["test"]

[commands]
test = "echo ok"

[design]
required_for = ["L"]

[docs]
required = ["README.md"]
"""

ITEM = """\
---
id: {item_id}
title: Demo
type: REQ
priority: P2
size: S
mode: one-shot
owner: {owner}
created: {created}
closed:
---

## Clarify

- Status: clarified
- Questions: none
- Confirmed assumptions: none

## AC

- [ ] AC01 works
"""


class BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.profile_path = self.root / "docs/flow/profile.toml"
        self.write("docs/flow/profile.toml", PROFILE)
        self.write("README.md", "# team project\n")
        self.profile = self.load_profile()
        self._env = mock.patch.dict(
            os.environ,
            {
                "LITE_DEV_OWNER": "alice",
                "GIT_CONFIG_GLOBAL": str(self.root / "no-global-gitconfig"),
                "GIT_CONFIG_NOSYSTEM": "1",
            },
        )
        self._env.start()
        flow._CLOCK = flow.stamp.Clock()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def load_profile(self) -> profile_mod.Profile:
        return profile_mod.load(self.profile_path)

    def make_item(
        self,
        item_id: str,
        owner: str = "alice",
        created: str = "2026-01-01",
        slug: str = "demo",
    ):
        month = created[:7]
        self.write(
            f"docs/work/{month}/{item_id}-{slug}/item.md",
            ITEM.format(item_id=item_id, owner=owner, created=created),
        )
        return artifacts.load_item(self.root / f"docs/work/{month}/{item_id}-{slug}")

    def run_flow(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = flow.main(["--profile", str(self.profile_path), *args])
        return code, output.getvalue()

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

    def init_repo(self) -> None:
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        self.git("add", "-A")
        self.git("commit", "-qm", "chore: initial import")


class IdCollisionTest(BaseCase):
    """The one case where two clones can collide: the same millisecond."""

    def test_new_bumps_past_a_code_already_on_disk(self) -> None:
        moment = datetime(2026, 1, 5, 10, 0, 0, 0)
        taken = f"20260105-REQ-{flow.stamp.encode(flow.stamp.ms_since_midnight(moment))}"
        self.make_item(taken, created="2026-01-05", slug="taken")

        with mock.patch.object(flow.stamp, "now", return_value=moment):
            code, output = self.run_flow(
                "new", "--title", "Bump", "--type", "REQ", "--size", "S"
            )
        self.assertEqual(code, 0, output)
        created = output.split()[1]
        self.assertNotEqual(created, taken)
        self.assertGreater(created, taken)
        self.assertEqual(artifacts.find_item(self.load_profile(), created).meta["owner"], "alice")

    def test_two_allocations_in_one_millisecond_stay_distinct(self) -> None:
        moment = datetime(2026, 1, 6, 9, 30, 0, 500_000)
        with mock.patch.object(flow.stamp, "now", return_value=moment):
            first_code, first = self.run_flow("new", "--title", "One", "--size", "S")
            second_code, second = self.run_flow("new", "--title", "Two", "--size", "S")
        self.assertEqual(first_code, 0, first)
        self.assertEqual(second_code, 0, second)
        first_id = first.split()[1]
        second_id = second.split()[1]
        self.assertNotEqual(first_id, second_id)
        self.assertGreater(second_id, first_id)

    def test_duplicate_ids_are_reported_and_never_merged(self) -> None:
        self.make_item("20260101-REQ-222222", slug="one")
        self.make_item("20260101-REQ-222222", slug="two")

        errors, _ = checks.check_project(self.load_profile())
        self.assertTrue(
            any("duplicate item id 20260101-REQ-222222" in error for error in errors),
            errors,
        )

        with self.assertRaises(FlowError) as raised:
            artifacts.find_item(self.load_profile(), "20260101-REQ-222222")
        self.assertIn("ambiguous", str(raised.exception))
        self.assertIn("2 matches", str(raised.exception))


class WriterLockTest(BaseCase):
    def test_a_second_process_waits_and_then_fails_with_a_reason(self) -> None:
        marker = self.root / "held.marker"
        script = (
            "import sys, time\n"
            f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
            "from pathlib import Path\n"
            "from flowlib import fsio\n"
            f"with fsio.project_lock(Path({str(self.root)!r})):\n"
            f"    Path({str(marker)!r}).write_text('held', encoding='utf-8')\n"
            "    time.sleep(3.0)\n"
        )
        child = subprocess.Popen([sys.executable, "-c", script])
        try:
            deadline = time.monotonic() + 15
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists(), "the child never took the lock")

            with self.assertRaises(FlowError) as raised:
                with fsio.project_lock(self.root, timeout=0.3):
                    pass
            self.assertIn("another flow.py process", str(raised.exception))
        finally:
            child.kill()
            child.wait()

    def test_atomic_write_uses_lf_and_leaves_no_temporary_file(self) -> None:
        target = self.root / "docs/work/note.md"
        fsio.atomic_write_text(target, "a\nb\n")
        self.assertEqual(target.read_bytes(), b"a\nb\n")
        self.assertEqual([path.name for path in target.parent.iterdir()], ["note.md"])


class OwnerWarningTest(BaseCase):
    def test_owners_that_differ_only_by_case_or_spacing_are_reported(self) -> None:
        self.make_item("20260101-REQ-aaaaaa", owner="Alice")
        self.make_item("20260101-REQ-bbbbbb", owner="alice")
        _, warnings = checks.check_project(self.load_profile())
        self.assertTrue(
            any("differ only by case or spacing" in warning for warning in warnings),
            warnings,
        )

    def test_an_owner_outside_the_roster_is_a_warning(self) -> None:
        self.write(
            "docs/flow/profile.toml",
            PROFILE.replace('language = "en"', 'language = "en"\nowners = ["alice"]'),
        )
        self.make_item("20260101-REQ-aaaaaa", owner="alice")
        self.make_item("20260101-REQ-bbbbbb", owner="carol")
        errors, warnings = checks.check_project(self.load_profile())
        self.assertEqual(errors, [])
        self.assertTrue(
            any("not in [project] owners" in warning for warning in warnings), warnings
        )

    def test_no_roster_means_no_roster_warning(self) -> None:
        self.make_item("20260101-REQ-aaaaaa", owner="carol")
        _, warnings = checks.check_project(self.load_profile())
        self.assertFalse(any("[project] owners" in warning for warning in warnings))

    def test_chinese_slugs_warn_until_quotepath_is_off(self) -> None:
        self.init_repo()
        self.make_item("20260101-REQ-aaaaaa", slug="修复登录超时")
        _, warnings = checks.check_project(self.load_profile())
        self.assertTrue(any("core.quotepath" in warning for warning in warnings), warnings)

        self.git("config", "core.quotepath", "false")
        _, warnings = checks.check_project(self.load_profile())
        self.assertFalse(any("core.quotepath" in warning for warning in warnings))


class StatusTest(BaseCase):
    def test_json_lists_items_and_the_checkout(self) -> None:
        self.make_item("20260101-REQ-aaaaaa", owner="alice")
        self.make_item("20260101-REQ-bbbbbb", owner="bob")
        code, output = self.run_flow("status", "--json")
        self.assertEqual(code, 0, output)
        data = json.loads(output)
        self.assertEqual(data["project"], "team-project")
        self.assertIsNone(data["checkout"])
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual({item["owner"] for item in data["items"]}, {"alice", "bob"})
        self.assertEqual(data["counts"], {"clarified": 2})

    def test_json_mine_filters_by_the_resolved_identity(self) -> None:
        self.make_item("20260101-REQ-aaaaaa", owner="alice")
        self.make_item("20260101-REQ-bbbbbb", owner="bob")
        code, output = self.run_flow("status", "--json", "--mine")
        self.assertEqual(code, 0, output)
        data = json.loads(output)
        self.assertEqual(data["mine"], "alice")
        self.assertEqual([item["id"] for item in data["items"]], ["20260101-REQ-aaaaaa"])

    def test_status_reports_the_distance_from_the_last_fetch(self) -> None:
        remote = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: shutil.rmtree(remote, ignore_errors=True))
        self.init_repo()
        self.git("init", "-q", "--bare", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-q", "-u", "origin", "main")
        self.write("next.txt", "x\n")
        self.git("add", "next.txt")
        self.git("commit", "-qm", "feat: ahead")

        code, output = self.run_flow("status", "--json")
        self.assertEqual(code, 0, output)
        checkout = json.loads(output)["checkout"]
        self.assertEqual(checkout["branch"], "main")
        self.assertTrue(checkout["upstream"])
        self.assertEqual(checkout["ahead"], 1)
        self.assertEqual(checkout["behind"], 0)

        text_code, text = self.run_flow("status")
        self.assertEqual(text_code, 0)
        self.assertIn("upstream: behind 0, ahead 1", text)

    def test_no_upstream_is_stated_in_the_text_output(self) -> None:
        self.make_item("20260101-REQ-aaaaaa")
        self.init_repo()
        code, output = self.run_flow("status")
        self.assertEqual(code, 0, output)
        self.assertIn("no upstream; this clone only", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
