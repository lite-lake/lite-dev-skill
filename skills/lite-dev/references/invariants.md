# lite-dev invariants

These are the non-negotiables. Everything else (commands, templates, references)
can adapt to a project; these cannot be removed by a profile or an extension.

Each invariant names how it is enforced. "Tool" means `flow.py` refuses or
reports; "human" means a stop condition; "v0.2" means specified but not yet
mechanised.

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

- The tool derives status from artifacts. Humans and agents never edit a status field.
- The state machine is: need-clarify → clarified → designing → ready → done, plus dropped.
- **Enforced**: `flow.py status` computes it; no template contains a status field.

## 4. The machine gate is the only judge

- A change is not submit-ready because it was reviewed or "works locally".
- The gate runs the project's own commands; the tool never invents one.
- Gate levels: l1 iterates, l2 accepts a batch, l3 commits/releases.
- **Enforced**: `gate` runs `check` first, then the profile's commands, and
  returns the command exit code.

## 5. Implementation and verification are different contexts

- The verifier checks AC black-box, not the implementer's rationale.
- Evidence is written to `test-report.md`; a claim is not evidence.
- When the harness has no subagents, the weaker mode is declared, not hidden.
- **Enforced**: v0.2 (missing test-report is reported when a design is ready);
  otherwise human.

## 6. Every batch is planned before the first one

- The design lists all `B1..Bn`; no "this round" or "stage 1".
- Every AC appears in at least one batch.
- Contracts and data model first; backend before frontend.
- After each batch the main branch builds and passes the gate.
- **Enforced**: `design-ready` validates batch ids, AC coverage, and dependencies.

## 7. Work is never half-done on main

- Unfinished features are hidden behind a flag or kept out of main.
- Each batch leaves main buildable.
- **Enforced**: human; the gate can only see what exists.

## 8. Releases are recorded; bypass is visible, not blocked

- Channel branches are fast-forward only; never commit on them.
- Every release records source commit, artefacts, gate/smoke results, rollback target.
- Commits without work items are recorded as adhoc debt; they are not blocked.
- **Enforced**: `release --record` runs `check` and the configured gate level,
  refuses a dirty tree, a channel branch, an empty rollback, or undocumented
  debt; `reconcile` reports the debt and exits 0.

## 9. One authority per fact

- Rules, stable design, precise contracts, environment facts, and glossary each
  have exactly one home. Other documents link.
- Entry documents (`README`, `AGENTS`) contain no version numbers, ports,
  service counts, or dates that will drift.
- **Enforced**: `check` validates required documents and links; the zero-fact
  rule is human until v0.2.

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
- **Enforced**: human; `design-ready` requires `## Rollback` to be non-empty.

## Compatibility

- The profile may set sizes, commands, channels, id format, and languages.
- An extension version must state the lite-dev version range it supports.
- A change to this file is a breaking change and requires a major version bump.
