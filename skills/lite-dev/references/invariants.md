# lite-dev invariants

These are the non-negotiables. Everything else (commands, templates, references)
can adapt to a project; these cannot be removed by a profile or an extension.

Each invariant names how it is enforced. "Tool" means `flow.py` refuses or
reports; "human" means a stop condition; "partly" means specified but only
partially mechanised.

`human` and `partly` are debts, not categories. Adding or changing an invariant
requires naming its mechanisation candidate: a generator, a gate step, a check,
a template, then prose, then habit. An item that has stayed `human` for two
releases either becomes a check or is deleted — a rule nobody enforces is a rule
that teaches people to ignore the file.

## 1. Clarify before design, design before code

- A requirement has at most five open questions, asked once, with defaults.
- `design.md` is not written and code is not changed before `Status: clarified`.
- **Enforced**: `design-ready` and `check` refuse an unclarified item with a design.

## 2. Confirmation is final

- The plan is spoken in conversation before `design.md` is written.
- A clear "go with this plan" is final. `design.md` records it; no second review.
- Re-confirmation is required only when scope, contracts, or the data model change.
- **Enforced**: `design-ready` requires `Confirmed: yes` and a date when
  `design.require_confirmed = true`.

## 3. Status is derived, never written

- The tool derives status from artifacts. Humans and agents never edit the item's status; `design.md` may carry its own `status` for its lifecycle.
- The state machine is: need-clarify → clarified → designing → ready → done, plus dropped.
- **Enforced**: `flow.py status` computes it; no template carries the item status.

## 4. The machine gate is the only judge

- A change is not submit-ready because it was reviewed or "works locally".
- The gate runs the project's own commands; the tool never invents one.
- Gate levels: l1 iterates, l2 accepts a batch, l3 commits/releases.
- A cheap level is scoped, not smaller: a change under `[gate] fallback_paths`
  invalidates it, and the tool says so instead of staying quiet.
- A structural change — a path under `[design] risk_paths` and not under
  `risk_exempt` — is not submit-ready without a ready design.
- **Enforced**: `gate` validates the applicable artifacts first — the item named
  by `--work` plus the profile's required documents, or the whole project when
  no item is named — then runs the profile's commands and returns their exit
  code. Another person's unfinished item does not block your batch; a release
  still validates everything. The strictest level's last PASS is recorded per
  clone and reported as stale when it ages out (advisory, never a block);
  `done` requires a PASS for the item at the strictest level in this clone; a
  project-wide run does not name the item. `gate --work` warns or refuses a
  risk-path change without a ready design, according to `[design] risk_gate`.

## 5. Implementation and verification are different contexts

- The verifier checks AC black-box, not the implementer's rationale.
- Evidence is written to one cumulative `test-report.md` per item; a claim is
  not evidence. A later batch appends its rows or another `## Evidence` block;
  it never overwrites an earlier batch's evidence.
- Evidence is one row per AC with the command and its output. A row with an
  empty cell, a TODO-style placeholder, or no row at all is not evidence.
  Angle-bracket text in a real command or output (`<skill>`, `<nil>`, `<br>`)
  is evidence, not a placeholder.
- When the harness has no subagents, the weaker mode is declared, not hidden.
  For a one-shot item with no `implementation.md`, declare it in `## Notes`.
- **Enforced**: `done` refuses any item without `test-report.md`, without
  `Verdict: PASS`, with an AC that has no evidence row, without a recorded
  full-level gate PASS, or without an identity. While the item is open, `check`
  reports a partial or failing report as a warning so iterating is not blocked.
  Whether the evidence is *sufficient* is still human.

## 6. Every batch is planned before the first one

- The design lists all `B1..Bn` in order, with no gaps; no "this round" or "stage 1".
- Every AC appears in at least one batch.
- A dependency names an earlier batch; no forward edge, cycle, or self-dependency.
- Contracts and data model first; backend before frontend.
- After each batch the main branch builds and passes the gate.
- **Enforced**: `design-ready` validates contiguous ordered batch ids, AC
  coverage, dependency existence and direction, and cycles. `handoff` refuses a
  done batch, a batch whose dependency is not done, and names a blocked batch
  instead of dispatching it.

## 7. Work is never half-done on main

- Unfinished features are hidden behind a flag or kept out of main.
- Each batch leaves main buildable.
- **Enforced**: human; the gate can only see what exists.

## 8. Releases are recorded; bypass is visible, not blocked

- Channel branches are fast-forward only; never commit on them.
- Every release records the source commit, who recorded it, the lite-dev version,
  gate/smoke results, the configured artefacts, and a rollback target.
- Records form one chain per channel; the watermark is the ancestry tip of that
  chain, not a filename or a local clock.
- Commits that only add records, change the profile, or archive an item are
  bookkeeping, not debt. Other commits without work items are recorded as adhoc
  debt; they are not blocked, but they cannot be skipped with `--since`.
- `## Work items` names only existing (active or archived) items; an unknown id
  is labelled `(missing)`.
- **Enforced**: `release --record` runs `check` and the configured gate level,
  refuses a dirty tree, a non-mainline branch, a behind clone, an empty rollback,
  undocumented debt, and a source that does not descend from the recorded tip;
  an unreadable or divergent record stops the release instead of being skipped;
  `reconcile` reports the debt and exits 0 when it can compute the range.
  Divergent records are repaired with a revert commit, never by editing one.

## 9. One authority per fact

- Rules, stable design, precise contracts, environment facts, and glossary each
  have exactly one home. Other documents link.
- Entry documents (`README`, `AGENTS`) contain no version numbers, ports,
  service counts, or dates that will drift.
- A document without a route does not exist: an index that nobody links is not
  an index, and a directory of documents without one has no entry point.
- Every document is reachable: `docs_dir/README.md` is the root index; every
  directory index outside the record stores (`work_dir`, the release directory,
  `_archive/`) is reachable from it by following links; a file in an indexed
  directory is linked from that directory's `README.md`; every artifact in an
  item directory is mentioned by its `item.md`.
- A decision is superseded, never rewritten: the status is an enum, a superseded
  decision names its successor, the successor exists, and the chain terminates.
  The shipped decision template uses `none` for empty pointers and passes its
  own checker.
- The archive index is the record store's entry point: every archived item has
  one row, and every row resolves to an archived item.
- A silence is a record, not a switch: an exception names one check, one path, a
  reason, and an expiry. An expired exception suppresses nothing and is an error.
  A global switch (`check_links`, `zero_fact`) is reported on every run, and an
  enabled check that inspects nothing is reported as inert.
- **Enforced**: `check` reports missing required documents, unresolved relative
  links, unreachable directory indexes, directories with no index, unindexed
  files, unmentioned item artifacts, archive-index drift, duplicate headings in
  a release record, version/port/date/count pins in entry documents, broken
  decision chains, expired or unused exemptions, and a disabled or inert check.
  Record stores (work items, release records, `_archive/`) are excluded from the
  link index. Whether the prose is true is still human.

## 10. Extensions may add, never remove

- An extension may add commands, paths, risk patterns, templates, and stricter checks.
- It may not change the state machine, remove required artifact fields, or waive
  an invariant.
- **Enforced**: the loader accepts only additive keys, rejects unknown keys and
  command collisions, and refuses an extension whose `requires` range excludes
  the running lite-dev version.

## 11. Stop conditions outrank progress

- Unclear requirement, unconfirmed plan, irreversible action without rollback,
  destructive schema change, gate failing three times, batch failing verification
  twice, scope growth, context exhaustion → stop and ask.
- Batch completion is not a stop condition.
- **Enforced**: human; the skill states the list where it is always loaded.

## 12. Irreversible actions require a rollback

- Data, permissions, credentials, and releases need a rollback target first.
- No rollback, no irreversible step.
- A release that touches a structural path is an irreversibility the profile can
  make explicit: with `[release] confirm_risk_paths = true`, the record must name
  the human's authorisation, not just the rollback.
- **Enforced**: human; `design-ready` requires `## Rollback` to be non-empty, and
  `release --record` refuses a risk-path range without `--confirm` when the
  profile asks for it.

## 13. Identity is collision-resistant and never guessed

- Item ids are allocated without coordination: `{date}-{type}-{time}`, where
  `{time}` is the millisecond of the local day. No clone pulls or scans before
  `new`, and ids sort in creation order within one local day and timezone. Two
  allocations that stamp the same millisecond collide; `new` bumps past a code
  already on disk, and `check` reports a duplicate id rather than merging the
  two items.
- Every item records its owner; the owner comes from an explicit identity, never
  from a machine's `user.name`. Reassigning an open item that another person
  owns requires an explicit `--takeover --reason "..."`, and closing an item
  requires an identity and records who closed it. A closed item cannot be
  claimed, and an archived item is read-only until unarchived.
- Shared facts that must agree across clones — release order, the watermark —
  come from the commit graph, never from a local clock or directory order. The
  id's time code is a label and a sort key, not a watermark.
- Two matches for one id is an error, not a choice; so is an unreadable,
  stale, or forked release record.
- **Enforced**: `new` allocates `{time}` and increments it on collision;
  `find_item` refuses an ambiguous id and lists the candidates; `claim` records
  ownership and refuses another person's open item without
  `--takeover --reason`; `done` requires an identity and writes `closed_by`;
  `release`/`reconcile` order records by ancestry and stop on a broken chain.

## Compatibility

- The profile may set sizes, commands, channels, id format, mainline branch,
  identity policy, and languages.
- An extension version must state the lite-dev version range it supports.
- Nothing is published before 1.0.0, so this file may change freely. 1.0.0 is
  the first public release; from then on, a change to this file is a breaking
  change and requires a major version bump and a note in both changelogs.
