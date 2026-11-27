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
>
> Split by the outcome a human can observe, not by layer: a batch that produces
> nothing observable is merged into its neighbour. A contract or schema batch is
> the exception — everything waits on it, so it goes first and on its own.
>
> `Parallel` names a group (for example `P1`) whose batches run at the same time.
> Batches in one group must name disjoint repositories — a shared worktree is one
> writer — and none may depend on another in its group. Leave it `—` otherwise.

| Batch | Goal | Repo | AC | Depends | Parallel |
|---|---|---|---|---|---|
| B1 | | . | AC01 | — | — |
| B2 | | . | AC02 | B1 | — |

## Impact

- Contracts:
- Data / schema:
- Permissions:

## Verification

> Every AC needs a command or a concrete check plus where the evidence lives.

| AC | Command | Environment | Evidence |
|---|---|---|---|
| AC01 | | | |

## Decision Defaults

> The plan cannot name every detail. This table is what lets implementation go
> on without a round trip: when a detail is left open and it is not a scope,
> contract, data-model, or security decision, take the smallest default here and
> record it as a deviation. Scope and contract gaps still stop and come back to
> this file. Keep the rows you would defend later; delete the rest.

| Situation | Default |
|---|---|
| The contract and the data model disagree | The data model wins; correct the contract's wording in the same change |
| A status code or field name is not written down | Follow the resource's existing endpoints and fields |
| A UI detail is not covered | Reuse the existing visual and interaction rules; do not add a component |
| An external environment is not available | Record the blockage and continue the batches that do not need it; never fake it |

## Rollback

TBD

## Open Decisions

None
