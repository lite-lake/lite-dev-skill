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
or a bad `--since` exits 2. Debt never blocks anything.

## Watermark

The last release record for the channel (`source`) is the watermark. `--since`
overrides it. With no record, the whole history is inspected; use `--since` on a
large repository.

## Categories

1. **no work item** — no item id in the subject or body. Becomes an adhoc note
   in the next release record.
2. **missing work item** — the subject references an id that does not exist.
   Usually a typo or a deleted item.
3. **risky path without item** — touches a configured `[reconcile] risk_paths`
   entry (migrations, auth, deploy) with no item. Needs a targeted check.
4. **uncommitted** — a dirty tree. Resolve it or exclude it explicitly.

## Recording

If an item cannot be created in time, the release `--note` records the debt:
what it is, why there is no item, and what was checked instead. Next release,
reconcile again. Debt may persist; it may not be invisible.

## What not to do

- Do not create retroactive items to make the report green.
- Do not treat reconcile as approval, or ask a human to sign it.
- Do not relax channel rules (gate, rollback, record) because a change is adhoc.
