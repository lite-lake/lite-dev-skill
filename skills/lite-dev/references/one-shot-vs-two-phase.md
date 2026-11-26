# One-shot vs two-phase

## Choose

| Signal | One-shot | Two-phase |
|---|---|---|
| Size | S / M | L |
| Estimate | within half a day | over five person-days |
| Surface | one file or one module | schema, permissions, new module, cross-cutting contract |
| Batches | one | two to five |
| Sessions | one | design session + scheduling session |

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
3. Only after a clear yes, write `design.md` and copy the same summary into it.
4. The design must list **every** batch up front. No "this round", no "stage 1".
5. Do not write production code or create a feature branch. Temporary experiments are not committed.
6. Run `flow.py design-ready <ID>`; it refuses AC gaps, batch gaps, missing
   rollback, placeholders, and an unconfirmed plan.
7. Commit the docs and end the session. Leave a copy-pasteable Phase B prompt.

If the estimate is over ~50 person-days, suggest one independent review after
the plan is agreed. It is a suggestion, not a gate; record the human's decision
in `## Confirmation`.

## Phase B: scheduling session

The main session does not write code. For each batch:

1. **implement** — fresh context, only the item id, batch id, design path, repo
   path, the batch's AC subset, and the gate command.
2. **verify** — fresh context, black-box against the batch's AC. At most two rounds.
3. **commit** — only after PASS; the gate runs in full, one commit per repo per batch.
4. **bookkeeping** — update `## Implementation`, then start the next batch.

Never stop between batches to ask "continue?". Batch completion is not a stop
condition. Stop only for the conditions in SKILL.md §9.

## Phase B handoff prompt

```text
Continue work item <ID>.
Read: docs/work/<dir>/item.md (Clarify, AC, Implementation) and
      docs/work/<dir>/design.md (Handoff, Batches).
Implement batches <Bx..By> in order. For each: implement -> verify -> commit,
then update ## Implementation. Do not redesign. Do not stop between batches.
Gate: python3 <skill>/scripts/flow.py gate --level l1 --work <ID>
```

## If the design has a gap

- Missing detail: update `design.md`, rerun `design-ready`, continue.
- Scope, contract, or data model change: stop and return to Phase A. Do not
  silently drift.
