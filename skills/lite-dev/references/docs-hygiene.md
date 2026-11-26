# Docs hygiene

Invariant 9 says each fact has one home and entry documents carry no drifting
facts. `check` mechanises the part of it that can be decided from the files:

| Rule | Severity | What it means |
|---|---|---|
| relative links resolve | error | a link to a deleted or renamed file |
| every file is linked from its directory's `README.md` | warning | a file nobody can reach |
| every artifact in an item directory is mentioned in `item.md` | warning | a `test-report.md` the next session will miss |
| a release record repeats no `##` heading | error | two entries collided in an append-only file |
| entry documents pin no version, port, or date | warning | a copy of a fact that will drift |
| `[docs] decisions` exists and has a `README.md` | error | a decisions directory with no index |
| no active document links into `_archive/` | reported by the archive rule | history is reachable through the archive index, not from live docs |

## What counts as an entry document

Every file in `[docs] required` whose name is `README.md` or `AGENTS.md`. That
is where a version pin hurts most: it is the first thing a newcomer reads and
the last thing anyone updates.

The patterns are shapes, not a list of tools:

- a version pin: a known runtime word followed by `1.2` or `1.2.3`
- a port: `localhost:8080`, `127.0.0.1:3000`, `0.0.0.0:80`
- a date: `2026-11-26`

## What is deliberately not checked

- Links inside fenced blocks and inline code: examples must be free to show a
  path that does not exist yet.
- Target URLs containing `{`, `<`, or `$`: that is prose about a path, not a path.
- Whether the prose is true. A check can prove a link resolves; it cannot prove
  the sentence.

## Turning it down

`[docs] check_links = false` and `[docs] zero_fact = false` exist for a
migration, not as a permanent setting. A project that turns them off has to say
so in its own `AGENTS.md`, because the next session will otherwise assume the
checks ran.

## Archiving

`flow.py archive <ID>` moves a closed item to
`<work_dir>/_archive/<YYYY-MM>/<id>-<slug>/` and writes one row into
`<work_dir>/_archive/README.md`: item, title, date, reason.

The rules are the ones that keep history trustworthy:

- Only a closed item is archived; `--force` exists for an abandoned item, and the
  reason is then mandatory in practice.
- The move mirrors the working layout, so an archived item keeps its month
  bucket and its path stays guessable.
- Nothing is deleted. `unarchive` moves it back and removes the row.
- Active documents do not link into the archive: they link the archive index.
  A live document that points at `_archive/...` is a link that will be read as
  current.
- `status` lists archived items as a count and stops there; they are not part of
  the working set, but an id still resolves.
