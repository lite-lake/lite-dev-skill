# Workspaces: one root, several repositories

A workspace is a directory that holds several git repositories and is not itself
one. The common shape is a root with `docs/` plus one or more code
repositories, each with its own remote, branch, and gate. lite-dev supports it
with four things a single-repository project never needs: an explicit root, a
control repository, declared repositories, and per-repository channels.

Omit `[workspace]` and nothing changes: one root, one repository, the same
output as before.

## The model

| Name | Meaning |
|---|---|
| `[project] root` | The path base. Every configured path is relative to it. |
| `[workspace] control` | The repository that carries work items, release records, and the gate ledger. |
| `[[workspace.repo]]` | A repository whose changes and commands the flow inspects. |
| Workspace path | `svc-a/src/main.go` — the only namespace reports use. |

```toml
[project]
root = "."
docs_dir = "docs"
work_dir = "docs/work"

[workspace]
control = "docs"

[[workspace.repo]]
path = "svc-a"
mainline = "main"
```

Why an explicit root: root discovery walks up to the nearest repository. When
`docs/` is itself a clone, that walk stops there and every item lands in
`docs/docs/work`. `root` is relative to the directory that holds `docs/`, so `.`
means the obvious thing.

Why a control repository: work items, release records, and the gate ledger need
one commit graph. `work_dir` and `release_dir` must live inside `control` — the
loader refuses a profile where they do not.

## The gate runs where the change is

A command with a `dir` belongs to a repository. The gate picks a **scope** and
runs only the commands inside it; a command without a `dir` is workspace-level
and always runs.

```toml
[commands]
svc_a_test = { dir = "svc-a", run = "go test ./..." }
docs_check = "python3 docs/tools/check_all.py"

[gate]
l1 = ["svc_a_test", "docs_check"]
```

Scope is decided in this order, and the gate prints which rule it used:

1. `--repo <path>` (repeatable; `.` is the control repository) — you said so.
2. Repositories whose history mentions the item id.
3. Repositories with uncommitted work.
4. The design's `## Batches` **Repo** column.
5. Everything, with a warning. Never silently.

A repository that is declared but not checked out is named as unavailable, and
the level says it did not inspect it. Missing output is loud; empty output is
not evidence.

## Change detection spans repositories

`changed_paths` visits every declared repository and prefixes each path with its
repository, so one risk list covers the whole workspace:

```toml
[design]
risk_paths = ["svc-a/migrations/", "svc-b/schema/"]
risk_exempt = ["docs/"]
```

A prefix is a directory, not a string: `svc-a` does not cover `svc-a-tools/`.
A repository that cannot be read is reported, not treated as an empty change.

## Releases: one channel per repository

A release record points at a commit, and a commit belongs to one repository, so
a channel names its repository:

```toml
[[release.channel]]
name = "svc-a"
repo = "svc-a"
mainline = "main"
```

The chain rule is unchanged — one chain per channel, ordered by one commit
graph — but the graph is the channel's repository. A record carries `repo:`, and
a record written before this field existed means the control repository, so old
record stores keep working.

A change that ships several repositories produces one record per channel on the
same day. `--record` refuses when the channel's repository or the control
repository is dirty; another repository being dirty is a warning, not a block.

## Documents in a workspace

- `docs_dir` is the document tree. `[docs] surfaces` adds package-level
  document roots; each needs a `README.md` reachable from the root index.
- `[docs] stores` names record stores and asset libraries (`docs/projects/*/prds`,
  `docs/resources`). They are found through `status`, the commit graph, or a
  catalogue — not by following links — so they are not asked for an index.
- A cross-repository link that resolves inside the project is fine. One that
  leaves the project root is a warning (`escape`). An absolute path is a warning
  (`absolute`): it resolves on one machine only.
- Both are bounded silences, not switches. Fix the link or register
  `[[exempt]]` with a reason and an expiry.

## Identity when the root is not a repository

`git config lite-dev.owner` is read in the control repository first, then the
root. When neither applies, `[project] owner_file` names an untracked file
holding the name on that machine. `user.name` is still never used, and
`whoami` still prints the source.

## Adopting a workspace

1. Put the profile where every repository can discover it —
   `<root>/docs/flow/profile.toml`. The search walks up, so `flow.py status`
   works from inside any repository.
2. Set `root`, `control`, and one `[[workspace.repo]]` per repository. Run
   `check` and read the errors before adding commands.
3. Name the record stores. This is the step that turns a large document tree
   from noise into a signal.
4. Add `dir` commands repository by repository, starting with the cheapest
   meaningful one. Keep `l1` cheap: it now scales with the number of
   repositories a change touches, not with the size of the workspace.
5. Bind channels only after `check` is clean.
6. `init --baseline` in the control repository, so history before adoption is a
   baseline and not debt.

## What it does not do

- No parallel gate execution. Levels run their steps in order and stop at the
  first failure.
- No nested repositories: declare the outermost one, or changes are counted
  twice.
- No second work-item store: items live in the control repository.
- No task-board integration. An item may carry `prd:` and `board:` pointers, but
  the board remains the authority for who holds a task.
