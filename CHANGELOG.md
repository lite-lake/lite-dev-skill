# Changelog

**English** | [简体中文](CHANGELOG.zh.md)

## 0.3.0 — 2026-11-26

Multi-person, multi-machine, and parallel-agent support. The flow no longer
depends on a local scan, a filename, or a local clock for any shared fact.

Pre-1.0: nothing in this project has been published. There is no migration path
and no compatibility promise until 1.0.0, which will be the first public release.

### Breaking changes

- Item ids are `{date}-{type}-{rand}` (five random characters). `{seq}`,
  `{owner}`, and `[id] owner` are removed; `[id] format` must contain `{rand}`.
- `owner` is a required item field. `new` resolves it from `--owner`,
  `$LITE_DEV_OWNER`, or `git config lite-dev.owner` and refuses to guess.
- `gate --work` and `check --work` validate only the named item plus the
  profile's required documents. A bare `check` and `release --record` still
  validate the whole project.
- `release --record` runs only on `[release] mainline`. A feature branch, a
  channel branch, and a detached HEAD are refused; a source that does not
  descend from the recorded tip is refused.
- Release records gain `by`, `tool`, and `## Artifacts`; the filename includes
  the short source. The watermark is the ancestry tip of the channel's records;
  an unreadable record, a missing commit, a stale clone, and divergent records
  are errors instead of being skipped.
- `[release] mainline` is required when channels are configured.
- `[flow] requires` is required and pins the lite-dev version; an incompatible
  install is a profile error.

### Added

- `claim <ID>`, `status --mine`, `check --work`, `release --by`, and repeatable
  `release --artifact`.
- `flowlib/identity.py`, `flowlib/fsio.py` (atomic LF writes, per-clone writer
  lock), `flowlib/errors.py`.
- `references/collaboration.md`: identity, ids, claims, trunk assumption, scoped
  gate, release rules, conflicts, one-person-many-machines checklist.
- Invariant 13: identity is collision-resistant and never guessed.
- Tests for cross-clone ids, ambiguous prefixes, scoped gate checks, release
  chain validation (stale, divergent, broken, unreadable), and LF writes.

### Changed

- Invariants 3, 4, and 8: status wording, gate scope, and record contents plus
  the ancestry watermark.
- `reconcile --since` must be an ancestor of HEAD; a channel it cannot order
  exits 2.
- Writes are atomic and use LF endings on every platform; two sessions in one
  clone serialize their read-modify-write.

## 0.2.1 — 2026-11-26

### Added

- `CHANGELOG.zh.md`, a section-by-section Chinese counterpart of this file.
- `README.zh.md` rewritten as a full mirror of `README.md` (it was a condensed
  version missing sections such as the deterministic/model table).
- Language switcher links at the top of both READMEs and both changelogs.

### Changed

- License changed from MIT to BSD 2-Clause. Updates `LICENSE`, the `license`
  field in `skills/lite-dev/SKILL.md`, and the license line in `README.md` and
  `README.zh.md`. No code or protocol change.
- `__version__` is now `0.2.1`. `v0.2.0` stays as published, under MIT.
- Dropped the `(v0.1)` version number from both READMEs, per invariant 9
  ("entry documents contain no version numbers"). The line now reads "Not a
  multi-repo orchestrator. Single repository only."

## Packaging — lite-dev-skill

- The distribution repository is <https://github.com/lite-lake/lite-dev-skill>.
- The skill keeps the name `lite-dev`: it is the flow name and the trigger.
- No behavior change; the tool version stays 0.2.0.

## 0.2.0 — 2026-11-26

### Added

- `release`: plan by default, `--record` to write. A record is written only after
  `check` passes, the configured `release.gate_level` passes, the tree is clean,
  the branch is not a release channel, and `--rollback` is non-empty. Commits
  without work items must be written into `--note`.
- Release watermark: the latest record's `source` is the next range base;
  `previous` is recorded for lineage. Records render from `templates/release.md`.
- `reconcile`: advisory report (`no work item`, `missing work item`, `risky path
  without item`, `uncommitted`), `--since`, `--json`, `--verbose`. Exit 0 whenever
  a report can be produced; it never blocks.
- Extension loader: declarative `extension.toml`, resolved from the project first
  and then the skill, with a mandatory `requires` version range. Merges are
  additive only; command collisions, unknown keys, and removing a rule are errors.
- Bundled `go-service` extension (build/vet/test commands, gate steps, risk paths).
- `extensions` command showing source, version range, commands, and gate additions.
- `flowlib/git.py`, `flowlib/reconcile.py`, `flowlib/release.py`.
- Tests for version ranges, extension merging and failures, reconcile categories,
  release recording, the watermark, dirty-tree and channel-branch refusals.

### Changed

- `gate` and `release` share one command runner; a failing step stops the run.
- `check --json` now includes the lite-dev version and resolved extensions.
- `release --record` reuses the same static check as `gate`.

## 0.1.0 — unreleased

First cut. The goal is a coherent single-repo loop, not feature parity with any
existing tool.

### Added

- `spec/invariants.md`: the twelve non-negotiables, each with its enforcement.
- `skills/lite-dev/SKILL.md`: entry point with a progressive-disclosure routing table.
- `references/`: clarify, one-shot vs two-phase, roles, harness modes, release
  channels, reconcile, anti-patterns.
- `templates/`: item, design, test-report, implementation, release, retro.
- `scripts/flow.py` + `flowlib/`:
  - `new` (id allocation, directory, template render)
  - `status` (derived status, AC progress)
  - `check` (fields, enums, AC, links, design rules, required docs)
  - `design-ready` (handoff, diagram, confirmation, batches, verification, rollback)
  - `gate` (static checks, then profile commands per level, exit codes)
  - `done` (AC and design prerequisites, writes `closed:`)
- `examples/minimal`: a runnable single-repo project with real tests.
- Unit tests for profile loading, parsing, status derivation, the design gate,
  command execution, and closing an item.

### Known limits

- `release` and `reconcile` are specified in references but not yet implemented.
- No extension loader; extension packs are still a layout convention.
- Single repository only; no workspace profile.
- Identity (`owner`) is a profile field, not a local machine convention.

### Decisions

- TOML profile, Python standard library only. No dependencies, no install step.
- Artifact headings are English and stable; prose language is free.
- The tool never invents commands: gate levels map to `[commands]` in the profile.
