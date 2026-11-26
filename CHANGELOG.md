# Changelog

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
