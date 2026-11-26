# Changelog

**English** | [简体中文](CHANGELOG.zh.md)

## 0.3.5 — 2026-11-26

The parts of the flow that were specified but left to people become checks: the
handoff prompt is assembled instead of retyped, `check` now reads the documents
it used to trust, a risk path without a design is visible, and a stale full gate
says so. Two optional extensions cover credentials and deployment manifests.

### Added

- `handoff <ID> [--batch <Bx>]` prints a cold-start prompt built from the
  artifacts: item and design paths, the design's handoff summary verbatim, batch
  progress from `## Implementation`, the next batch, and the gate command.
  `--batch` prints the implement dispatch for one batch. Instructions are written
  in `project.language`; the data is never paraphrased.
- `archive <ID> [--reason …]` and `unarchive <ID>`: a closed item moves to
  `<work_dir>/_archive/<YYYY-MM>/` and one row is appended to that directory's
  `README.md`. Nothing is deleted; an archived id still resolves but is not part
  of `status`.
- `check` now validates documents, not only artifacts:
  - relative links under `docs_dir` resolve (fenced blocks and inline code are
    skipped, template tokens are ignored);
  - every markdown file in an indexed directory is linked from that directory's
    `README.md`;
  - every artifact file inside an item directory is mentioned by its `item.md`;
  - a release record repeats no `##` heading;
  - no live document links into `_archive/`;
  - entry documents (`README`, `AGENTS`) pin no version, port, or date;
  - `[docs] decisions`, when set, exists and has an index.
- `[design] risk_paths`, `risk_exempt`, `risk_gate`: `gate --work` reports (or,
  with `"block"`, refuses) a change under a risk path that has no ready design.
  The exemption list is what keeps prose about a risk path from tripping it.
- `[gate] fallback_paths`: changing a listed path (lock files, schema runs,
  toolchain pins) invalidates a cheap level; the gate says to run the strictest.
- `[gate] fresh_days` and a per-clone gate ledger in `<git-dir>/lite-dev/`:
  `status` and a cheaper level report when the strictest level's last PASS is
  stale. Advisory only; the ledger is never a working-tree file.
- Extension commands may contain `{skill}`; the loader expands it to the
  installed skill directory (shell-quoted), so a bundled extension can ship a
  script without hardcoding a machine path.
- Bundled `security-scan`: fails the gate on tracked credentials, sensitive file
  names, or credentialed URLs, with a path-prefix allowlist.
- Bundled `deploy-lane`: validates deployment manifests — required fields,
  backfilled values, RFC3339 time, commit shas, immutable tags and `sha256:`
  digests, and a rollback target that is never blank.
- `templates/decision.md` and `[docs] decisions` for records that outlive a
  work item.
- `references/docs-hygiene.md`.

### Changed

- `check` can now fail where it used to pass: a broken relative link, a repeated
  heading in a release record, or a missing decisions index is an error. Run
  `check` once after upgrading; the warnings name the file and the fix.
- `status` adds a gate-freshness line, an archived count, and `gate` in
  `--json`. Existing consumers of the text output are unaffected; script
  consumers that parse strictly should read the new field.
- `gate` records each run in the per-clone ledger and prints the fallback and
  risk-path advisories before running the commands.
- `done` is unchanged, but `find_item` now resolves archived ids as well; a
  duplicate between the working set and the archive is still reported by `check`.
- The profile template pins `[flow] requires = ">=0.3.5,<0.4"`. A project on
  `>=0.3.2,<0.4` needs no change and picks all of the above up; the new keys are
  simply unavailable on older installs.
- The extension schema was **not** widened beyond `{skill}`. Deployment records
  are covered by the release record plus the document checks, so `[templates]`
  and `[artifacts]` stay out until something real needs them.

### Fixed

- `git status --porcelain -uall` is used for changed paths, so the risk gate sees
  `db/schema.sql` instead of the collapsed `db/`, and an exemption can match.

## 0.3.4 — 2026-11-26

Working with other people and on more than one machine: identity drift becomes
visible, an accidental takeover is refused, and closing an item records who did
it.

### Added

- `whoami` prints the resolved identity, where it came from (`--owner`,
  `$LITE_DEV_OWNER`, `git config lite-dev.owner`), and the project.
- `status --json` emits the checkout, items, and counts for scripts and
  dashboards. The text output now shows the branch, HEAD, and the behind/ahead
  distance from the remote-tracking ref; it still never fetches.
- `check` warns when two owners differ only by case or spacing, and, when
  `[project] owners` is set, about any owner outside the roster.
- `check` warns to set `git config core.quotepath false` once an item directory
  contains non-ASCII characters.
- `done` writes `closed_by` into `item.md` and warns when the closer is not the
  owner. The field is optional, so existing items stay valid.

### Changed

- `claim <ID>` now refuses an open item owned by someone else and exits 2;
  `--takeover` reassigns it. This is a behaviour change, shipped as a patch
  release on purpose: a project pinned `>=0.3.2,<0.4` picks it up without
  editing the pin. An unowned or already closed item is claimed as before.
- `[flow] requires` stays `>=0.3.2,<0.4`; no project has to change its pin.
- The docs narrow the id claim: ids sort in creation order within one local day
  and timezone, not globally. `collaboration.md` now covers cross-timezone and
  clock-rollback codes, takeover, the roster, and the release-record filename
  collision that happens when two clones record the same source.
- Tests cover the paths that were only specified before: the id bump when a code
  is already on disk, the duplicate-id report, a second process contending for
  the per-clone lock, and atomic writes that keep LF endings.

### Fixed

- Test fixtures resolve their temporary directory, so the suite passes on macOS
  where `/var` is a symlink to `/private/var`. CI runs on Linux and never saw it.

## 0.3.3 — 2026-11-26

The directory slug follows the title's script instead of forcing one width on
every language.

### Changed

- A Chinese title keeps its characters in the directory name, capped at 30
  characters; an English title keeps the dash-joined form and the 32-character
  cap. The rule reads the title, not `[project] language`: a Chinese title in an
  English-language project keeps its slug instead of becoming empty.
- `check` warns when a Chinese slug exceeds 20 characters. It is a warning, not
  an error; the hard cap is 30.
- `[flow] requires` stays `>=0.3.2,<0.4`: the slug is cosmetic and does not
  change what the gate accepts.

## 0.3.2 — 2026-11-26

Work items are filed by month, so a long-lived project does not keep thousands
of directories in one place.

### Breaking changes

- Items live at `<work_dir>/<YYYY-MM>/<id>-<slug>/`. The month comes from the
  item's `created` date and is written once by `new`; `check` reports an item
  filed under another month.
- A directory directly under `<work_dir>` that is not `YYYY-MM` is an error,
  never skipped. Move a pre-0.3.2 flat item with
  `git mv <work_dir>/<id>-<slug> <work_dir>/<YYYY-MM>/`.
- `[flow] requires` in the template, `examples/minimal`, and the bundled
  `go-service` extension is now `>=0.3.2,<0.4`: 0.3.1 would look for items in
  the old layout and find none.

### Changed

- `new` creates the month directory and files the item inside it.
- `new`'s duplicate scan reads only the target month instead of every item in
  the project; an id carries its `created` date, so a candidate cannot collide
  with an item filed in another month.
- `check` warns about a month directory that holds a stray directory without
  `item.md`.

## 0.3.1 — 2026-11-26

Item ids carry the millisecond of the local day, so they sort in creation order.

### Breaking changes

- Item ids are `{date}-{type}-{time}`. `{time}` is the millisecond since local
  midnight, six characters from `23456789abcdefghjkmnpqrstuvwxyz`, zero-padded.
  `{rand}` is removed; `[id] format` must contain `{time}`.
- Ids written before this release (five random characters) no longer match the
  format. `check` reports them; rename the directory and the `id:` field to a
  current id if you keep such a project.
- Invariant 13 no longer claims a random token. The time code is a label and a
  sort key, not a coordination fact: two creators that stamp the same
  millisecond get the same code, and `check` reports the duplicate id.

### Added

- `flowlib/stamp.py`: the clock read, the fixed-width code, and the per-process
  allocator that never hands out a code twice.

### Changed

- `new` reads the clock once, so the date and the time code cannot straddle
  midnight; a code collision bumps to the next millisecond instead of redrawing
  a random token, and `new` also refuses a code already on disk.
- `examples/minimal`, the profile template, and the bundled `go-service`
  extension require `>=0.3.1,<0.4`.

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
