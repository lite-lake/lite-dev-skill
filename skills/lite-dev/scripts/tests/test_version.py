"""The X/Y/Z policy: patch seamless, minor review, major confirmation."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import flow  # noqa: E402
from flowlib import adopt, changelog, checks, scaffold  # noqa: E402
from flowlib import profile as profile_mod  # noqa: E402

PROFILE = """\
[project]
name = "demo"
language = "en"

[flow]
requires = ">=0.7.0,<1.0"
reviewed = "0.7.0"

[id]
format = "{date}-{type}-{time}"

[gate]
l1 = ["test"]
l2 = ["test"]
l3 = ["test"]

[commands]
test = "!unconfigured"

[docs]
required = ["README.md"]
"""

DRIFTED = PROFILE.replace(
    'requires = ">=0.7.0,<1.0"\nreviewed = "0.7.0"',
    'requires = ">=0.6.0,<1.0"\nreviewed = "0.6.1"',
)
UNLOADABLE = PROFILE.replace(
    'requires = ">=0.7.0,<1.0"\nreviewed = "0.7.0"',
    'requires = ">=0.6.0,<0.7"\nreviewed = "0.6.1"',
)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.profile_path = self.root / "docs/flow/profile.toml"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def scaffold(self, profile: str = PROFILE) -> None:
        self.write("docs/flow/profile.toml", profile)
        self.write("README.md", "# demo\n")

    def load(self):
        return profile_mod.load(self.profile_path)

    def profile_text(self) -> str:
        return self.profile_path.read_text(encoding="utf-8")

    def run_cmd(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = flow.main(["--profile", str(self.profile_path), *args])
        return code, out.getvalue(), err.getvalue()

    def run_init(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = flow.main(["init", "--root", str(self.root), *args])
        return code, out.getvalue(), err.getvalue()


class WindowTest(unittest.TestCase):
    def test_compat_range_spans_the_major_line(self) -> None:
        self.assertEqual(scaffold.compat_range("0.7.0"), ">=0.7.0,<1.0")
        self.assertEqual(scaffold.compat_range("0.7.9"), ">=0.7.0,<1.0")
        self.assertEqual(scaffold.compat_range("1.2.3"), ">=1.2.0,<2.0")
        self.assertEqual(scaffold.compat_range("2.0.0"), ">=2.0.0,<3.0")

    def test_range_floor(self) -> None:
        self.assertEqual(profile_mod.range_floor(">=0.6.1,<1.0"), "0.6.1")
        self.assertEqual(profile_mod.range_floor(">=0.6,<1.0"), "0.6.0")
        self.assertEqual(profile_mod.range_floor("0.6"), "0.6.0")
        self.assertEqual(profile_mod.range_floor(">0.6.0,<1.0"), "0.6.1")
        self.assertEqual(profile_mod.range_floor("<1.0"), "")
        self.assertEqual(profile_mod.range_floor("banana"), "")

    def test_drift_classes(self) -> None:
        self.assertEqual(profile_mod.classify_drift("0.7.2", "0.7.0"), "patch")
        self.assertEqual(profile_mod.classify_drift("0.7.0", "0.7.9"), "patch")
        self.assertEqual(profile_mod.classify_drift("0.8.0", "0.7.9"), "minor")
        self.assertEqual(profile_mod.classify_drift("1.0.0", "0.9.9"), "major")
        self.assertEqual(profile_mod.classify_drift("0.6.1", "0.7.0"), "older-minor")
        self.assertEqual(profile_mod.classify_drift("0.9.0", "1.0.0"), "older-major")
        self.assertEqual(profile_mod.classify_drift("0.7.0", ""), "unknown")

    def test_drift_note_is_empty_for_patches(self) -> None:
        self.assertEqual(profile_mod.drift_note("0.7.2", "0.7.0"), "")
        self.assertIn("minor ahead", profile_mod.drift_note("0.8.0", "0.7.0"))
        self.assertIn("older than", profile_mod.drift_note("0.6.1", "0.7.0"))


class ProfileContractTest(Base):
    def test_reviewed_is_read(self) -> None:
        self.scaffold(DRIFTED)
        profile = self.load()
        self.assertEqual(profile.reviewed, "0.6.1")
        self.assertEqual(profile_mod.classify_drift(flow.__version__, profile.reviewed), "minor")

    def test_missing_reviewed_falls_back_to_the_floor(self) -> None:
        self.scaffold(DRIFTED.replace('reviewed = "0.6.1"\n', ""))
        self.assertEqual(self.load().reviewed, "0.6.0")

    def test_reviewed_outside_requires_is_an_error(self) -> None:
        self.scaffold(
            PROFILE.replace('reviewed = "0.7.0"', 'reviewed = "1.5.0"')
        )
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load()
        self.assertIn("outside requires", str(caught.exception))

    def test_check_warns_on_a_minor_but_not_a_patch(self) -> None:
        self.scaffold(DRIFTED)
        _, warnings = checks.check_project(self.load())
        self.assertTrue(
            any("minor ahead" in warning for warning in warnings), warnings
        )

        self.scaffold(PROFILE.replace('reviewed = "0.7.0"', 'reviewed = "0.7.0"'))
        _, warnings = checks.check_project(self.load())
        self.assertFalse(any("minor ahead" in warning for warning in warnings))


class ChangelogTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "CHANGELOG.md"
        self.path.write_text(
            "# Changelog\n\n"
            "## Unreleased\n\n### Changed\n\n- wip\n\n"
            "## 0.7.0 — 2026-11-27\n\n### Breaking changes\n\n- moved\n\n"
            "## 0.6.1 — 2026-11-26\n\n### Fixed\n\n- small\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_sections_skip_unreleased(self) -> None:
        self.assertEqual(
            [section.version for section in changelog.sections(self.path)],
            ["0.7.0", "0.6.1"],
        )

    def test_between_is_exclusive_at_the_floor(self) -> None:
        items = changelog.between(self.path, "0.6.1", "0.7.0")
        self.assertEqual([item.version for item in items], ["0.7.0"])
        self.assertTrue(changelog.render(items, mark_breaking=True)[0].endswith("[breaking]"))

    def test_no_baseline_shows_only_the_target(self) -> None:
        items = changelog.between(self.path, "", "0.7.0")
        self.assertEqual([item.version for item in items], ["0.7.0"])


class VersionCommandTest(Base):
    def test_reports_a_minor_drift(self) -> None:
        self.scaffold(DRIFTED)
        code, out, _ = self.run_cmd("version")
        self.assertEqual(code, 0)
        self.assertIn(f"lite-dev {flow.__version__}", out)
        self.assertIn("reviewed: 0.6.1", out)
        self.assertIn("drift:    minor", out)
        self.assertIn("read CHANGELOG 0.6.1", out)

    def test_json_is_machine_readable(self) -> None:
        self.scaffold(DRIFTED)
        code, out, _ = self.run_cmd("version", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["reviewed"], "0.6.1")
        self.assertEqual(payload["drift"], "minor")
        self.assertTrue(payload["changelog"].endswith("CHANGELOG.md"))

    def test_answers_when_the_profile_cannot_load(self) -> None:
        self.scaffold(UNLOADABLE)
        code, out, _ = self.run_cmd("version")
        self.assertEqual(code, 0)
        self.assertIn("requires lite-dev", out)
        self.assertIn("drift:    minor", out)

    def test_no_profile_is_not_an_error(self) -> None:
        previous = Path.cwd()
        os.chdir(self.root)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = flow.main(["version"])
        finally:
            os.chdir(previous)
        self.assertEqual(code, 0)
        self.assertIn("project:  none", out.getvalue())


class UpgradeReviewTest(Base):
    def test_minor_shows_the_changelog_and_applies_both_proposals(self) -> None:
        self.scaffold(UNLOADABLE)
        code, out, _ = self.run_init("--upgrade")
        self.assertEqual(code, 0)
        self.assertIn("review:  minor 0.6.1", out)
        self.assertIn("## 0.7.0", out)
        self.assertIn("flow.reviewed", out)
        self.assertIn("flow.requires", out)

        code, out, err = self.run_init(
            "--upgrade", "--apply", "flow.requires", "--apply", "flow.reviewed"
        )
        self.assertEqual(code, 0, out + err)
        text = self.profile_text()
        self.assertIn('requires = ">=0.7.0,<1.0"', text)
        self.assertIn('reviewed = "0.7.1"', text)
        _, warnings = checks.check_project(self.load())
        self.assertFalse(any("minor ahead" in warning for warning in warnings))

    def test_major_apply_needs_accept_major(self) -> None:
        self.scaffold(PROFILE.replace('reviewed = "0.7.0"', 'reviewed = "0.6.1"'))
        with patch.object(flow, "__version__", "1.0.0"), patch.object(
            profile_mod, "__version__", "1.0.0"
        ), patch.object(adopt.profile_mod, "__version__", "1.0.0"), patch.object(
            checks, "__version__", "1.0.0"
        ):
            code, out, err = self.run_init(
                "--upgrade", "--apply", "flow.requires", "--apply", "flow.reviewed"
            )
        self.assertEqual(code, 2)
        self.assertIn("--accept-major", err)
        self.assertNotIn('requires = ">=1.0.0,<2.0"', self.profile_text())

    def test_major_apply_records_the_review(self) -> None:
        self.scaffold(PROFILE.replace('reviewed = "0.7.0"', 'reviewed = "0.6.1"'))
        with patch.object(flow, "__version__", "1.0.0"), patch.object(
            profile_mod, "__version__", "1.0.0"
        ), patch.object(adopt.profile_mod, "__version__", "1.0.0"), patch.object(
            checks, "__version__", "1.0.0"
        ):
            code, out, err = self.run_init(
                "--upgrade",
                "--accept-major",
                "--apply",
                "flow.requires",
                "--apply",
                "flow.reviewed",
            )
        self.assertEqual(code, 0, out + err)
        text = self.profile_text()
        self.assertIn('requires = ">=1.0.0,<2.0"', text)
        self.assertIn('reviewed = "1.0.0"', text)


if __name__ == "__main__":
    unittest.main()
