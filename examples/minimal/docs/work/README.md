# Work items

One directory per item, created by `flow.py new`:

```text
<id>-<slug>/
  item.md            created by the tool; you edit the prose and AC
  design.md          optional; copied from the skill template for L/risky items
  implementation.md  optional; batch log during Phase B
  test-report.md     optional; evidence written by the verifier
```

Rules:

- Do not rename a directory away from its `<id>` prefix; `check` reports it.
- Ids are `{date}-{type}-{rand}` and are unique across clones; never write one by hand.
- `owner` is required. Change it with `flow.py claim <ID>` and commit the change.
- Do not add a status field. Status is derived from `## Clarify`, `design.md`, and `closed:`.
- Keep AC ids (`AC01`) stable; design batches and test reports reference them.
- Only the verifier ticks AC; only the orchestrator updates `## Implementation`.
