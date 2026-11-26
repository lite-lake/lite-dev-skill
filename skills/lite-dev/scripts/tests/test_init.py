"""Scaffolding and adoption: init writes what is missing, baseline bounds history."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import flow  # noqa: E402


class InitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> str:
        process = subprocess.run(
            ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        return process.stdout.strip()

    def init_repo(self) -> None:
        self.git("init", "-q")

    def commit_all(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_flow(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = flow.main(["init", "--root", str(self.root), *args])
        return code, out.getvalue(), err.getvalue()

    def run_command(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = flow.main([*args, "--profile", str(self.root / "docs/flow/profile.toml")])
        return code, out.getvalue(), err.getvalue()

    def profile_text(self) -> str:
        return (self.root / "docs/flow/profile.toml").read_text(encoding="utf-8")

    def test_init_scaffolds_a_new_project(self) -> None:
        self.init_repo()
        code, output, _ = self.run_flow()
        self.assertEqual(code, 0, output)
        self.assertIn("(created)", output)
        self.assertIn("check: PASS", output)
        for relative in (
            "docs/flow/profile.toml",
            "README.md",
            "AGENTS.md",
            "docs/README.md",
            "docs/work/README.md",
        ):
            self.assertTrue((self.root / relative).is_file(), relative)
        self.assertIn("<!-- lite-dev:begin -->", (self.root / "AGENTS.md").read_text())
        # The scaffold pins this install, so every machine runs the same gate.
        self.assertIn('requires = ">=', self.profile_text())
        self.assertIn(flow.__version__, self.profile_text())
        # Generated entry documents must pass their own zero-fact rule.
        self.assertIn("0 warning(s)", output)

    def test_init_is_idempotent(self) -> None:
        self.init_repo()
        self.assertEqual(self.run_flow()[0], 0)
        before = {
            path.relative_to(self.root).as_posix(): path.read_text(encoding="utf-8")
            for path in self.root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }
        code, output, _ = self.run_flow()
        self.assertEqual(code, 0, output)
        self.assertIn("(kept)", output)
        after = {
            path.relative_to(self.root).as_posix(): path.read_text(encoding="utf-8")
            for path in self.root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }
        self.assertEqual(before, after)

    def test_init_keeps_existing_documents_and_prepends_the_router(self) -> None:
        self.init_repo()
        self.write("README.md", "# legacy\n\nTeam rules live in AGENTS.md.\n")
        self.write("AGENTS.md", "# Team rules\n\nBe nice.\n")
        code, output, _ = self.run_flow("--adopt")
        self.assertEqual(code, 0, output)
        self.assertEqual(
            (self.root / "README.md").read_text(), "# legacy\n\nTeam rules live in AGENTS.md.\n"
        )
        agents = (self.root / "AGENTS.md").read_text()
        self.assertTrue(agents.startswith("# Team rules"))
        self.assertIn("Be nice.", agents)
        self.assertIn("routing block inserted", output)
        self.assertLess(agents.index("<!-- lite-dev:begin -->"), agents.index("Be nice."))
        # A second run must not insert the block twice.
        self.run_flow("--adopt")
        self.assertEqual(
            (self.root / "AGENTS.md").read_text().count("<!-- lite-dev:begin -->"), 1
        )

    def test_init_reports_legacy_pins_as_warnings(self) -> None:
        self.init_repo()
        self.write(
            "README.md",
            "# legacy\n\nRuns on Node 18.2.0 with 3 services since 2024-05-01.\n",
        )
        code, output, _ = self.run_flow("--adopt")
        self.assertEqual(code, 0, output)
        self.assertIn("pins a version (Node 18.2.0)", output)
        self.assertIn("adopt:", output)

    def test_init_honours_the_language(self) -> None:
        self.init_repo()
        code, output, _ = self.run_flow("--language", "zh")
        self.assertEqual(code, 0, output)
        self.assertIn('language = "zh"', self.profile_text())
        self.assertIn("本项目使用 lite-dev", (self.root / "AGENTS.md").read_text())
        self.assertIn("文档", (self.root / "docs/README.md").read_text())
        self.assertIn("0 warning(s)", output)

    def test_init_works_without_git(self) -> None:
        code, output, _ = self.run_flow()
        self.assertEqual(code, 0, output)
        self.assertIn('mainline = "main"', self.profile_text())

    def test_baseline_needs_a_clean_tree(self) -> None:
        self.init_repo()
        self.run_flow()
        self.commit_all("chore: scaffold")
        self.write("README.md", "# changed\n")
        code, output, _ = self.run_flow("--baseline")
        self.assertEqual(code, 0, output)
        self.assertIn("baseline: not set", output)
        self.assertNotIn('\nbaseline = "', self.profile_text())

    def test_baseline_without_git_names_the_fix(self) -> None:
        code, output, _ = self.run_flow("--baseline")
        self.assertEqual(code, 0, output)
        self.assertIn("not a git repository", output)
        self.assertIn("git init", output)

    def test_baseline_bounds_the_debt_of_a_project_without_channels(self) -> None:
        self.init_repo()
        self.run_flow()
        self.commit_all("chore: scaffold")
        code, output, _ = self.run_flow("--baseline")
        self.assertEqual(code, 0, output)
        self.assertIn("[reconcile] baseline", output)
        self.assertIn('\nbaseline = "', self.profile_text())
        self.commit_all("chore: record the baseline")

        code, output, _ = self.run_command("reconcile")
        self.assertEqual(code, 0, output)
        self.assertIn("channel: baseline", output)
        # Committing the baseline line is a record write, not debt.
        self.assertIn("no work item (0)", output)
        self.assertIn("bookkeeping ignored (1)", output)

        self.write("src/legacy.py", "x = 1\n")
        self.commit_all("feat: unrecorded change")
        code, output, _ = self.run_command("reconcile")
        self.assertEqual(code, 0, output)
        self.assertIn("feat: unrecorded change", output)

    def test_reconcile_without_channels_names_the_fix(self) -> None:
        self.init_repo()
        self.run_flow()
        self.commit_all("chore: scaffold")
        code, _, err = self.run_command("reconcile")
        self.assertEqual(code, 2)
        self.assertIn("[reconcile] baseline", err)

    def test_reconcile_since_works_without_channels(self) -> None:
        self.init_repo()
        self.run_flow()
        self.commit_all("chore: scaffold")
        first = self.git("rev-parse", "HEAD")
        self.write("src/a.py", "x = 1\n")
        self.commit_all("feat: later work")
        code, output, _ = self.run_command("reconcile", "--since", first)
        self.assertEqual(code, 0, output)
        self.assertIn("channel: baseline", output)
        self.assertIn("feat: later work", output)


if __name__ == "__main__":
    unittest.main()
