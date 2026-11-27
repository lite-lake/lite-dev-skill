"""A workspace is several git repositories under one project root.

Covers the model that a single-repository project never exercised: an explicit
root, a control repository for the flow's own records, per-repository commands,
gate scoping, cross-repository change sets, per-repository release channels, and
the document rules a workspace needs (record stores, absolute and escaping
links).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent
REPO = SCRIPTS.parents[2]
SKILL = REPO / "skills/lite-dev"
FLOW = SKILL / "scripts/flow.py"
EXAMPLE = REPO / "examples/workspace"
sys.path.insert(0, str(SCRIPTS))

from flowlib import checks, commands, docs, identity, profile as profile_mod  # noqa: E402
from flowlib.errors import FlowError  # noqa: E402

PROFILE = """\
[project]
name = "ws"
language = "en"
root = "."
docs_dir = "docs"
work_dir = "docs/work"

[flow]
requires = ">=0.5.0,<0.6"

[id]
format = "{date}-{type}-{time}"

[workspace]
control = "docs"

[[workspace.repo]]
path = "svc-a"
mainline = "main"

[[workspace.repo]]
path = "svc-b"
mainline = "main"

[gate]
l1 = ["a_test", "b_test"]
l2 = ["a_test", "b_test", "ws_check"]
l3 = ["a_test", "b_test", "ws_check"]

[design]
required_for = ["L"]
require_confirmed = true
risk_paths = ["svc-a/migrations/"]
risk_exempt = ["docs/"]

[commands]
a_test = { dir = "svc-a", run = "echo a" }
b_test = { dir = "svc-b", run = "echo b" }
ws_check = "echo ws"

[docs]
required = ["docs/README.md"]
stores = ["docs/work", "docs/projects/*/prds"]

[release]
dir = "docs/releases"
gate_level = "l3"
mainline = "main"

[[release.channel]]
name = "svc-a"
repo = "svc-a"
mainline = "main"

[[release.channel]]
name = "svc-b"
repo = "svc-b"
mainline = "main"

[[release.group]]
name = "platform"
channels = ["svc-a", "svc-b"]

[reconcile]
risk_paths = ["svc-a/migrations/"]
"""


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


class WorkspaceCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve() / "ws"
        self.write("docs/README.md", "# docs\n")
        self.write("docs/AGENTS.md", "# agents\n")
        self.write("docs/flow/profile.toml", PROFILE)
        self.write("svc-a/app.txt", "a\n")
        self.write("svc-b/app.txt", "b\n")
        for repo in ("docs", "svc-a", "svc-b"):
            git(self.root / repo, "init", "-q", "-b", "main")
            git(self.root / repo, "add", "-A")
            git(self.root / repo, "commit", "-qm", f"init {repo}")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def load(self, text: str | None = None):
        if text is not None:
            self.write("docs/flow/profile.toml", text)
        return profile_mod.load(self.root / "docs/flow/profile.toml")

    def run_flow(self, *args: str):
        return subprocess.run(
            [sys.executable, str(FLOW), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=dict(os.environ, LITE_DEV_OWNER="ws-owner"),
        )


class ProfileWorkspaceTest(WorkspaceCase):
    def test_explicit_root_beats_docs_being_a_repository(self) -> None:
        # docs/ is itself a repository; discovery alone would stop there.
        discovered = profile_mod.resolve_root(
            self.root / "docs/flow/profile.toml", None
        )
        self.assertEqual(discovered, self.root / "docs")
        loaded = self.load()
        self.assertEqual(loaded.root, self.root)
        self.assertEqual(loaded.control_root, self.root / "docs")

    def test_paths_translate_between_workspace_and_repository(self) -> None:
        p = self.load()
        self.assertEqual(p.to_workspace("svc-a", "src/a.py"), "svc-a/src/a.py")
        self.assertEqual(p.to_workspace("", "src/a.py"), "src/a.py")
        self.assertEqual(p.to_repo("svc-a/src/a.py"), ("svc-a", "src/a.py"))
        self.assertEqual(p.to_repo("docs/work/x"), ("docs", "work/x"))
        self.assertEqual(p.control_relative("docs/work"), "work")
        self.assertTrue(p.workspace)

    def test_a_workspace_without_a_control_repository_is_refused(self) -> None:
        text = PROFILE.replace('control = "docs"', "").replace("[workspace]\n", "")
        shutil.rmtree(self.root / "docs/.git")
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load(text)
        self.assertIn("control is unset", str(caught.exception))

    def test_control_must_be_a_git_work_tree(self) -> None:
        shutil.rmtree(self.root / "docs/.git")
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load()
        self.assertIn("not a git work tree", str(caught.exception))

    def test_items_must_live_in_the_control_repository(self) -> None:
        text = PROFILE.replace('work_dir = "docs/work"', 'work_dir = "svc-a/work"')
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load(text)
        self.assertIn("outside [workspace] control", str(caught.exception))

    def test_nested_repositories_are_refused(self) -> None:
        text = PROFILE.replace('path = "svc-b"', 'path = "svc-a/app"')
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load(text)
        self.assertIn("overlaps", str(caught.exception))

    def test_a_command_dir_must_belong_to_a_declared_repository(self) -> None:
        text = PROFILE.replace('dir = "svc-b"', 'dir = "svc-c"')
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load(text)
        self.assertIn("not inside a declared repository", str(caught.exception))

    def test_table_commands_keep_run_and_dir(self) -> None:
        p = self.load()
        self.assertEqual(p.commands["a_test"], "echo a")
        self.assertEqual(p.command_dirs["a_test"], "svc-a")
        self.assertNotIn("ws_check", p.command_dirs)
        self.assertEqual(p.command_repo("a_test"), "svc-a")
        self.assertIsNone(p.command_repo("ws_check"))

    def test_channels_bind_to_repositories(self) -> None:
        p = self.load()
        channel = p.channel("svc-a")
        self.assertIsNotNone(channel)
        self.assertEqual(channel.repo, "svc-a")
        self.assertEqual(p.release_channels, ["svc-a", "svc-b"])

    def test_a_group_names_existing_channels(self) -> None:
        p = self.load()
        group = p.group("platform")
        self.assertIsNotNone(group)
        self.assertEqual(group.channels, ["svc-a", "svc-b"])

    def test_a_group_cannot_invent_a_channel(self) -> None:
        text = PROFILE.replace('channels = ["svc-a", "svc-b"]', 'channels = ["svc-a", "svc-c"]')
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load(text)
        self.assertIn("is not configured", str(caught.exception))
        self.assertIn("[[release.channel]]", str(caught.exception))

    def test_legacy_channel_list_means_the_control_repository(self) -> None:
        text = PROFILE.split("[[release.channel]]")[0]
        text = text.replace(
            '[release]\ndir = "docs/releases"',
            '[release]\nchannels = ["docs"]\ndir = "docs/releases"',
        )
        p = self.load(text)
        self.assertEqual(p.channel("docs").repo, "docs")

    def test_a_channel_pointing_at_an_undeclared_repository_is_refused(self) -> None:
        text = PROFILE.replace('repo = "svc-a"\nmainline = "main"', 'repo = "svc-c"')
        with self.assertRaises(profile_mod.ProfileError) as caught:
            self.load(text)
        self.assertIn("not in [[workspace.repo]]", str(caught.exception))

    def test_a_single_repository_project_stays_unchanged(self) -> None:
        text = """\
[project]
name = "solo"
language = "en"
docs_dir = "docs"
work_dir = "docs/work"

[flow]
requires = ">=0.5.0,<0.6"

[id]
format = "{date}-{type}-{time}"

[gate]
l1 = ["test"]

[commands]
test = "echo ok"

[docs]
required = []

[release]
channels = ["staging"]
dir = "docs/releases"
gate_level = "l1"
mainline = "main"
"""
        self.write("docs/flow/profile.toml", text)
        p = profile_mod.load(self.root / "docs/flow/profile.toml")
        self.assertEqual(p.root, self.root / "docs")
        self.assertEqual(p.control_path, "")
        self.assertFalse(p.workspace)
        self.assertEqual(p.to_workspace("", "docs/a.md"), "docs/a.md")


class GateScopeTest(WorkspaceCase):
    def test_path_prefixes_respect_directory_boundaries(self) -> None:
        self.assertEqual(checks.paths_matching(["svc-a/x"], ["svc-a"]), ["svc-a/x"])
        self.assertEqual(checks.paths_matching(["svc-a-tools/x"], ["svc-a"]), [])

    def test_a_dirty_repository_enters_the_scope(self) -> None:
        self.write("svc-b/app.txt", "changed\n")
        p = self.load()
        chosen = checks.scope(p, None)
        self.assertEqual(chosen.reason, "project-wide")
        item = None
        # An item with no commits anywhere falls back to worktree, then to all.
        from flowlib import artifacts

        self.write(
            "docs/work/2026-01/20260101-REQ-abcdef/item.md",
            "---\nid: 20260101-REQ-abcdef\ntitle: t\ntype: REQ\npriority: P2\n"
            "size: S\nmode: one-shot\nowner: o\ncreated: 2026-01-01\n"
            "closed:\nclosed_by:\n---\n\n## AC\n\n- [ ] AC01 x\n",
        )
        git(self.root / "docs", "add", "-A")
        git(self.root / "docs", "commit", "-qm", "item")
        self.write("svc-b/app.txt", "changed again\n")
        item = artifacts.all_items(p)[0]
        chosen = checks.scope(p, item, None)
        self.assertEqual(chosen.repos, ["svc-b"])
        self.assertEqual(chosen.reason, "worktree")

    def test_commits_scope_the_gate(self) -> None:
        p = self.load()
        self.write(
            "docs/work/2026-01/20260101-REQ-abcdef/item.md",
            "---\nid: 20260101-REQ-abcdef\ntitle: t\ntype: REQ\npriority: P2\n"
            "size: S\nmode: one-shot\nowner: o\ncreated: 2026-01-01\n"
            "closed:\nclosed_by:\n---\n\n## AC\n\n- [ ] AC01 x\n",
        )
        self.write("svc-a/feature.txt", "x\n")
        git(self.root / "svc-a", "add", "-A")
        git(self.root / "svc-a", "commit", "-qm", "feat 20260101-REQ-abcdef")
        from flowlib import artifacts

        item = artifacts.all_items(p)[0]
        chosen = checks.scope(p, item, None)
        self.assertIn("svc-a", chosen.repos)
        self.assertEqual(chosen.reason, "commits")

    def test_explicit_repo_accepts_the_control_shorthand(self) -> None:
        p = self.load()
        self.assertEqual(checks.scope(p, None, ["."]).repos, ["docs"])
        self.assertEqual(checks.scope(p, None, ["docs"]).repos, ["docs"])
        with self.assertRaises(FlowError) as caught:
            checks.scope(p, None, ["nope"])
        self.assertIn("not a declared repository", str(caught.exception))

    def test_plan_skips_out_of_scope_commands_and_keeps_workspace_steps(self) -> None:
        p = self.load()
        chosen = commands.plan(p, "l3", ["svc-a"])
        self.assertEqual(chosen.steps, ["a_test", "ws_check"])
        self.assertEqual(chosen.skipped, ["b_test"])

    def test_no_scoping_runs_every_step(self) -> None:
        p = self.load()
        chosen = commands.plan(p, "l3", None)
        self.assertEqual(chosen.steps, ["a_test", "b_test", "ws_check"])
        self.assertEqual(chosen.skipped, [])

    def test_changed_paths_prefix_each_repository(self) -> None:
        p = self.load()
        self.write("svc-a/one.txt", "1\n")
        self.write("svc-b/two.txt", "2\n")
        changed = checks.changed_paths(p, None)
        self.assertIn("svc-a/one.txt", changed.worktree)
        self.assertIn("svc-b/two.txt", changed.worktree)
        self.assertEqual(changed.unavailable, [])

    def test_risk_gate_sees_a_cross_repository_change(self) -> None:
        p = self.load()
        self.write("svc-a/migrations/001.sql", "select 1;\n")
        changed = checks.changed_paths(p, None)
        touched = checks.risk_paths_touched(p, changed.paths)
        self.assertEqual(touched, ["svc-a/migrations/001.sql"])


class DocumentWorkspaceTest(WorkspaceCase):
    def test_record_stores_are_excluded_from_the_index_graph(self) -> None:
        p = self.load()
        prds = self.write("docs/projects/app-x/prds/20260101-01-plan.md", "# plan\n")
        self.assertTrue(docs._excluded_from_index(p, prds))
        loose = self.write("docs/sops/note.md", "# note\n")
        self.assertFalse(docs._excluded_from_index(p, loose))

    def test_an_absolute_link_is_a_warning_not_an_error(self) -> None:
        p = self.load()
        self.write("docs/page.md", "[x](/etc/hosts)\n")
        errors, warnings = docs.problems(p)
        self.assertFalse([e for e in errors if "page.md" in e])
        self.assertTrue(any("absolute link target" in w for w in warnings))

    def test_a_link_that_escapes_the_root_is_a_warning(self) -> None:
        p = self.load()
        (self.root.parent / "outside.md").write_text("# outside\n", encoding="utf-8")
        self.write("docs/page.md", "[x](../../outside.md)\n")
        errors, warnings = docs.problems(p)
        self.assertFalse([e for e in errors if "page.md" in e])
        self.assertTrue(any("leaves the project root" in w for w in warnings))

    def test_a_cross_repository_link_inside_the_root_resolves(self) -> None:
        p = self.load()
        self.write("docs/page.md", "[x](../svc-a/app.txt)\n")
        errors, warnings = docs.problems(p)
        self.assertFalse([e for e in errors if "page.md" in e])
        self.assertFalse([w for w in warnings if "leaves the project root" in w])
        self.assertFalse([w for w in warnings if "absolute link target" in w])


class IdentityWorkspaceTest(WorkspaceCase):
    def test_owner_file_is_the_last_resort(self) -> None:
        p = self.load()
        self.write(".lite-dev/owner", "# per machine\nowner: Machine Owner\n")
        text = PROFILE.replace(
            'docs_dir = "docs"', 'docs_dir = "docs"\nowner_file = ".lite-dev/owner"'
        )
        self.write("docs/flow/profile.toml", text)
        p = profile_mod.load(self.root / "docs/flow/profile.toml")
        saved = os.environ.pop("LITE_DEV_OWNER", None)
        try:
            owner, source = identity.resolve_with_source_for(p)
        finally:
            if saved is not None:
                os.environ["LITE_DEV_OWNER"] = saved
        self.assertEqual(owner, "Machine Owner")
        self.assertEqual(source, ".lite-dev/owner")

    def test_git_config_of_the_control_repository_is_used(self) -> None:
        p = self.load()
        git(self.root / "docs", "config", "lite-dev.owner", "Repo Owner")
        saved = os.environ.pop("LITE_DEV_OWNER", None)
        try:
            owner, source = identity.resolve_with_source_for(p)
        finally:
            if saved is not None:
                os.environ["LITE_DEV_OWNER"] = saved
        self.assertEqual(owner, "Repo Owner")
        self.assertIn("git config", source)


class WorkspaceAcceptanceTest(WorkspaceCase):
    def test_a_workspace_runs_the_whole_flow(self) -> None:
        shutil.rmtree(self.root)
        shutil.copytree(EXAMPLE, self.root)
        for repo in ("docs", "svc-a", "svc-b"):
            git(self.root / repo, "init", "-q", "-b", "main")
            git(self.root / repo, "add", "-A")
            git(self.root / repo, "commit", "-qm", f"init {repo}")

        status = self.run_flow("status")
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        self.assertIn("control docs", status.stdout)
        self.assertIn("svc-a main", status.stdout)
        self.assertIn("svc-b main", status.stdout)

        check = self.run_flow("check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

        created = self.run_flow(
            "new", "--title", "label prefix", "--type", "REQ", "--size", "S"
        )
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        item_id = created.stdout.split("created ", 1)[1].split()[0]
        directory = next((self.root / "docs/work").glob(f"*/*{item_id}*"))

        item = (directory / "item.md").read_text(encoding="utf-8")
        item = item.replace("- Status: pending", "- Status: clarified")
        item = item.replace("- [ ] AC01 <observable outcome>", "- [x] AC01 a")
        item = item.replace("- [ ] AC02 <observable outcome>", "- [x] AC02 b")
        (directory / "item.md").write_text(item, encoding="utf-8")
        (directory / "test-report.md").write_text(
            "---\nitem: %s\n---\n\n## Result\n\n- Verdict: PASS\n\n## Evidence\n\n"
            "| AC | Command | Output |\n|---|---|---|\n"
            "| AC01 | svc-a tests | OK |\n| AC02 | svc-b tests | OK |\n" % item_id,
            encoding="utf-8",
        )
        self.write("svc-a/NOTES.md", "note\n")

        gate = self.run_flow("gate", "--level", "l1", "--work", item_id)
        self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
        self.assertIn("gate l1: scope worktree", gate.stdout)
        self.assertIn("skipped (not in scope): svc_b_test", gate.stdout)

        forced = self.run_flow(
            "gate", "--level", "l1", "--work", item_id, "--repo", "svc-b"
        )
        self.assertEqual(forced.returncode, 0, forced.stdout + forced.stderr)
        self.assertIn("svc_b_test [svc-b]", forced.stdout)

        full = self.run_flow("gate", "--level", "l3", "--work", item_id)
        self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
        self.assertIn("docs_check", full.stdout)

        done = self.run_flow("done", item_id)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("closed by: ws-owner", done.stdout)

        git(self.root / "svc-a", "add", "-A")
        git(self.root / "svc-a", "commit", "-qm", f"note {item_id}")
        git(self.root / "docs", "add", "-A")
        git(self.root / "docs", "commit", "-qm", f"item {item_id}")

        plan = self.run_flow("release", "--channel", "svc-a")
        self.assertEqual(plan.returncode, 0, plan.stdout + plan.stderr)
        self.assertIn("record: docs/releases/svc-a-", plan.stdout)

        recorded = self.run_flow(
            "release",
            "--channel",
            "svc-a",
            "--record",
            "--rollback",
            "revert the commit",
            "--note",
            "initial repository import",
        )
        self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)
        record = next((self.root / "docs/releases").glob("svc-a-*.md"))
        text = record.read_text(encoding="utf-8")
        self.assertIn("repo: svc-a", text)
        self.assertIn("source:", text)

        reconcile = self.run_flow("reconcile", "--channel", "svc-a")
        self.assertEqual(reconcile.returncode, 0, reconcile.stdout + reconcile.stderr)

    def test_a_missing_repository_is_reported_not_ignored(self) -> None:
        shutil.rmtree(self.root / "svc-b")
        gate = self.run_flow("gate", "--level", "l1")
        self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
        self.assertIn("svc-b", gate.stdout)
        self.assertIn("not a git work tree", gate.stdout)


if __name__ == "__main__":
    unittest.main()


DESIGN = """\
---
item: {item}
status: ready
---

# {item} design

## Handoff

- Goal: prefix labels
- Scope: svc-a only
- Out: no migration
- Verify: unit tests
- Rollback: revert the commit

## Diagram

```text
request -> label
```

## Confirmation

- Confirmed: yes
- Date: 2026-01-01
- Source: conversation

## Approach

Use the prefix from svc-a.

## Batches

| Batch | Goal | Repo | AC | Depends |
|---|---|---|---|---|
| B1 | prefix | svc-a | AC01 | — |
| B2 | passthrough | svc-b | AC02 | B1 |

## Impact

- Contracts: none

## Verification

| AC | Command | Environment | Evidence |
|---|---|---|---|
| AC01 | unit | - | test-report |
| AC02 | unit | - | test-report |

## Rollback

Revert the commit.

## Open Decisions

None
"""


class WorkspaceDiagnosticsTest(WorkspaceCase):
    def _item(self, size: str = "S", design: bool = False) -> str:
        item_id = "20260101-REQ-abcdef"
        directory = self.root / "docs/work/2026-01" / f"{item_id}-t"
        self.write(
            f"docs/work/2026-01/{item_id}-t/item.md",
            "---\n"
            f"id: {item_id}\ntitle: t\ntype: REQ\npriority: P2\nsize: {size}\n"
            "mode: one-shot\nowner: o\ncreated: 2026-01-01\nclosed:\nclosed_by:\n---\n\n"
            "## Clarify\n\n- Status: clarified\n\n"
            "## AC\n\n- [ ] AC01 a\n- [ ] AC02 b\n",
        )
        if design:
            (directory / "design.md").write_text(
                DESIGN.format(item=item_id), encoding="utf-8"
            )
        return item_id

    def test_check_names_a_repository_that_is_not_checked_out(self) -> None:
        shutil.rmtree(self.root / "svc-b")
        result = self.run_flow("check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("svc-b is not checked out here", result.stdout)

    def test_check_is_quiet_when_every_repository_is_present(self) -> None:
        result = self.run_flow("check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("is not checked out here", result.stdout)

    def test_a_batch_handoff_names_its_repository_in_the_gate_command(self) -> None:
        item_id = self._item(size="L", design=True)
        result = self.run_flow("handoff", item_id, "--batch", "B1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--repo svc-a", result.stdout)

    def test_a_repository_that_is_not_a_work_tree_is_reported(self) -> None:
        shutil.rmtree(self.root / "svc-b/.git")
        result = self.run_flow("check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("svc-b is not a git work tree", result.stdout)

    def test_status_repo_filters_items_by_history(self) -> None:
        item_id = self._item()
        self.write("svc-a/marker.txt", "x\n")
        git(self.root / "svc-a", "add", "-A")
        git(self.root / "svc-a", "commit", "-qm", f"work {item_id}")
        self.write("docs/work/2026-01/x.txt", "x\n")
        git(self.root / "docs", "add", "-A")
        git(self.root / "docs", "commit", "-qm", "item")

        mine = self.run_flow("status", "--repo", "svc-a")
        self.assertEqual(mine.returncode, 0, mine.stdout + mine.stderr)
        self.assertIn(item_id, mine.stdout)
        self.assertIn("filter  repo svc-a", mine.stdout)

        other = self.run_flow("status", "--repo", "svc-b")
        self.assertEqual(other.returncode, 0, other.stdout + other.stderr)
        self.assertNotIn(item_id, other.stdout)

    def test_status_repo_refuses_an_undeclared_repository(self) -> None:
        result = self.run_flow("status", "--repo", "nope")
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a declared repository", result.stdout)


class WorkspaceReleaseGroupTest(WorkspaceCase):
    def setUp(self) -> None:
        super().setUp()
        shutil.rmtree(self.root)
        shutil.copytree(EXAMPLE, self.root)
        for repo in ("docs", "svc-a", "svc-b"):
            git(self.root / repo, "init", "-q", "-b", "main")
            git(self.root / repo, "add", "-A")
            git(self.root / repo, "commit", "-qm", f"init {repo}")

    def record_group(self, *extra: str):
        return self.run_flow(
            "release",
            "--group",
            "platform",
            "--record",
            "--rollback",
            "revert the commits",
            "--note",
            "initial repository import",
            *extra,
        )

    def test_a_group_records_each_channel_and_one_index(self) -> None:
        result = self.record_group()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # One gate run covers every channel; each record repeats its summary.
        self.assertEqual(result.stdout.count("gate l3: PASS\n"), 1, result.stdout)

        releases = sorted((self.root / "docs/releases").glob("*.md"))
        names = [path.name for path in releases]
        self.assertTrue(any(name.startswith("svc-a-") for name in names), names)
        self.assertTrue(any(name.startswith("svc-b-") for name in names), names)
        index = [path for path in releases if path.name.startswith("group-platform-")][0]
        text = index.read_text(encoding="utf-8")
        self.assertIn("group: platform", text)
        self.assertIn("| svc-a | svc-a |", text)
        self.assertIn("| svc-b | svc-b |", text)
        # An index is not a release: it carries no source of its own.
        self.assertNotIn("source:", text)

        listing = self.run_flow("release")
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        self.assertIn("group platform: svc-a, svc-b", listing.stdout)
        self.assertIn("svc-a: last", listing.stdout)

        reconcile = self.run_flow("reconcile", "--channel", "svc-a")
        self.assertEqual(
            reconcile.returncode, 0, reconcile.stdout + reconcile.stderr
        )

    def test_the_index_is_not_part_of_a_chain(self) -> None:
        first = self.record_group()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        plan = self.run_flow("release", "--channel", "svc-a")
        self.assertEqual(plan.returncode, 0, plan.stdout + plan.stderr)
        self.assertNotIn("previous: none", plan.stdout)

    def test_a_group_release_names_the_channel_that_blocks_it(self) -> None:
        self.write("svc-b/blocked.txt", "x\n")
        result = self.record_group()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("svc-b: ", result.stdout)
        self.assertIn("repository is dirty", result.stdout)

    def test_channel_and_group_are_mutually_exclusive(self) -> None:
        result = self.run_flow(
            "release", "--group", "platform", "--channel", "svc-a"
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("pick one", result.stdout)

    def test_an_unknown_group_lists_the_configured_ones(self) -> None:
        result = self.run_flow("release", "--group", "nope")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown release group", result.stdout)
        self.assertIn("platform", result.stdout)

    def test_an_optional_repository_may_be_absent(self) -> None:
        profile_path = self.root / "docs/flow/profile.toml"
        text = profile_path.read_text(encoding="utf-8")
        text = text.replace(
            'path = "svc-b"\nmainline = "main"',
            'path = "svc-b"\nmainline = "main"\nrequired = false',
        )
        profile_path.write_text(text, encoding="utf-8")
        shutil.rmtree(self.root / "svc-b")

        check = self.run_flow("check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertNotIn("svc-b is not checked out here", check.stdout)

        status = self.run_flow("status")
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        self.assertNotIn("not checked out here", status.stdout)
