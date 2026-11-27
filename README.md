# lite-dev-skill

**English** | [简体中文](README.zh.md)

`lite-dev` is an agent-first development flow that ships as an installable
**skill**: a protocol, templates, and a small profile-driven tool. Install it,
write one profile, and an agent can run a change from clarification to recorded
completion without inventing process.

Repository: <https://github.com/lite-lake/lite-dev-skill>
Mirror for mainland China: <https://cnb.cool/lite-lake/lite-dev-skill>
(clone from either; issues and pull requests live on GitHub)

- Single repository by default; a workspace of several repositories is one table away.
- Zero install: Python 3.11+ standard library only (`tomllib`). No dependencies.
- The agent is the runtime. The skill is the entry point; scripts and references
  load on demand.

## What it is

A closed loop with a machine at the end of it:

```text
request
  -> clarify (<=5 questions, once)
  -> work item (item.md, AC)
  -> design (when profile.required_for or risk_paths says so; M by default)
  -> batches (B1..Bn, ordered, every AC covered; a disjoint group may run at once)
  -> implement -> verify (each AC accepted once, evidence appended) -> commit, per batch
  -> gate (the project's own commands, not ours)
  -> release record (optional channel)
  -> done (AC checked, evidence, gate PASS, identity)
```

Three things make it different from a checklist:

1. **Status is derived, never written.** `flow.py` reads the files and tells you
   where the item is. No status field to drift.
2. **The gate is the project's commands.** lite-dev defines the ladder (l1/l2/l3)
   and when a level is enough; it never invents a build command.
3. **Bypass is visible, not blocked.** Commits without work items are recorded as
   release debt instead of turning the flow into a police state.

## What it is not

- Not a task tracker, a spec generator, or a project management tool.
- Not a replacement for your tests. It decides *when* they run and *what counts
  as evidence*.
- Not a build orchestrator. It runs the commands you configure, scoped to the
  repositories a change touches; it does not fetch, build images, or deploy.

## Quick start

1. **Install the skill.** Clone the repository, then put `skills/lite-dev/` where
   your agent harness discovers skills (for example `.claude/skills/`,
   `.agents/skills/`, or a user-level skills directory), or point your `AGENTS.md`
   at `skills/lite-dev/SKILL.md`.

   ```bash
   git clone https://github.com/lite-lake/lite-dev-skill.git
   # mainland China: git clone https://cnb.cool/lite-lake/lite-dev-skill.git
   ```

2. **Scaffold the project, then wire it.**

   ```bash
   python3 <skill>/scripts/flow.py init
   python3 <skill>/scripts/flow.py init --plan   # proposals, when a runner is recognisable
   ```

   `init` writes `docs/flow/profile.toml` (pinned to this install's version,
   with the detected mainline), the required entry documents, and a routing
   block in `AGENTS.md` (after the title when one exists). Existing files are
   never replaced. It ends by listing the adoption ladder and the one next
   command. `--plan` reads the repository — a Makefile target, package scripts,
   pytest or unittest evidence, `go.mod`, `Cargo.toml`, CI — and proposes
   profile values; `--apply <id>` writes the one you choose, and editing
   `[commands]` by hand works too. A new profile's `test` command is the value
   `!unconfigured`, so `check` says so and `gate` refuses to run until it is
   wired.

3. **Set your identity.** One value per person, on every machine:

   ```bash
   git config --global lite-dev.owner "Your Name"
   ```

   `new` refuses to guess: no owner, no item. `LITE_DEV_OWNER` and `--owner`
   override it; `flow.py whoami` shows what is in effect on this machine.

4. **Ask the agent.** "Set up lite-dev in this repo", or go straight to
   "implement X". The skill triggers on implementation, fix, design, and release
   requests. `flow.py design <ID>` scaffolds the design when one is required.
   Every item closes with a cumulative `test-report.md`, a recorded full-level
   gate PASS, and an identity.

5. **Check anytime.**

   ```bash
   python3 <skill>/scripts/flow.py status --mine
   python3 <skill>/scripts/flow.py check
   ```

## Adopting an existing project

A project that already has code, tests, and opinions does not start over. It
enters one derived ladder — no adoption state is stored, so every clone sees the
same place and re-running a command is always safe:

| Rung | Meaning | Blocks? |
|---|---|---|
| S0 | scaffolded: the profile loads | — |
| S1 | wired: every gate level runs a configured command | **yes** |
| S2 | bounded: `check` has no errors and no inert switch | no |
| S3 | anchored: a baseline or a release record exists | no |
| S4 | owned: this clone resolves an identity | no |
| S5 | practiced: one item has closed through `done` | no |

Only S1 blocks, so the next change is never held hostage by the rest of the
backlog. Refusal is per level: a wired `l1` iterates while `l3` is still being
wired, and `done` waits for the strictest level. `status` prints the ladder and
the one command that advances it.

1. **`flow.py init --adopt`.** It keeps every file it finds, inserts the routing
   block, reports the existing tree (drift is a warning; a missing required
   document or a broken link is an error), and prints proposals. Apply the ones
   you want: `flow.py init --apply commands.test`. Proposals never write
   themselves, and one whose expected value changed is refused.
2. **Commit the scaffold, then `flow.py init --baseline`.** It records `HEAD` as
   `[reconcile] baseline`; from then on `reconcile` reports only work that
   bypassed the flow, never the history that predates adoption.
3. **Make the first item the one that converges facts.** The register of
   documents with no single authority is the item that pays for the rest: it
   produces the design template the following items copy.

Drift that cannot be fixed yet is recorded as one `[[exempt]]` (a check, a path, a
reason, an expiry) — `--plan` prints the shape, and you fill in the reason and
the date. Profiles from an older install are migrated with
`flow.py init --upgrade`, which reads the pin it cannot load and proposes the
version contract (`requires` and `reviewed`). Details:
[adoption.md](skills/lite-dev/references/adoption.md).

Nothing is backfilled: no retroactive work items, no rewritten history. If a
change cannot wait for an item, the release `--note` records the debt, and
`reconcile` keeps it visible.

## Version policy

`init` pins two values in `docs/flow/profile.toml`:

```toml
[flow]
requires = ">=X.Y.0,<X+1.0"   # hard window: same major, derived by init
reviewed = "X.Y.Z"            # the exact version this project last reconciled with
```

The version has three components, and each means a different amount of work:

| Change | Meaning | What happens |
|---|---|---|
| Z (patch) | compatible fix | loads; no warning |
| Y (minor) | may be incompatible | loads; `status`, `check`, and `gate` warn with the CHANGELOG range; `init --upgrade --apply flow.reviewed` records the review |
| X (major) | contract change | refuses to load; `init --upgrade` shows the breaking sections and the checklist; applying needs `--accept-major` |

`flow.py version` answers what the machine runs, what the project reviewed, and
which case applies — even when the profile cannot load. The review steps and the
major checklist are in
[upgrade.md](skills/lite-dev/references/upgrade.md). The skill ships both
changelogs so a copied install can read them offline.

## Repository layout

```text
spec/invariants.md          entry point for readers; points at the canonical file
scripts/check_release.py    version/changelog/template/extension consistency gate
skills/lite-dev/            the installable skill: everything is inside
  SKILL.md                  entry point: principles, routing, stop conditions, red lines
  profile.template.toml     copy to docs/flow/profile.toml
  CHANGELOG.md / .zh.md     the skill's release history, bundled for the upgrade review
  references/               invariants + depth, loaded per situation
                            (adoption.md covers introducing the flow;
                            workspace.md covers one root, several repositories)
  templates/                item, design, test report, implementation, release,
                            release group, retro, decision
  extensions/               bundled add-ons (go-service, security-scan, deploy-lane)
  scripts/flow.py           init / new / claim / whoami / status / version / check /
                            design / design-ready / gate / done / drop / handoff /
                            archive / unarchive / release / reconcile / extensions
  scripts/flowlib/          profile, identity, artifacts, checks, document hygiene,
                            gate ledger, handoff, archive, command runner,
                            scaffolding, adoption ladder and proposals,
                            atomic writes and the writer lock
  scripts/tests/            unit tests and an end-to-end acceptance test
examples/minimal/           a working single-repo project
examples/workspace/         a working workspace: one root, two repositories
```

## What is deterministic, what is not

| Deterministic (`flow.py`) | Model |
|---|---|
| scaffolding: profile, entry documents, `AGENTS.md` router, mainline | what the project actually is |
| adoption rungs derived from files; proposals from repository evidence (`plan` → `apply`) | which command the project actually wants |
| time-ordered id allocation, directory scaffold | clarifying questions, trade-offs |
| frontmatter / AC / batch parsing | design narrative and diagrams |
| derived status | batch decomposition |
| required fields, links, AC↔batch↔verification, which batch accepts each AC | code and tests |
| evidence completeness for every item (one command and output per AC, verdict) | whether the evidence is sufficient |
| design gate (confirmation, decision defaults, rollback, gaps, ordered batch graph, parallel-group disjointness) | failure diagnosis |
| running profile commands, exit codes, recorded full-level PASS | black-box acceptance judgement |
| release chain ordered by commit ancestry; bookkeeping vs debt | deployment judgement |
| handoff prompt assembled from the artifacts | the judgement behind the next step |
| document reachability, index-graph connectivity, entry-document pins, archive index | whether the prose is true |
| decision chains, exemption expiry, item staleness from git | what should be cleaned up or re-reviewed |
| risk-path design gate over the whole history, each hit labelled worktree or committed | how risky a change actually is |
| per-clone gate freshness, the strictest level `done` will close on, the running version | when a recorded PASS is still current |
| identity, claim/takeover, archived read-only lifecycle | who is trusted to change what |

Anything left of the line is a script because agents self-report it badly.
Anything right of the line is prose because a script would get it wrong.

## Two design decisions worth knowing

- **Headings are a contract.** Artifact headings (`## AC`, `## Batches`, ...) stay
  in English so parsing is language-independent. Write the prose in any language;
  `project.language` only affects generated prose.
- **TOML, not YAML.** `tomllib` is in the standard library, so the tool has no
  dependencies. The profile contains shell commands: treat it as trusted project
  configuration, not as data from an untrusted source.

## Releases and extensions

```bash
flow.py release --channel staging      # plan: gate, commits, debt, record path
flow.py release --channel staging --record --rollback "..." --note "..."
flow.py release --channel staging --record --rollback "..." --confirm "..." --confirmed-by "..."
flow.py reconcile                      # advisory debt report; never blocks
flow.py extensions                     # what each add-on contributes
```

`--record` runs the gate itself; a previous run is not evidence. It refuses a
dirty tree, a branch other than `release.mainline`, a clone behind its upstream,
an empty rollback, a source that does not descend from the recorded tip, or
commits without work items that are not written into `--note`. Commits that only
touch the profile, work items, or release records are bookkeeping, not debt. With
`[release] confirm_risk_paths`, a range that touches `[design] risk_paths` also
needs `--confirm`; `--confirmed-by` names the authorizer when it is not the
recorder. The record keeps the human's words, not only the rollback.

Extensions are declarative and additive: commands, gate steps, required docs,
risk paths. The loader rejects command collisions, unknown keys, and an
incompatible `requires` range. A bundled extension may ship a script and name it
with `{skill}`, which the loader expands to the installed skill directory.

Bundled: `go-service` (build/vet/test and Go risk paths; build output goes to a
temp directory), `security-scan` (fails on credentials in the index or untracked
non-ignored files), `deploy-lane` (validates deployment manifests).

## One root, several repositories

A workspace is a directory that holds several clones and is not itself one. It
declares four things — an explicit root, a control repository, the declared
repositories, and (when it releases) per-repository channels — and everything
else follows:

```toml
[project]
root = "."                  # explicit; discovery would stop at docs/ (its own clone)
docs_dir = "docs"
work_dir = "docs/work"

[workspace]
control = "docs"            # items, release records, and the gate ledger live here

[[workspace.repo]]
path = "svc-a"
mainline = "main"

[commands]
svc_a_test = { dir = "svc-a", run = "go test ./..." }
```

- **The gate runs where the change is.** A command with `dir` belongs to a
  repository; the gate scopes to the repositories the change touches (commits,
  then the worktree, then the design's Repo column) and names what it skipped or
  could not inspect. `gate --repo svc-a` overrides the scope, and
  `status --repo svc-a` lists the items that repository's history mentions. This is what keeps
  `l1` cheap without weakening it.
- **Change detection spans repositories.** Every path is prefixed with its
  repository, so `[design] risk_paths = ["svc-a/migrations/"]` is one list for
  the whole workspace.
- **Releases are per repository.** `[[release.channel]]` binds a channel to one
  repository, the record carries `repo:`, and the chain is ordered by that
  repository's history — the old rule, applied to the right graph. Channels that
  ship together form a `[[release.group]]`: one command records each, runs the
  gate once, and writes an index record that links them.
- **Documents get a record-store list.** `[docs] stores` names requirement and
  asset trees so they are not asked for an index; a cross-repository link inside
  the root is fine, an absolute path or a link that leaves the root is a warning
  with a bounded exemption.

Omit `[workspace]` and you get the single-repository behaviour: one root, one
repository, no declared repositories.
Details: [references/workspace.md](skills/lite-dev/references/workspace.md).

## Teams and multiple machines

The flow is files plus git; there is no server, no lock service, and no network
call. These rules make that work for several people, several machines, and
parallel agent sessions:

- **Ids sort by time and need no coordination.** `{date}-{type}-{time}` encodes
  the millisecond of the local day, so a clone allocates an id alone and ids
  list in creation order within one timezone and day. Two creators stamping the
  same millisecond is the one collision left; `check` reports the duplicate
  instead of merging it. A prefix that matches two items is an error with the
  candidates listed; the tool never guesses.
- **Ownership is explicit.** `owner` is required and resolved from `--owner`,
  `$LITE_DEV_OWNER`, `git config lite-dev.owner`, or the project's
  `[project] owner_file` when the root is not a repository — never from
  `user.name`.
  `whoami` shows the value and its source; `claim` takes over an item and
  `status --mine` filters. Taking over someone's open item needs
  `--takeover --reason "..."`; closed items cannot be claimed and archived items
  are read-only until unarchived. `done` requires an identity, records
  `closed_by`, and an optional `[project] owners` roster makes `check` flag a
  non-canonical spelling.
- **Releases are ordered by the commit graph.** `--record` only runs on the
  mainline; a clone behind its upstream is refused; an unfetched clone cannot be
  detected, so pull first. An unreadable or divergent record stops the release;
  a bad record from a stale clone is repaired with a revert commit, never an
  edit.

`gate --work <ID>` validates that item plus the required documents, so a
teammate's unfinished item does not block your batch; a bare `check` and a
release still validate everything. `status` reports the branch, HEAD, and the
distance from the last fetch (`status --json` for scripts), and it never
fetches. Writes are atomic (LF endings, `os.replace`) and local writers are
serialized by a per-clone lock, so two agent sessions in one checkout cannot
interleave a read-modify-write.

Details: [collaboration.md](skills/lite-dev/references/collaboration.md).

## Status

The current release implements `init` (with `--plan`, `--apply`, `--baseline`,
and `--upgrade`), `new`,
`claim`, `whoami`, `status` (with `--stale`), `check`, `design`, `design-ready`,
`gate`, `done`, `drop`, `handoff`, `archive`, `unarchive`, `release`,
`reconcile`, `extensions`, the templates
(including `decision.md`), the invariants, document hygiene checks, index-graph
connectivity, decision chains, the expiring exemption ledger, cumulative
evidence (`done` refuses any item without a passing report, a recorded full-level
gate PASS, and an identity), ordered batch graphs, the risk-path design gate over
the whole history with worktree/committed provenance, the strictest-level
announcement `done`/`status`/`init` print, the
per-clone gate ledger, the derived adoption ladder
(`init --plan`/`--apply` proposals with a value guard), release
bookkeeping/debt separation, three bundled
extensions, per-repository commands and gate scoping, per-repository release
channels, configurable document stores, and two runnable examples (single
repository and workspace).

Versions and breaking changes live in `CHANGELOG.md` ([中文](CHANGELOG.zh.md)).

BSD 2-Clause licensed. See `LICENSE`.
