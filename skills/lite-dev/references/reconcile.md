# Reconcile

Multi-person reality: not every commit has a work item, docs and tests can lag,
and blocking the main line for process is worse than the debt. Reconcile makes
the debt visible without becoming an approval gate.

## Command

```bash
flow.py reconcile                    # the only configured channel
flow.py reconcile --channel staging
flow.py reconcile --since <sha>      # override the watermark
flow.py reconcile --json --verbose
```

It always exits 0 when it can produce a report. Missing git, an unknown channel,
a bad `--since`, or a release record it cannot order exits 2. Debt never blocks
anything; an ambiguous channel history does.

## No release channel yet

A project that adopted the flow mid-history has no release record to anchor the
range, and that is exactly when the debt is worth seeing. Give it a baseline:

```toml
[reconcile]
baseline = "<commit>"     # `flow.py init --baseline` writes it
```

Then `reconcile` inspects `baseline..HEAD` and labels the run `channel: baseline`.
`--since <commit>` does the same for one run. The baseline is a record, not a
switch: it says "history before adoption is not inspected here", and commits
after it stay debt. Set it only on a clean tree, so it names a commit somebody
meant.

Without channels and without a baseline, `reconcile` exits 2 and names both
fixes; it does not silently inspect the whole history and call it a report.

Every commit that only touches the profile, the work store, or the release store
is bookkeeping, not debt: adopting the flow changes the profile, and a release
or archive writes records. Risk paths are reported before that classification,
so a profile change that touches one is still named.

## Watermark

The watermark is the ancestry tip of the channel's records, not the newest
filename. `--since` overrides it and must be an ancestor of HEAD. With no
record, the whole history is inspected; use `--since` on a large repository.
`[reconcile] baseline` fills that gap only while a channel has no record: once a
record exists, the watermark wins.
On `release --record`, `--since` may start earlier than the recorded tip (a
first-release baseline) but never later; it cannot skip debt between the tip
and HEAD.

A record that references a commit missing from this clone, two records that are
not on one history, or a `previous` that does not match the record before it is
reported as an error. The range cannot be trusted until it is fixed, so
`reconcile` exits 2 instead of printing a misleading report.

## Categories

1. **no work item** — no item id in the subject or body. Becomes an adhoc note
   in the next release record. A commit that only adds release records or
   archives an item is **bookkeeping**, not debt; it stays visible in its own
   category and does not need a note.
2. **missing work item** — the subject references an id that does not exist.
   Usually a typo or a deleted item. Archived ids are known, so history does not
   become missing after archival.
3. **risky path without item** — touches a configured `[reconcile] risk_paths`
   entry (migrations, auth, deploy) with no item. Needs a targeted check.
4. **risky path with item** — the same path under a commit that names an item.
   It is still reported: an unrelated id must not hide a migration.
5. **uncommitted** — a dirty tree. Resolve it or exclude it explicitly.

`[reconcile] risk_paths` colours this report. `[design] risk_paths` drives
`release --confirm`; a path in only one list is called out by `release` so the
split is visible. They have different jobs; keep both honest.

## Recording

If an item cannot be created in time, the release `--note` records the debt:
what it is, why there is no item, and what was checked instead. Next release,
reconcile again. Debt may persist; it may not be invisible.

## What not to do

- Do not create retroactive items to make the report green.
- Do not treat reconcile as approval, or ask a human to sign it.
- Do not relax channel rules (gate, rollback, record) because a change is adhoc.
