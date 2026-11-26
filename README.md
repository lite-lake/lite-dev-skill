# lite-dev-skill

**English** | [简体中文](README.zh.md)

`lite-dev` is an agent-first development flow that ships as an installable
**skill**: a protocol, templates, and a small profile-driven tool. Install it,
write one profile, and an agent can run a change from clarification to recorded
completion without inventing process.

Repository: <https://github.com/lite-lake/lite-dev-skill>

- Single repository first. No workspace, no service mesh, no assumptions about your CI.
- Zero install: Python 3.11+ standard library only (`tomllib`). No dependencies.
- The agent is the runtime. The skill is the entry point; scripts and references
  load on demand.

## What it is

A closed loop with a machine at the end of it:

```text
request
  -> clarify (<=5 questions, once)
  -> work item (item.md, AC)
  -> design (only when the change is large or risky)
  -> batches (B1..Bn, every AC covered)
  -> implement -> verify -> commit, per batch
  -> gate (the project's own commands, not ours)
  -> release record (optional channel)
  -> done (AC checked, evidence present)
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
- Not a multi-repo orchestrator. Single repository only.

## Quick start

1. **Install the skill.** Clone the repository, then put `skills/lite-dev/` where
   your agent harness discovers skills (for example `.claude/skills/`,
   `.agents/skills/`, or a user-level skills directory), or point your `AGENTS.md`
   at `skills/lite-dev/SKILL.md`.

   ```bash
   git clone https://github.com/lite-lake/lite-dev-skill.git
   ```

2. **Create a profile.**

   ```bash
   mkdir -p docs/flow
   cp <skill>/profile.template.toml docs/flow/profile.toml
   ```

   Edit `commands`, `gate`, `mainline`, `[flow] requires`, and `docs.required`.
   This is the only file that contains project-specific facts.

3. **Set your identity.** One value per person, on every machine:

   ```bash
   git config --global lite-dev.owner "Your Name"
   ```

   `new` refuses to guess: no owner, no item. `LITE_DEV_OWNER` and `--owner`
   override it.

4. **Ask the agent.** "Set up lite-dev in this repo", or go straight to
   "implement X". The skill triggers on implementation, fix, design, and release
   requests.

5. **Check anytime.**

   ```bash
   python3 <skill>/scripts/flow.py status --mine
   python3 <skill>/scripts/flow.py check
   ```

## Repository layout

```text
spec/invariants.md          entry point for readers; points at the canonical file
skills/lite-dev/            the installable skill: everything is inside
  SKILL.md                  entry point: principles, routing, stop conditions, red lines
  profile.template.toml     copy to docs/flow/profile.toml
  references/               invariants + depth, loaded per situation
  templates/                item, design, test report, implementation, release, retro
  extensions/               bundled declarative add-ons (go-service)
  scripts/flow.py           new / claim / status / check / design-ready / gate /
                            done / release / reconcile / extensions
  scripts/flowlib/          profile, identity, artifacts, checks, command runner,
                            atomic writes and the writer lock
  scripts/tests/            unit tests and an end-to-end acceptance test
examples/minimal/           a working single-repo project
```

## What is deterministic, what is not

| Deterministic (`flow.py`) | Model |
|---|---|
| collision-resistant id allocation, directory scaffold | clarifying questions, trade-offs |
| frontmatter / AC / batch parsing | design narrative and diagrams |
| derived status | batch decomposition |
| required fields, links, AC↔batch↔verification | code and tests |
| design gate (confirmation, rollback, gaps) | failure diagnosis |
| running profile commands, exit codes | black-box acceptance judgement |
| release chain ordered by commit ancestry | deployment judgement |

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
flow.py reconcile                      # advisory debt report; never blocks
flow.py extensions                     # what each add-on contributes
```

`--record` runs the gate itself; a previous run is not evidence. It refuses a
dirty tree, a branch other than `release.mainline`, an empty rollback, a source
that does not descend from the recorded tip, or commits without work items that
are not written into `--note`.

Extensions are declarative and additive: commands, gate steps, required docs,
risk paths. The loader rejects command collisions, unknown keys, and an
incompatible `requires` range.

## Teams and multiple machines

The flow is files plus git; there is no server, no lock service, and no network
call. Three rules make that work for several people, several machines, and
parallel agent sessions:

- **Ids never need coordination.** `{date}-{type}-{rand}` gives every clone a
  collision-resistant id. A prefix that matches two items is an error with the
  candidates listed; the tool never guesses.
- **Ownership is explicit.** `owner` is required and resolved from `--owner`,
  `$LITE_DEV_OWNER`, or `git config lite-dev.owner` — never from `user.name`.
  `claim` takes over an item and `status --mine` filters.
- **Releases are ordered by the commit graph.** `--record` only runs on the
  mainline, a stale clone is refused instead of recording an older source, and
  an unreadable or divergent record stops the release.

`gate --work <ID>` validates that item plus the required documents, so a
teammate's unfinished item does not block your batch; a bare `check` and a
release still validate everything. Writes are atomic (LF endings, `os.replace`)
and local writers are serialized by a per-clone lock, so two agent sessions in
one checkout cannot interleave a read-modify-write.

Details: [collaboration.md](skills/lite-dev/references/collaboration.md).

## Status

The current release implements `new`, `claim`, `status`, `check`, `design-ready`,
`gate`, `done`, `release`, `reconcile`, `extensions`, the templates, the
invariants, and a runnable single-repo example. Planned: a multi-repo workspace
profile.

Versions and breaking changes live in `CHANGELOG.md` ([中文](CHANGELOG.zh.md)).

BSD 2-Clause licensed. See `LICENSE`.
