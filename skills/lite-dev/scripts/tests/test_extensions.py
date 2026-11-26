import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import flow  # noqa: E402
from flowlib import profile as profile_mod  # noqa: E402

PROFILE = """\
[project]
name = "ext-project"
language = "en"

[flow]
requires = ">=0.3,<0.4"

[id]
format = "{date}-{type}-{rand}"

[gate]
l1 = ["test"]

[commands]
test = "echo ok"

[docs]
required = ["README.md", "docs/README.md"]

[extensions]
enabled = [__ENABLED__]
dir = "docs/flow/extensions"
"""

EXTENSION = """\
name = "__NAME__"
version = "1.0.0"
description = "demo extension"
requires = ">=0.3,<0.4"

[commands]
demo_test = "echo demo"

[gate]
l1 = ["demo_test"]

[docs]
required = ["docs/design/README.md"]

[reconcile]
risk_paths = ["migrations/"]
"""


class ExtensionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.profile_path = self.root / "docs/flow/profile.toml"
        self.write("README.md", "# r\n")
        self.write("docs/README.md", "# d\n")
        self.write("docs/design/README.md", "# design\n")
        self.write_profile('"demo"')
        self.write_extension("demo")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_profile(self, enabled: str) -> None:
        self.write("docs/flow/profile.toml", PROFILE.replace("__ENABLED__", enabled))

    def write_extension(self, name: str, text: str | None = None) -> None:
        body = (text or EXTENSION).replace("__NAME__", name)
        self.write(f"docs/flow/extensions/{name}/extension.toml", body)

    def load(self):
        return profile_mod.load(self.profile_path)

    def run_flow(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = flow.main(["--profile", str(self.profile_path), *args])
        return code, output.getvalue()

    def test_version_range(self) -> None:
        self.assertTrue(profile_mod.satisfies("0.2.0", ">=0.2,<0.3"))
        self.assertTrue(profile_mod.satisfies("0.2.9", "0.2"))
        self.assertFalse(profile_mod.satisfies("0.3.0", ">=0.2,<0.3"))
        self.assertFalse(profile_mod.satisfies("0.1.9", ">=0.2"))
        with self.assertRaises(profile_mod.ProfileError):
            profile_mod.satisfies("0.2.0", "banana")

    def test_merge_adds_without_replacing(self) -> None:
        profile = self.load()
        self.assertEqual(profile.gate["l1"], ["test", "demo_test"])
        self.assertEqual(profile.commands["demo_test"], "echo demo")
        self.assertIn("docs/design/README.md", profile.required_docs)
        self.assertIn("migrations/", profile.risk_paths)
        self.assertEqual(profile.extension_info[0]["source"], "project")
        self.assertEqual(profile.extension_info[0]["requires"], ">=0.3,<0.4")

    def test_command_collision_is_an_error(self) -> None:
        self.write_extension(
            "demo",
            EXTENSION.replace('demo_test = "echo demo"', 'test = "echo different"'),
        )
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load()
        self.assertIn("collides", str(caught.exception))

    def test_version_mismatch_is_an_error(self) -> None:
        self.write_extension("demo", EXTENSION.replace(">=0.3,<0.4", ">=0.4"))
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load()
        self.assertIn("requires lite-dev", str(caught.exception))

    def test_missing_requires_is_an_error(self) -> None:
        lines = [line for line in EXTENSION.splitlines() if not line.startswith("requires")]
        self.write_extension("demo", "\n".join(lines) + "\n")
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load()
        self.assertIn("requires", str(caught.exception))

    def test_unknown_extension_key_is_an_error(self) -> None:
        self.write_extension("demo", EXTENSION + '\n[design]\nrequired_for = ["L"]\n')
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load()
        self.assertIn("unknown key", str(caught.exception))

    def test_unknown_docs_key_is_an_error(self) -> None:
        self.write_extension(
            "demo",
            EXTENSION.replace('[docs]\nrequired = ["docs/design/README.md"]',
                              '[docs]\nrequired = ["docs/design/README.md"]\nforbidden = []'),
        )
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load()
        self.assertIn("[docs]", str(caught.exception))

    def test_missing_extension_is_an_error(self) -> None:
        self.write_profile('"missing"')
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load()
        self.assertIn("not found", str(caught.exception))

    def test_ambiguous_extension_is_an_error(self) -> None:
        self.write_profile('"go-service"')
        self.write_extension("go-service")
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load()
        self.assertIn("both", str(caught.exception))

    def test_extensions_command(self) -> None:
        code, output = self.run_flow("extensions")
        self.assertEqual(code, 0)
        self.assertIn("lite-dev 0.3.0", output)
        self.assertIn("demo 1.0.0", output)
        self.assertIn("gate l1 += demo_test", output)

    def test_bundled_extension_loads(self) -> None:
        self.write_profile('"go-service"')
        profile = self.load()
        self.assertEqual(profile.extension_info[0]["source"], "bundled")
        self.assertIn("go_build", profile.commands)
        self.assertEqual(profile.gate["l1"], ["test", "go_build"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
