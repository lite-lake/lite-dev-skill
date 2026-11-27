"""Tests for scripts/push_mirror.py.

Two local bare repositories stand in for GitHub and the cnb replica, so the
suite exercises real git with no network and no credentials.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "push_mirror.py"
HOOKS = Path(__file__).resolve().parents[2] / ".githooks"
ZERO = "0" * 40


class MirrorTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        base = self.base
        self.github = base / "github.git"
        self.cnb = base / "cnb.git"
        self.work = base / "work"
        # A clean environment: no user identity to depend on, no global hooks.
        self.env = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_AUTHOR_NAME": "Mirror Test",
            "GIT_AUTHOR_EMAIL": "mirror@example.com",
            "GIT_COMMITTER_NAME": "Mirror Test",
            "GIT_COMMITTER_EMAIL": "mirror@example.com",
        }
        self.git("init", "-q", "--bare", str(self.github), cwd=base, check=True)
        self.git("init", "-q", "--bare", str(self.cnb), cwd=base, check=True)
        self.git("init", "-q", "-b", "main", str(self.work), cwd=base, check=True)
        self.git("remote", "add", "origin", str(self.github))
        self.git("remote", "add", "origin-cnb", str(self.cnb))

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args, check=False, cwd=None):
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd or self.work),
            text=True,
            capture_output=True,
            env=self.env,
            stdin=subprocess.DEVNULL,
        )
        if check and result.returncode != 0:
            self.fail(f"git {' '.join(args)} failed: {result.stderr}")
        return result

    def commit(self, name="a.txt", text="one") -> str:
        (self.work / name).write_text(text)
        self.git("add", "-A", check=True)
        self.git("commit", "-qm", f"add {name}", check=True)
        return self.git("rev-parse", "HEAD", check=True).stdout.strip()

    def refs(self, remote: str) -> dict[str, str]:
        result = self.git("ls-remote", remote, check=True)
        refs = {}
        for line in result.stdout.splitlines():
            sha, _, ref = line.partition("\t")
            refs[ref] = sha
        return refs

    def run_script(self, *args, stdin=""):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=str(self.work),
            input=stdin,
            text=True,
            capture_output=True,
            env=self.env,
        )

    def hook(self, *lines, remote="origin"):
        stdin = "".join(f"{line}\n" for line in lines)
        return self.run_script("hook", remote, str(self.github), stdin=stdin)

    @staticmethod
    def line(ref: str, sha: str) -> str:
        return f"{ref} {sha} {ref} {ZERO}"

    @staticmethod
    def deletion(ref: str) -> str:
        return f"(delete) {ZERO} {ref} {ZERO}"

    # -- check ---------------------------------------------------------

    def test_check_passes_when_replica_matches(self):
        self.commit()
        self.git("push", "-q", "origin", "main", check=True)
        self.assertEqual(self.run_script("--sync").returncode, 0)

        result = self.run_script("--check")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("match origin", result.stdout)

    def test_check_names_the_drift_and_the_repair(self):
        self.commit()
        self.git("push", "-q", "origin", "main", check=True)

        result = self.run_script("--check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("missing", result.stdout)
        self.assertIn("refs/heads/main", result.stdout)
        self.assertIn("--sync", result.stdout)

    def test_check_reports_a_ref_the_replica_has_alone(self):
        sha = self.commit()
        self.git("push", "-q", "origin", "main", check=True)
        self.git("push", "-q", "origin-cnb", f"{sha}:refs/heads/stray", check=True)

        result = self.run_script("--check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("extra", result.stdout)
        self.assertIn("refs/heads/stray", result.stdout)

    def test_check_ignores_pull_request_refs(self):
        sha = self.commit()
        self.git("push", "-q", "origin", "main", check=True)
        self.git("update-ref", "refs/pull/1/head", sha, cwd=self.github, check=True)
        self.assertEqual(self.run_script("--sync").returncode, 0)

        self.assertEqual(self.run_script("--check").returncode, 0)
        self.assertNotIn("refs/pull", self.refs(str(self.cnb)))

    def test_check_explains_an_unreachable_remote(self):
        self.git("remote", "remove", "origin-cnb", check=True)

        result = self.run_script("--check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("git remote -v", result.stderr)

    # -- sync ----------------------------------------------------------

    def test_sync_sends_branches_and_annotated_tags(self):
        sha = self.commit()
        self.git("tag", "-a", "v0.1.0", "-m", "release", check=True)
        self.git("push", "-q", "origin", "main", check=True)
        self.git("push", "-q", "origin", "v0.1.0", check=True)

        result = self.run_script("--sync")

        self.assertEqual(result.returncode, 0, result.stderr)
        replica = self.refs(str(self.cnb))
        self.assertEqual(replica["refs/heads/main"], sha)
        tag = self.git("rev-parse", "v0.1.0", check=True).stdout.strip()
        self.assertEqual(replica["refs/tags/v0.1.0"], tag)

    def test_sync_prunes_refs_github_does_not_have(self):
        sha = self.commit()
        self.git("push", "-q", "origin", "main", check=True)
        self.git("push", "-q", "origin-cnb", f"{sha}:refs/heads/stray", check=True)

        result = self.run_script("--sync")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("refs/heads/stray", self.refs(str(self.cnb)))

    def test_sync_refuses_a_replica_ref_it_cannot_fast_forward(self):
        self.commit()
        self.git("push", "-q", "origin", "main", check=True)
        self.git("push", "-q", "origin-cnb", "main", check=True)
        # A different root: origin's main is rewritten, so the replica's main
        # is not an ancestor of it.
        self.git("checkout", "-q", "--orphan", "rewritten", check=True)
        self.commit("b.txt", "two")
        self.git("branch", "-M", "rewritten", "main", check=True)
        self.git("push", "-q", "--force", "origin", "main", check=True)

        refused = self.run_script("--sync")

        self.assertEqual(refused.returncode, 1)
        self.assertIn("--sync --force", refused.stderr)

        forced = self.run_script("--sync", "--force")

        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertEqual(
            self.refs(str(self.cnb))["refs/heads/main"],
            self.git("rev-parse", "main").stdout.strip(),
        )

    # -- hook ----------------------------------------------------------

    def test_hook_mirrors_a_branch(self):
        sha = self.commit()

        result = self.hook(self.line("refs/heads/main", sha))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("refs/heads/main", result.stdout)
        self.assertEqual(self.refs(str(self.cnb))["refs/heads/main"], sha)

    def test_hook_mirrors_a_tag_object(self):
        self.commit()
        self.git("tag", "-a", "v0.2.0", "-m", "release", check=True)
        tag = self.git("rev-parse", "v0.2.0", check=True).stdout.strip()

        result = self.hook(self.line("refs/tags/v0.2.0", tag))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.refs(str(self.cnb))["refs/tags/v0.2.0"], tag)

    def test_hook_mirrors_a_deletion(self):
        sha = self.commit()
        self.git("push", "-q", "origin", "main", check=True)
        self.assertEqual(self.run_script("--sync").returncode, 0)

        result = self.hook(self.deletion("refs/heads/main"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("refs/heads/main", self.refs(str(self.cnb)))

    def test_hook_does_not_re_enter_for_the_replica(self):
        sha = self.commit()

        result = self.hook(self.line("refs/heads/main", sha), remote="origin-cnb")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.refs(str(self.cnb)), {})

    def test_hook_is_inert_without_a_replica_remote(self):
        sha = self.commit()
        self.git("remote", "remove", "origin-cnb", check=True)

        result = self.hook(self.line("refs/heads/main", sha))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_hook_leaves_the_replica_alone_when_origin_would_reject(self):
        self.commit()
        self.git("push", "-q", "origin", "main", check=True)
        self.assertEqual(self.run_script("--sync").returncode, 0)
        accepted = self.refs(str(self.cnb))["refs/heads/main"]
        # Commit on main, push it, then diverge locally from the old tip.
        second = self.commit("b.txt", "two")
        self.git("push", "-q", "origin", "main", check=True)
        self.git("reset", "-q", "--hard", "HEAD~1", check=True)
        divergent = self.commit("c.txt", "three")
        self.assertNotEqual(divergent, second)

        result = self.hook(self.line("refs/heads/main", divergent))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would reject", result.stderr)
        self.assertEqual(self.refs(str(self.cnb))["refs/heads/main"], accepted)

    def test_hook_fails_with_the_repair_command_when_the_replica_is_down(self):
        sha = self.commit()
        self.git("remote", "set-url", "origin-cnb", str(self.work / "unreachable.git"))
        self.git("push", "-q", "origin", "main", check=True)

        result = self.hook(self.line("refs/heads/main", sha))

        self.assertEqual(result.returncode, 1)
        self.assertIn("not updated", result.stderr)
        self.assertIn("--sync", result.stderr)

    def test_hook_ignores_empty_input(self):
        self.commit()

        self.assertEqual(self.hook().returncode, 0)

    # -- through the real hook -----------------------------------------

    def install_hook(self):
        """Put the hook and its script in the clone, as a real clone has them."""
        hooks = self.work / ".githooks"
        hooks.mkdir()
        shutil.copy2(HOOKS / "pre-push", hooks / "pre-push")
        (self.work / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.work / "scripts" / "push_mirror.py")
        self.git("config", "core.hooksPath", str(hooks), check=True)

    def push(self, *args, timeout=60):
        """A git push that runs .githooks/pre-push, which is what git does."""
        return subprocess.run(
            ["git", "push", *args],
            cwd=str(self.work),
            text=True,
            capture_output=True,
            env=self.env,
            timeout=timeout,
        )

    def test_git_push_mirrors_in_the_same_command(self):
        self.install_hook()
        sha = self.commit()

        result = self.push("origin", "main")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("origin-cnb", result.stdout + result.stderr)
        self.assertEqual(self.refs(str(self.cnb))["refs/heads/main"], sha)

    def test_git_push_follow_tags_mirrors_the_release_tag(self):
        self.install_hook()
        sha = self.commit()
        self.git("tag", "-a", "v0.3.0", "-m", "release", check=True)
        tag = self.git("rev-parse", "v0.3.0", check=True).stdout.strip()

        result = self.push("origin", "--follow-tags", "main")

        self.assertEqual(result.returncode, 0, result.stderr)
        replica = self.refs(str(self.cnb))
        self.assertEqual(replica["refs/heads/main"], sha)
        self.assertEqual(replica["refs/tags/v0.3.0"], tag)

    def test_git_push_does_not_re_enter_its_own_dry_run(self):
        # The hook runs a dry run against origin, and git runs hooks for dry
        # runs too: without the guard this test hangs instead of pushing.
        self.install_hook()
        sha = self.commit()
        self.git("push", "-q", "origin", "main", check=True)
        self.assertEqual(self.run_script("--sync").returncode, 0)
        self.commit("b.txt", "two")

        result = self.push("origin", "main", timeout=60)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.refs(str(self.cnb))["refs/heads/main"],
            self.git("rev-parse", "HEAD").stdout.strip(),
        )

    def test_direct_push_to_the_replica_stays_there(self):
        self.install_hook()
        sha = self.commit()

        result = self.push("origin-cnb", "main")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.refs(str(self.cnb))["refs/heads/main"], sha)
        self.assertNotIn("refs/heads/main", self.refs(str(self.github)))


if __name__ == "__main__":
    unittest.main()
