# One-shot vs two-phase

## Choose

| Signal | One-shot | Two-phase |
|---|---|---|
| Size | S; M when it fits | L |
| Design | none for S; M/L require it when `design.required_for` says so | required |
| Estimate | within half a day | over five person-days |
| Surface | one file or one module | schema, permissions, new module, cross-cutting contract |
| Batches | one | two to five |
| Sessions | one | design session + scheduling session |

M is the awkward middle: it is still one session, but if the profile lists M in
`design.required_for`, write the design first and keep the batches small. Size
does not override a `risk_paths` change; that needs a design at any size.

When unsure, prefer one-shot for reversible changes and two-phase when a wrong
contract would be expensive to undo.

## Phase A: design session

1. Read the relevant design, contracts, and code. Read-only commands are fine.
2. **Speak the plan before writing any file.** It must include:
   - one page: goal / scope / out of scope / affected modules / contract changes / risks / rollback;
   - an ASCII or Mermaid diagram: components and data flow, or the key journey before → after;
   - two or three trade-offs: options, cost, decision;
   - questions only the human can answer;
   - the explicit question: "shall I write this into design.md?"
3. Only after a clear yes, run `flow.py design <ID>` (or copy
   `templates/design.md`) and fill it; the scaffold is not a plan.
4. The design must list **every** batch up front, `B1..Bn` in order, with no
   forward dependency. No "this round", no "stage 1". Batches in one `Parallel`
   group must name disjoint repositories; with one repository the column is `—`.
5. Fill `## Decision Defaults` with the details you are willing to settle during
   execution (a status code, a field name, wording, which existing component to
   use). The human confirms these with the plan, which is what makes continuing
   without a round trip safe. A gap they do not cover is a design gap.
6. Do not write production code or create a feature branch. Temporary experiments are not committed.
7. Run `flow.py design-ready <ID>`; it refuses AC gaps, batch gaps, missing
   rollback, placeholders, an empty defaults table, a parallel group that shares a
   repository, and an unconfirmed plan.
8. Commit the docs and end the session. Leave a copy-pasteable Phase B prompt.

If the estimate is over ~50 person-days, suggest one independent review after
the plan is agreed. It is a suggestion, not a gate; record the human's decision
in `## Confirmation`.

## Phase B: scheduling session

The main session does not write code. For each batch:

1. **implement** — fresh context, only the item id, batch id, design path, repo
   path, the batch's AC subset and acceptance set, and the gate command. Batches
   in one parallel group may be dispatched together; each keeps its own scope.
2. **verify** — fresh context, black-box against the batch's ACs. Accept only the
   ACs this batch is the first to name; for an AC accepted in an earlier batch,
   run regression for what this change touches. At most two rounds. Append the
   batch's evidence to the item's cumulative `test-report.md`; never overwrite
   earlier rows.
3. **commit** — only after PASS; the full gate runs, one commit per repo per batch.
4. **bookkeeping** — update `## Implementation`, then start the next batch. A
   concurrent group is written by the orchestrator after the group returns, so no
   two implementers write the file at once.

Never stop between batches to ask "continue?". Batch completion is not a stop
condition. Stop only for the conditions in SKILL.md §9.

## Phase B handoff prompt

```text
Continue work item <ID>.
Read: docs/work/<YYYY-MM>/<dir>/item.md (Clarify, AC, Implementation) and
      docs/work/<YYYY-MM>/<dir>/design.md (Handoff, Batches, Decision Defaults).
Implement batches <Bx..By> in order. For each: implement -> verify -> commit,
then update ## Implementation. Do not redesign. Do not stop between batches.
Batch <Bx> dispatch: python3 <skill>/scripts/flow.py handoff <ID> --batch <Bx>
Gate: python3 <skill>/scripts/flow.py gate --level l1 --work <ID>
```

## If the design has a gap

- A detail `## Decision Defaults` covers: take the default, record the deviation
  with its reason, continue.
- Any other missing detail: update `design.md`, rerun `design-ready`, continue.
- Scope, contract, data model, or security change: stop and return to Phase A.
  Do not silently drift.
