---
item: <ID>
status: draft
---

# <ID> design

> Section headings are a parsing contract: keep them English and translate the
> prose. Batches are `B1..Bn` in order; a dependency must point backwards.

## Handoff

> Must be readable without the rest of this file. A fresh session starts here.

- Goal:
- Scope:
- Out:
- Verify:
- Rollback:

## Diagram

```text
<components and data flow, or the key user journey: current -> changed>
```

## Confirmation

- Confirmed: no
- Date:
- Source: conversation
- Note: a clear "go with this plan" in conversation is final. This file is the
  record; no second review unless scope, contracts, or the data model change.

## Approach

TBD

## Batches

> List every batch up front (B1...Bn). Every AC must appear in at least one
> batch. Contracts and data model first, backend before frontend. After each
> batch the main branch must build and pass the gate.

| Batch | Goal | Repo | AC | Depends |
|---|---|---|---|---|
| B1 | | . | AC01 | — |
| B2 | | . | AC02 | B1 |

## Impact

- Contracts:
- Data / schema:
- Permissions:

## Verification

> Every AC needs a command or a concrete check plus where the evidence lives.

| AC | Command | Environment | Evidence |
|---|---|---|---|
| AC01 | | | |

## Rollback

TBD

## Open Decisions

None
