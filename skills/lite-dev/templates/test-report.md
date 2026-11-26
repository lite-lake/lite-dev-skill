---
item: <ID>
batch: B1-Bn
---

> One report per item, cumulative. Each verifier appends evidence; never
> overwrite a previous batch's rows. A later batch may append another
> `## Evidence` block, and `done` reads every block.
>
> `done` refuses an item without this file, without a `Verdict: PASS`, or
> without one evidence row per AC with a command and an output. Write the
> command you ran and what it printed; "tested" is not an output.

## Scope

- Batch:
- What was verified:

## Result

- Verdict: FAIL
- Reason:

## Evidence

| AC | Command | Output / artefact |
|---|---|---|
| AC01 | | |

## Defects

- None

## Notes

- Environment:
- Not covered:
