# Work items

One directory per item, filed under the month in its `created` date, created by
`flow.py new`:

```text
<YYYY-MM>/            e.g. 2026-11, from the item's created date
  <id>-<slug>/
    item.md            created by the tool; you edit the prose and AC
    design.md          required for M/L/risky; flow.py design <ID> scaffolds it
    implementation.md  optional; batch log during Phase B
    test-report.md     cumulative evidence; one row per AC, appended per batch
```

Rules:

- Do not rename a directory away from its `<id>` prefix; `check` reports it.
- Do not move an item out of its month directory. The month comes from `created`,
  so `check` reports a mismatch instead of rewriting the path.
- The slug comes from the title and follows its script: English words join with
  `-`, Chinese stays Chinese. Keep a Chinese title within 20 characters; the
  slug caps at 30.
- Ids are `{date}-{type}-{time}` and sort in creation order; never write one by hand.
- `owner` is required. Change it with `flow.py claim <ID>`; taking over someone
  else's open item needs `--takeover --reason "..."`. A closed item cannot be
  claimed.
- Do not add a status field. Status is derived from `## Clarify`, `design.md`, and `closed:`.
  Use `flow.py drop <ID> --reason "..."` for `dropped`.
- Keep AC ids (`AC01`) stable; design batches and test reports reference them.
- Only the verifier ticks AC; only the orchestrator updates `## Implementation`.
- One cumulative `test-report.md` per item; append evidence per batch, never
  overwrite an earlier batch's rows. `done` needs it, a full-level gate PASS,
  and an identity.
- A finished item stays here until it is archived: `flow.py archive <ID>` moves it
  to `_archive/<YYYY-MM>/` and records it in `_archive/README.md`. Nothing is
  deleted, and a live document links the archive index, never the item. Archived
  items are read-only until `flow.py unarchive <ID>`.
- At a session boundary, `flow.py handoff <ID>` prints the prompt the next
  session needs; do not retype it.
