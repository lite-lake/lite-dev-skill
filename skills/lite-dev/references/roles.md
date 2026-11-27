# Roles

Roles are contexts, not job titles. Use a fresh context per role when the
harness supports it. The main session orchestrates; it does not implement.

## Shared rules

- Pass paths and ids, not conversation history.
- Each role returns at most ~30 lines: what changed, evidence, open issues.
- Only the commit role commits. Only the verify role declares PASS.
- An implementer or verifier that commits is doing the commit role's work; a
  committer that edits code is doing the implementer's. Stop the role, return
  the finding, and let the orchestrator re-dispatch.
- Never let the implementer be the only verifier.
- No role closes the item. `done` closes it, after the evidence exists.

## Orchestrator (Phase B main session)

- Preflight: `flow.py status`, read `## Handoff`, `## Batches`, `## Verification`,
  and `## Decision Defaults`.
- Dispatch every unfinished batch in dependency order; after each one, update
  `## Implementation`.
- Batches in one `Parallel` group with disjoint repositories may be dispatched in
  the same turn; one repository is always serial. Dispatch a group through
  `handoff --batch` for each member, so every member gets its own gate scope and
  its own acceptance set.
- One file, one writer: while a group runs concurrently, each implementer returns
  its `## Bx` section in its result and the orchestrator appends them after the
  group returns. Two concurrent writers to `implementation.md` lose one of them.
- Do not write business code, fix bugs, or redesign.
- Stop only on the conditions in SKILL.md §9, and classify before stopping: an
  open implementation detail takes the design's default, a missing environment is
  recorded and the independent batches continue. Context exhaustion is a hard
  stop: update progress first, then hand off.

## Implement

Input: item id, batch id, design path, repo path, the batch's AC subset and
acceptance set, gate command.

- Read the batch row and the approach section; do not re-plan the design.
- Write code and tests. Use the fast gate (`l1`) for feedback; do not run the
  full suite unless the batch says so.
- Write the batch section in `implementation.md`; return a short result. In a
  concurrent group the orchestrator writes the section from your result.
- A gap in scope, a contract, the data model, or a security semantic stops the
  batch and is reported. An implementation detail takes the design's
  `## Decision Defaults`, is written into `## Deviations` with its reason, and
  does not stop anything.
- Do not commit. Do not touch other batches.

## Verify

Input: item id, batch id, acceptance set, regression set, how to run the product.

- Verify black-box against the AC. Do not read the implementation rationale first.
- Choose checks that can falsify the AC, not checks that reproduce the implementation.
- Accept this batch's ACs — the ones it is the first to name — black-box. For an
  AC accepted in an earlier batch, run regression for what this change touches;
  re-accepting it is waste, and skipping it because "it passed" is not evidence.
- Append to the item's single cumulative `test-report.md`: verdict, evidence per
  AC, environment, what was not covered. One row per AC with the command you ran
  and what it printed; never overwrite an earlier batch's rows. A later batch may
  append another `## Evidence` block; `done` reads every block. `done` refuses
  any item without the report, and an empty cell is not evidence.
- Do not commit. Report a defect; the commit role owns the commit.
- Fix only defects inside the batch; at most two rounds, then stop and ask.

## Commit

Input: item id, batch id, changed repos.

- Run the full gate: `flow.py gate --level l3 --work <ID>` (or the profile's commit level).
- One commit per repo per batch. Message: `<type>: <module>-<summary> (<ID>)`.
- Integrate the mainline without rewriting it: merge it in (fast-forward when
  possible) and push. Never force-push the mainline; a rewritten mainline
  orphans recorded release watermarks. Record commit hashes in `implementation.md`.
- Do not change code. If the gate fails, return to implement.
