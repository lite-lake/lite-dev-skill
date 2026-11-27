# Adoption: a derived ladder, three steps

Introducing lite-dev into a project that already has code, tests, documents, and
opinions is the first task the flow has to get right. It is not an install event:
the project is somewhere on a ladder, and the ladder is computed from files so
every clone sees the same place.

No adoption state is stored. Delete any local output and the ladder is the same
on the next run.

## The ladder

| Rung | Meaning | Completion predicate | Blocks? |
|---|---|---|---|
| S0 | scaffolded | `docs/flow/profile.toml` loads | — |
| S1 | wired | every declared gate level runs a configured command | **yes** |
| S2 | bounded | `check` has no errors and no enabled-but-inert switch | no |
| S3 | anchored | `[reconcile] baseline` is set, or a release record exists | no |
| S4 | owned | this clone resolves an identity | no |
| S5 | practiced | at least one item has been closed through `done` | no |

`status` prints the count, the next rung, why it is not done, and the one
command that advances it. `--json` carries the same facts.

Only S1 blocks. A project must be able to adopt mid-history and still ship its
next change; the remaining rungs are a visible backlog, not an entrance fee.
Refusal is per level: a level whose command is unconfigured refuses to run and
names `init --plan`, so a wired l1 still iterates while l3 is being wired.
`done` refuses because it closes on the strictest level, and that level cannot
run.

## The three steps

```bash
flow.py init                      # scaffold; never overwrites; prints the ladder
flow.py init --plan               # read-only: proposals from repository evidence
flow.py init --apply commands.test  # write one proposal, then re-check
```

`init --adopt` is the same as `init` followed by `--plan`: it keeps every file
it finds and prints the plan.

`--plan` and `--apply` are deliberately separate. The profile is executable
input, so no detector writes it. A proposal names the value it expects to
replace; if that value changed since the plan, `--apply` refuses and says to
re-plan. Applying several ids is all-or-nothing.

After the scaffold is committed, anchor it:

```bash
flow.py init --baseline
```

The baseline is a commit in the control repository; history before adoption is
a baseline, not debt. `--baseline` needs a clean tree, so it is a second run.

## Unconfigured is a value

The template writes `test = "!unconfigured"`. That is not a comment and not a
placeholder command that fails at run time:

- `check` reports the unconfigured level and points at `init --plan`;
- `gate --level` refuses that level before running anything;
- `done` refuses when the strictest level is unconfigured;
- `commands.plan` raises if a level selects such a command.

Profiles that still carry the old `echo 'configure [commands] test ...'`
placeholder are recognised as unconfigured too, so an adopted project cannot
keep a silent one forever. Nothing is rewritten: the plan proposes a real
command and `--apply` writes it.

## What is proposed

Detection is read-only and conservative. Core proposes:

- `commands.test` / `commands.lint` when a gate level references an
  unconfigured name and the repository shows a runnable convention: a `Makefile`
  target, `package.json` scripts (with the lockfile's runner), pytest or
  unittest evidence, `go.mod`, `Cargo.toml`, Maven, Gradle, Composer;
- `project.name` when the profile still says `my-project`;
- `project.language = "zh"` when the entry documents are mostly Chinese;
- `docs.stores` for record-like directories (`prds`, `requirements`,
  `resources`, `assets`, `exports`) that have files but no index.

The plan also reports, without proposing a write: CI entrypoints (l3 must be
runnable locally), sibling repositories that look like a workspace (declare
`[workspace]` by hand), and paste-ready `[[exempt]]` shapes for real document
conflicts. Exemptions are a record with a reason and an expiry, so the tool
shows the shape and leaves those two fields to a human.

Detectors may recognise ecosystem conventions; they may not encode project
facts and they never write. A false proposal costs one ignored line.

## Adding a detector

An extension may declare detectors; the loader accepts only additive keys:

```toml
[[detect]]
file = "go.mod"
command = "go test ./..."
note = "go.mod (go-service extension)"
```

`init --plan` then offers the command when the marker file exists. The bundled
`go-service` extension ships one as the pattern. Core keeps the mechanism and
the language-agnostic probes; an ecosystem belongs in an extension.

## Version drift

A profile from an older install may not load, and "install the matching skill
version" is not a migration. The version has three components: a patch is
seamless, a minor still loads but asks for a CHANGELOG review, and a major
refuses until the checklist is acknowledged. `init --upgrade` reads the raw
profile (it cannot load it), classifies the drift, prints the changelog range,
and proposes both `flow.requires` and `flow.reviewed`:

```bash
flow.py init --upgrade
flow.py init --upgrade --apply flow.requires --apply flow.reviewed
```

`--apply flow.requires` alone moves the window but leaves `reviewed` outside
it, so the profile does not load until `flow.reviewed` is applied too. A major
crossing also needs `--accept-major`; the full checklist is in
[upgrade](upgrade.md). After the contract is current, run `init --plan` to wire
commands, then `check`.

## What it does not do

- No adoption state file, and no `installed` flag: the ladder is derived.
- No automatic profile writes, and no command guessed without evidence.
- No backfill: no retroactive items, no rewritten history. If a change cannot
  wait for an item, the release `--note` records the debt and `reconcile` keeps
  it visible.
- No workspace scaffolding yet: sibling repositories are reported and declared
  by hand, following [workspace](workspace.md).
- S2 does not require a clean document tree, only that `check` is honest: fix
  the conflict or record a bounded silence with an expiry.

## The invariant

[Invariant 14](invariants.md) is the rule this file implements: adoption is
derived, only S1 blocks, detection proposes and a human declares, and an
extension may add a detector but never waive a rung.
