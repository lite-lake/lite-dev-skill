# Work items

One directory per item, filed by the month in its `created` date; `flow.py new`
creates it. Do not rename or move an item directory, and never write a status by
hand: the tool derives it from `## Clarify`, `design.md`, and `closed:`.

- `item.md` — the request, its AC, and the batch log.
- `design.md` — written by `flow.py design <ID>` when the profile requires one.
- `test-report.md` — cumulative evidence, one row per AC.
