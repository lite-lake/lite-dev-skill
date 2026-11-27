"""Adoption is derived, not stored; detectors propose and only --apply writes."""

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
from flowlib import adopt, artifacts, checks  # noqa: E402
from flowlib import profile as profile_mod  # noqa: E402
from flowlib.errors import FlowError  # noqa: E402

PROFILE = """\
[project]
name = "legacy"
language = "en"

[flow]
requires = ">=0.5.0,<0.6"

[id]
format = "{date}-{type}-{time}"

[gate]
l1 = ["test"]
l2 = ["test", "lint"]
l3 = ["test", "lint"]

[commands]
test = "!unconfigured"
lint = "!unconfigured"

[docs]
required = ["README.md"]
"""


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.profile_path = self.root / "docs/flow/profile.toml"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> str:
        process = subprocess.run(
            ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        return process.stdout.strip()

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def scaffold(self, profile: str = PROFILE) -> None:
        self.write("docs/flow/profile.toml", profile)
        self.write("README.md", "# legacy\n")

    def load(self) -> profile_mod.Profile:
        return profile_mod.load(self.profile_path)

    def run_init(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = flow.main(["init", "--root", str(self.root), *args])
        return code, out.getvalue(), err.getvalue()

    def run_gate(self, level: str = "l1") -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = flow.main(["--profile", str(self.profile_path), "gate", "--level", level])
        return code, out.getvalue()

    def run_status(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = flow.main(["--profile", str(self.profile_path), "status", *args])
        return code, out.getvalue()

    def run_cli(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = flow.main(["--profile", str(self.profile_path), *args])
        return code, out.getvalue()

    def profile_text(self) -> str:
        return self.profile_path.read_text(encoding="utf-8")


class SentinelTest(Base):
    def test_unconfigured_is_a_value(self) -> None:
        self.assertTrue(profile_mod.is_unconfigured("!unconfigured"))
        self.assertTrue(profile_mod.is_unconfigured(""))
        self.assertTrue(
            profile_mod.is_unconfigured(
                "echo 'configure [commands] test in docs/flow/profile.toml' >&2; exit 1"
            )
        )
        self.assertFalse(profile_mod.is_unconfigured("npm test"))

    def test_legacy_placeholder_blocks_the_gate(self) -> None:
        self.scaffold(
            PROFILE.replace(
                'test = "!unconfigured"',
                'test = "echo \'configure [commands] test\' >&2; exit 1"',
            )
        )
        code, output = self.run_gate()
        self.assertEqual(code, 2, output)
        self.assertIn("is not wired", output)

    def test_commands_plan_refuses_an_unconfigured_step(self) -> None:
        self.scaffold()
        from flowlib import commands

        with self.assertRaises(profile_mod.ProfileError):
            commands.plan(self.load(), "l1")

    def test_done_refuses_before_looking_for_the_item(self) -> None:
        self.scaffold()
        code, output = self.run_cli("done", "20260101-REQ-aaaaaa")
        self.assertEqual(code, 2, output)
        self.assertIn("is not wired", output)

    def test_a_cheap_level_runs_before_a_strict_level_is_wired(self) -> None:
        self.scaffold(
            PROFILE.replace('test = "!unconfigured"', 'test = "echo ok"')
            .replace('lint = "!unconfigured"', 'lint = "echo lint"\ne2e = "!unconfigured"')
            .replace('l3 = ["test", "lint"]', 'l3 = ["test", "e2e"]')
        )
        code, output = self.run_gate("l1")
        self.assertEqual(code, 0, output)
        code, output = self.run_gate("l3")
        self.assertEqual(code, 2, output)
        self.assertIn("gate l3 is not wired", output)


class LadderTest(Base):
    def test_a_fresh_scaffold_opens_at_wired(self) -> None:
        self.scaffold()
        ladder = adopt.ladder(self.load())
        self.assertTrue(ladder.by_id("S0").done)
        self.assertFalse(ladder.by_id("S1").done)
        self.assertEqual(ladder.current.id, "S1")
        self.assertEqual(ladder.done, 1)

    def test_wiring_the_command_closes_s1(self) -> None:
        self.scaffold()
        text = self.profile_text().replace(
            'test = "!unconfigured"', 'test = "echo ok"'
        ).replace('lint = "!unconfigured"', 'lint = "echo lint"')
        self.profile_path.write_text(text, encoding="utf-8")
        ladder = adopt.ladder(self.load())
        self.assertTrue(ladder.by_id("S1").done)

    def test_later_rungs_do_not_count_past_a_gap(self) -> None:
        self.scaffold()
        # Identity resolves from the environment, but S1 is open: the count stops.
        import os

        os.environ["LITE_DEV_OWNER"] = "tester"
        try:
            ladder = adopt.ladder(self.load())
        finally:
            os.environ.pop("LITE_DEV_OWNER", None)
        self.assertTrue(ladder.by_id("S4").done)
        self.assertEqual(ladder.done, 1)

    def test_status_reports_the_ladder(self) -> None:
        self.scaffold()
        code, output = self.run_status("--json")
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["adoption"]["done"], 1)
        self.assertEqual(payload["adoption"]["current"], "S1")
        self.assertEqual(payload["adoption"]["next"], "init --plan")


class DetectTest(Base):
    def test_makefile_target_is_proposed(self) -> None:
        self.scaffold()
        self.write("Makefile", "test:\n\tpytest\n")
        plan = adopt.plan(self.load())
        proposal = plan.find("commands.test")
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.value, "make test")
        self.assertIn("Makefile", proposal.source)

    def test_package_json_picks_the_lockfile_runner(self) -> None:
        self.scaffold()
        self.write("package.json", '{"scripts": {"test": "jest", "lint": "eslint ."}}')
        self.write("pnpm-lock.yaml", "lockfileVersion: 6\n")
        plan = adopt.plan(self.load())
        self.assertEqual(plan.find("commands.test").value, "pnpm test")
        self.assertEqual(plan.find("commands.lint").value, "pnpm run lint")

    def test_python_unittest_is_proposed_from_tests(self) -> None:
        self.scaffold()
        self.write("tests/test_app.py", "def test_ok():\n    assert True\n")
        plan = adopt.plan(self.load())
        self.assertEqual(
            plan.find("commands.test").value,
            "python3 -m unittest discover -s tests -q",
        )

    def test_pytest_configuration_wins_over_unittest(self) -> None:
        self.scaffold()
        self.write("pytest.ini", "[pytest]\n")
        self.write("tests/test_app.py", "def test_ok():\n    assert True\n")
        plan = adopt.plan(self.load())
        self.assertEqual(plan.find("commands.test").value, "python3 -m pytest")

    def test_language_follows_the_entry_documents(self) -> None:
        self.scaffold()
        self.write("README.md", "# 旧项目\n\n" + "这是一个中文项目。" * 20 + "\n")
        plan = adopt.plan(self.load())
        proposal = plan.find("project.language")
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.value, "zh")

    def test_a_record_directory_is_proposed_as_a_store(self) -> None:
        self.scaffold()
        for index in range(5):
            self.write(f"docs/prds/req-{index}.md", "# requirement\n")
        plan = adopt.plan(self.load())
        proposal = plan.find("docs.stores")
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.value, ["docs/prds"])

    def test_extension_detector_is_used(self) -> None:
        self.scaffold(
            PROFILE
            + """
[extensions]
enabled = ["demo"]
dir = "docs/flow/extensions"
"""
        )
        self.write(
            "docs/flow/extensions/demo/extension.toml",
            'name = "demo"\nversion = "1.0.0"\nrequires = ">=0.5.0,<0.6"\n'
            '[[detect]]\nfile = "go.mod"\ncommand = "go test ./..."\n',
        )
        self.write("go.mod", "module example.com/demo\n")
        plan = adopt.plan(self.load())
        proposal = plan.find("commands.test")
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.value, "go test ./...")
        self.assertIn("demo", proposal.source)
        code, output = self.run_cli("extensions")
        self.assertEqual(code, 0, output)
        self.assertIn("detect go.mod -> go test ./...", output)

    def test_plan_is_read_only(self) -> None:
        self.scaffold()
        self.write("package.json", '{"scripts": {"test": "echo ok"}}')
        before = self.profile_text()
        code, output, _ = self.run_init("--plan")
        self.assertEqual(code, 0, output)
        self.assertIn("commands.test", output)
        self.assertEqual(self.profile_text(), before)

    def test_a_broken_link_yields_an_exempt_shape(self) -> None:
        self.scaffold()
        self.write("README.md", "# legacy\n\n[gone](missing.md)\n")
        plan = adopt.plan(self.load())
        self.assertTrue(any('check = "links"' in block for block in plan.advice))


class ApplyTest(Base):
    def test_apply_wires_commands_and_keeps_comments(self) -> None:
        self.scaffold()
        self.write("package.json", '{"scripts": {"test": "echo ok", "lint": "echo lint"}}')
        code, output, _ = self.run_init(
            "--apply", "commands.test", "--apply", "commands.lint"
        )
        self.assertEqual(code, 0, output)
        self.assertIn("applied: commands.test", output)
        self.assertIn("applied: commands.lint", output)
        self.assertIn('test = "npm test"', self.profile_text())
        self.assertIn('lint = "npm run lint"', self.profile_text())
        self.assertIn("adoption: 3/6", output)
        code, gate_output = self.run_gate()
        self.assertEqual(code, 0, gate_output)

    def test_apply_language_rewrites_the_routing_block(self) -> None:
        self.write("README.md", "# 旧项目\n\n" + "中文说明。" * 30 + "\n")
        code, output, _ = self.run_init()
        self.assertEqual(code, 0, output)
        self.assertIn("This project uses lite-dev", (self.root / "AGENTS.md").read_text())
        code, output, _ = self.run_init("--apply", "project.language")
        self.assertEqual(code, 0, output)
        agents = (self.root / "AGENTS.md").read_text()
        self.assertIn("本项目使用 lite-dev", agents)
        self.assertIn("# 旧项目", (self.root / "README.md").read_text())

    def test_apply_refuses_a_stale_plan(self) -> None:
        self.scaffold()
        proposal = adopt.Proposal(
            id="commands.test",
            value="npm test",
            source="test",
            section="commands",
            key="test",
            expect="!unconfigured",
        )
        self.profile_path.write_text(
            self.profile_text().replace('test = "!unconfigured"', 'test = "make test"'),
            encoding="utf-8",
        )
        before = self.profile_text()
        with self.assertRaises(FlowError):
            adopt.apply(self.profile_path, [proposal], ["commands.test"])
        self.assertEqual(self.profile_text(), before)

    def test_apply_rejects_an_unknown_id(self) -> None:
        self.scaffold()
        with self.assertRaises(FlowError):
            adopt.apply(self.profile_path, [], ["commands.nope"])

    def test_apply_writes_a_multiline_array_whole(self) -> None:
        text = '[docs]\nstores = [\n  "a",\n]\n\n[release]\nchannels = []\n'
        new = adopt.set_value(text, "docs", "stores", '["b"]')
        self.assertIn('stores = ["b"]', new)
        self.assertNotIn('"a"', new)
        self.assertIn("[release]", new)

    def test_set_value_preserves_a_trailing_comment(self) -> None:
        text = '[project]\nlanguage = "en"   # en | zh\n'
        new = adopt.set_value(text, "project", "language", '"zh"')
        self.assertIn('language = "zh"', new)
        self.assertIn("# en | zh", new)

    def test_set_value_inserts_a_missing_key_and_section(self) -> None:
        text = '[docs]\nrequired = ["README.md"]\n'
        new = adopt.set_value(text, "docs", "stores", '["docs/prds"]')
        self.assertIn('stores = ["docs/prds"]', new)
        self.assertIn("required", new)
        created = adopt.set_value('[project]\nname = "x"\n', "docs", "stores", "[]")
        self.assertIn("[docs]\nstores = []\n", created)
        eof = adopt.set_value("[docs]", "docs", "stores", "[]")
        self.assertEqual(eof, "[docs]\nstores = []\n")


class UpgradeTest(Base):
    def test_upgrade_proposes_and_applies_the_pin(self) -> None:
        self.scaffold(PROFILE.replace(">=0.5.0,<0.6", ">=0.3.9,<0.4"))
        plan = adopt.upgrade_plan(self.profile_path)
        proposal = plan.find("flow.requires")
        self.assertIsNotNone(proposal)
        self.assertIn(flow.__version__, proposal.value)
        adopt.apply(self.profile_path, plan.proposals, ["flow.requires"])
        self.assertEqual(self.load().requires, proposal.value)

    def test_upgrade_reports_commands_it_cannot_invent(self) -> None:
        self.scaffold(PROFILE.replace(">=0.5.0,<0.6", ">=0.3.9,<0.4"))
        plan = adopt.upgrade_plan(self.profile_path)
        self.assertTrue(any("unconfigured" in note for note in plan.notes))


class EndToEndTest(Base):
    def test_adopt_a_legacy_project_in_three_steps(self) -> None:
        """init -> plan -> apply: the only three steps a project needs."""
        self.git("init", "-q")
        self.write(
            "package.json",
            '{"scripts": {"test": "echo ok", "lint": "echo lint"}}',
        )
        code, output, _ = self.run_init("--adopt")
        self.assertEqual(code, 0, output)
        # The template's three levels all run `test`; one proposal wires them.
        self.assertIn("plan: 1 proposal(s)", output)
        code, output, _ = self.run_init("--apply", "commands.test")
        self.assertEqual(code, 0, output)
        code, status_output = self.run_status("--json")
        self.assertEqual(code, 0)
        payload = json.loads(status_output)
        self.assertGreaterEqual(payload["adoption"]["done"], 3)
        self.assertNotEqual(payload["adoption"]["current"], "S1")
        code, gate_output = self.run_gate("l1")
        self.assertEqual(code, 0, gate_output)


if __name__ == "__main__":
    unittest.main()
