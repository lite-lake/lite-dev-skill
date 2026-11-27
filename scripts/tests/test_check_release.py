"""Every carrier of the version must agree, or a release is refused."""

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import check_release  # noqa: E402


class Tree:
    """A minimal repository whose version carriers can be broken one at a time."""

    def __init__(self, root: Path, version: str = "0.7.0") -> None:
        self.root = root
        self.version = version
        self.write("CHANGELOG.md", self.changelog("en"))
        self.write("CHANGELOG.zh.md", self.changelog("zh"))
        self.write("README.md", "# readme\n\n## One\n\n## Two\n")
        self.write("README.zh.md", "# readme\n\n## 一\n\n## 二\n")
        self.write(
            "skills/lite-dev/scripts/flowlib/__init__.py",
            f'"""demo."""\n\n__version__ = "{version}"\n',
        )
        self.write(
            "skills/lite-dev/profile.template.toml",
            f'[flow]\nrequires = ">={version},<1.0"\nreviewed = "{version}"\n',
        )
        self.write(
            "skills/lite-dev/extensions/demo/extension.toml",
            'name = "demo"\nrequires = ">=0.7.0,<1.0"\n',
        )
        self.sync()

    def changelog(self, language: str) -> str:
        unreleased = "未发布" if language == "zh" else "Unreleased"
        return (
            f"# Changelog\n\n## {unreleased}\n\n"
            f"## {self.version} — 2026-11-27\n\n- release\n\n"
            "## 0.6.1 — 2026-11-26\n\n- older\n"
        )

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def sync(self) -> None:
        for name in check_release.PAIRS:
            (self.root / "skills/lite-dev" / name).write_bytes(
                (self.root / name).read_bytes()
            )


class CheckReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.tree = Tree(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_a_consistent_tree_passes(self) -> None:
        self.assertEqual(check_release.check(self.root, tag="v0.7.0"), [])

    def test_the_changelog_must_start_at_the_version(self) -> None:
        self.tree.write(
            "CHANGELOG.md",
            "# Changelog\n\n## Unreleased\n\n## 0.6.9 — 2026-11-20\n",
        )
        self.tree.sync()
        errors = check_release.check(self.root)
        self.assertTrue(any("CHANGELOG.md starts at 0.6.9" in error for error in errors))

    def test_the_two_changelogs_must_list_the_same_versions(self) -> None:
        self.tree.write(
            "CHANGELOG.zh.md",
            "# 变更日志\n\n## 未发布\n\n## 0.7.0 — 2026-11-27\n\n"
            "## 0.6.0 — 2026-11-20\n",
        )
        self.tree.sync()
        errors = check_release.check(self.root)
        self.assertTrue(any("different versions" in error for error in errors))

    def test_the_bundled_copy_must_be_byte_identical(self) -> None:
        self.tree.write("skills/lite-dev/CHANGELOG.md", "# stale\n")
        errors = check_release.check(self.root)
        self.assertTrue(any("is stale; run this script with --sync" in error for error in errors))

    def test_the_template_window_is_derived(self) -> None:
        self.tree.write(
            "skills/lite-dev/profile.template.toml",
            '[flow]\nrequires = ">=0.6.0,<0.7"\nreviewed = "0.7.0"\n',
        )
        errors = check_release.check(self.root)
        self.assertTrue(any("derives" in error for error in errors))

    def test_an_extension_pin_must_admit_the_version(self) -> None:
        self.tree.write(
            "skills/lite-dev/extensions/demo/extension.toml",
            'name = "demo"\nrequires = ">=0.6,<0.7"\n',
        )
        errors = check_release.check(self.root)
        self.assertTrue(any("excludes 0.7.0" in error for error in errors))

    def test_a_tag_at_head_must_match(self) -> None:
        errors = check_release.check(self.root, tag="v0.6.9")
        self.assertTrue(any("tag v0.6.9" in error for error in errors))

    def test_the_two_readmes_stay_paired(self) -> None:
        self.tree.write("README.zh.md", "# readme\n\n## 一\n")
        errors = check_release.check(self.root)
        self.assertTrue(any("H2 sections" in error for error in errors))

    def test_this_repository_passes(self) -> None:
        self.assertEqual(check_release.check(REPO), [])


if __name__ == "__main__":
    unittest.main()
