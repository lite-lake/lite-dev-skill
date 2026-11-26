# <DECISION-ID>

> One decision per file. A decision that changes is superseded, never rewritten:
> set `Status: superseded`, and add `Superseded by:` pointing at the new file.
> Design documents and the flow link here instead of restating the reasoning.

- Status: proposed
- Date:
- Owner:
- Supersedes:
- Superseded by:

> `Status` is one of `proposed`, `accepted`, `rejected`, `superseded`,
> `deprecated`. `Superseded by:` is required when the status is `superseded`,
> names a file in this directory, and the chain must terminate. `check` enforces
> the enum, the pointers, and the absence of cycles.

## Context

What forced a decision, and what would break if none was made.

## Decision

One paragraph. The rule someone can apply without reading the rest.

## Alternatives

| Option | Why not |
|---|---|
| | |

## Consequences

- What becomes true once this is in force.
- What it costs, and what it forbids.
