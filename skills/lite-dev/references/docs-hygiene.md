# Docs hygiene

Invariant 9 says each fact has one home and entry documents carry no drifting
facts. `check` mechanises the part of it that can be decided from the files:

| Rule | Severity | What it means |
|---|---|---|
| relative links resolve | error | a link to a deleted or renamed file |
| no link target is an absolute path | warning | a path that resolves on one machine only |
| no link leaves the project root | warning | a target outside every declared repository |
| every directory index is reachable from `docs_dir/README.md` | warning | an index nobody can find |
| a directory of documents has a `README.md` | warning | no entry point for the subtree |
| every file is linked from its directory's `README.md` | warning | a file nobody can reach |
| every artifact in an item directory is mentioned in `item.md` | warning | a `test-report.md` the next session will miss |
| a release record repeats no `##` heading | error | two entries collided in an append-only file |
| entry documents pin no version, port, date, or count | warning | a copy of a fact that will drift |
| a decision's status and supersede pointers agree | error | a rewritten or dangling decision |
| `[docs] decisions` exists and has a `README.md` | error | a decisions directory with no index |
| an exemption has a reason and has not expired | error | a silence nobody reviewed |
| an exemption suppresses at least one issue | warning | a stale exception |
| no active document links into `_archive/` | warning | history read as current |
| every item has a passing test report | error at `done` | an AC tick standing in for evidence |
| every archived item has one index row | warning | the archive index drifting from the tree |

The test-report row is not a document rule: it is invariant 5, enforced where
the item closes. `check` reports it as a warning while the item is still open.
The archive-index row is a document rule: the index is the entry point for the
record store, so it must not drift from the tree.

## What counts as an entry document

Every file in `[docs] required` whose name is `README.md` or `AGENTS.md`. That
is where a version pin hurts most: it is the first thing a newcomer reads and
the last thing anyone updates.

The patterns are shapes, not a list of tools:

- a version pin: a known runtime word followed by `1.2` or `1.2.3`
- a port: `localhost:8080`, `127.0.0.1:3000`, `0.0.0.0:80`
- a date: `2026-11-26`
- a count: `3 services`, `2 个应用`, `5 处路由`

## Indexes and reachability

`docs_dir/README.md` is the root of the graph. Every directory index (`README.md`
or `index.md`) must be reachable from it by following links, and every directory
that holds markdown needs one. The per-directory rule only covered directories
that already had a README, which left a whole unreferenced subtree invisible.

Record stores are excluded: item directories under `work_dir` are listed by
`status`, release records are ordered by the commit graph. `[docs] stores` names
the project's own record and asset directories (globs allowed), so a requirement
tree or an asset library does not have to grow a README per folder. Demanding
index links for them would be noise, not reachability. This applies even if you add a
`docs/releases/README.md`: its records are not required to be linked from it.
The archive index is the exception: it is the entry point for archived items, so
`check` warns when an archived item has no row or a row has no item.

A document that cannot be described as one row in a route table probably should
not exist. Write the row first; if it does not make sense, the page has no
reader.

## Exemptions

A conflict between a rule and reality has two legal outcomes: fix the document,
or register the exception. Turning a check off for the whole project is not one
of them.

```toml
[[exempt]]
check = "links"            # links | index | artifact | archive_link | zero_fact |
                           # heading | absolute | escape
path = "docs/legacy"       # path prefix, relative to the project root
reason = "imported handbook, not maintained here"
until = "2027-03-31"
```

- Every field is required; the profile loader rejects a missing reason or date.
- An expired exemption is an error and silences nothing.
- An exemption that suppresses no issue is reported: the exception outlived the
  problem.
- Evidence is not exemptable. An exemption records drift, it does not waive an
  invariant.

## Decisions

A decision that changes is superseded, never rewritten. `check` enforces the
mechanics:

- `Status` is one of `proposed`, `accepted`, `rejected`, `superseded`,
  `deprecated`;
- an unused pointer is written as `none`, not left empty; the shipped template
  does this and passes its own checker;
- a `superseded` decision has `Superseded by:` pointing at a decision in the
  same directory;
- a decision that names a successor has the matching status;
- the chain terminates;
- ids are unique within the directory.

## What is deliberately not checked

- Links inside fenced blocks and inline code: examples must be free to show a
  path that does not exist yet.
- Target URLs containing `{`, `<`, or `$`: that is prose about a path, not a path.
- Whether the prose is true. A check can prove a link resolves; it cannot prove
  the sentence.

## Turning it down

`[docs] check_links = false` and `zero_fact = false` are migration switches, not
settings. Prefer one `[[exempt]]` entry per problem: it names the path, records
why, and expires. A project that still uses a global switch has to say so in its
own `AGENTS.md`, because the next session will otherwise assume the checks ran —
and `check` now reports the switch on every run, so the reminder cannot be lost.

The same failure with extra steps is an enabled check that inspects nothing:
`zero_fact = true` with no `README.md` or `AGENTS.md` in `[docs] required`.
`check` reports that as inert instead of passing quietly.

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
