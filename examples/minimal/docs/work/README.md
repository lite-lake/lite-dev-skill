# Work items

One directory per item, filed under the month in its `created` date, created by
`flow.py new`:

```text
<YYYY-MM>/            e.g. 2026-11, from the item's created date
  <id>-<slug>/
    item.md            created by the tool; you edit the prose and AC
    design.md          optional; copied from the skill template for L/risky items
    implementation.md  optional; batch log during Phase B
    test-report.md     optional; evidence written by the verifier
```

Rules:

- Do not rename a directory away from its `<id>` prefix; `check` reports it.
- Do not move an item out of its month directory. The month comes from `created`,
  so `check` reports a mismatch instead of rewriting the path.
- Ids are `{date}-{type}-{time}` and sort in creation order; never write one by hand.
- `owner` is required. Change it with `flow.py claim <ID>` and commit the change.
- Do not add a status field. Status is derived from `## Clarify`, `design.md`, and `closed:`.
- Keep AC ids (`AC01`) stable; design batches and test reports reference them.
- Only the verifier ticks AC; only the orchestrator updates `## Implementation`.
