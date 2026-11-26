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

- Preflight: `flow.py status`, read `## Handoff`, `## Batches`, `## Verification`.
- Dispatch every unfinished batch in order; after each one, update `## Implementation`.
- Do not write business code, fix bugs, or redesign.
- Stop only on the conditions in SKILL.md §9. Context exhaustion is a stop
  condition: update progress first, then hand off.

## Implement

Input: item id, batch id, design path, repo path, the batch's AC subset, gate command.

- Read the batch row and the approach section; do not re-plan the design.
- Write code and tests. Use the fast gate (`l1`) for feedback; do not run the
  full suite unless the batch says so.
- Write the batch section in `implementation.md`; return a short result.
- Do not commit. Do not touch other batches.

## Verify

Input: item id, batch id, AC subset, how to run the product.

- Verify black-box against the AC. Do not read the implementation rationale first.
- Choose checks that can falsify the AC, not checks that reproduce the implementation.
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
