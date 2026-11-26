---
name: lite-dev
description: Agent-first development flow for software projects. Use when implementing, fixing, designing, or releasing a change; creating or resuming a work item; deciding whether a change needs a design; running a gate; or verifying acceptance criteria. Triggers include "implement", "fix", "design", "release", "continue the work item", "run the gate".
license: BSD-2-Clause
---

# lite-dev

> Distribution: <https://github.com/lite-lake/lite-dev-skill>. The skill name and
> trigger are `lite-dev`; that repository packages it.

> Run every command from the project root.
> There is exactly one flow. Do not invent states, roles, or approvals.
> Tools: `init`, `new`, `status`, `check`, `design`, `design-ready`, `gate`,
> `done`, `drop`, `claim`, `whoami`, `handoff`, `archive`, `unarchive`,
> `release`, `reconcile`, `extensions`.

## 0. Four principles

1. You own the change end to end. The only approvals are business trade-offs and irreversible actions.
2. Small changes are done directly. Create a work item when the change spans days, modules, risky areas, or a release.
3. The machine gate is the only judge. "It works locally" is not evidence.
4. Confirmation is final. Once the human says "go with this plan", `design.md` is a record; do not ask for a second review unless scope, contracts, or the data model change.

## 1. Status is derived, never written

```text
need-clarify -> clarified -> designing -> ready -> done
                                   \-> dropped
```

`flow.py` derives status from files: the `- Status:` line in `## Clarify`, the
presence of `design.md` and its `status: ready`, and the `closed:` field.
Never edit a status by hand.

## 2. Route your reading (progressive disclosure)

| Situation | Read | Run |
|---|---|---|
| First session in a project | — | `init` (then `status`) |
| Any task starts | [references/clarify.md](references/clarify.md) | `flow.py status` |
| S, one session | nothing else | `new` → edit → `test-report` → `check` → `gate --level l3 --work <ID>` → `done` |
| M, one session with a design | [references/one-shot-vs-two-phase.md](references/one-shot-vs-two-phase.md) | `new` → `design` → `design-ready` → implement → `gate` → `done` |
| L, risky, multi-batch | [references/one-shot-vs-two-phase.md](references/one-shot-vs-two-phase.md) | `new` → design → `design-ready` |
| Phase B implementation | [references/roles.md](references/roles.md) | `gate --level l1` per batch |
| Session boundary or resume | — | `handoff <ID> [--batch Bx]` |
| Harness has no subagents | [references/harness-modes.md](references/harness-modes.md) | sequential roles |
| Releasing | [references/release-channels.md](references/release-channels.md) | `release --channel <name>` |
| More than one person or machine | [references/collaboration.md](references/collaboration.md) | set `lite-dev.owner`, then `new` |
| Others bypassed the flow | [references/reconcile.md](references/reconcile.md) | `reconcile` |
| Docs drifting (links, indexes, pins) | [references/docs-hygiene.md](references/docs-hygiene.md) | `check` |
| Retiring a finished item | — | `archive <ID>` |
| A project ships an extension | [references/extensions.md](references/extensions.md) | `extensions` |
| Stuck or repeated failure | [references/anti-patterns.md](references/anti-patterns.md) | — |

Read only the rows you need. SKILL.md plus one reference is usually enough.

`size` is a label, not the whole decision: `[design] required_for` decides whether
a design exists, and `[design] risk_paths` can force one at any size. M is still
one session, but a design is its record, not a second execution mode. `done`
always needs a report, a recorded full-level gate PASS, and an identity.

## 3. Clarify before you build

1. Restate the request in one sentence.
2. Ask at most five questions at once, each with a recommended default.
3. Write the answers into `## Clarify`, set `- Status: clarified`.

Cover: who uses it and where; what is in and out; existing data; who can see or
change it; how acceptance is proven; which release channel is affected.

Do not write a design or code before `clarified`. If the request is already
clear, write "None" and set `clarified` anyway.

## 4. Choose the execution mode

| Mode | Sessions | Use when |
|---|---|---|
| one-shot | 1 | copy, style, one-line bug; S; M when it fits one session (design still required if `required_for` says so); within half a day |
| two-phase | 2 | L, over five person-days, schema/permissions/new module, multi-batch |

Phase A is the design session. Phase B is a scheduling session that dispatches
**every** batch. Details: [references/one-shot-vs-two-phase.md](references/one-shot-vs-two-phase.md).

## 5. Work item commands

```bash
python3 <skill>/scripts/flow.py init [--adopt] [--baseline]
python3 <skill>/scripts/flow.py new --title "Export CSV" --type REQ --size M
python3 <skill>/scripts/flow.py status --mine
python3 <skill>/scripts/flow.py status --stale [--days N]
python3 <skill>/scripts/flow.py check [--work <ID>]
python3 <skill>/scripts/flow.py design <ID>
python3 <skill>/scripts/flow.py design-ready <ID>
python3 <skill>/scripts/flow.py gate --level l3 --work <ID>
python3 <skill>/scripts/flow.py claim <ID> [--takeover --reason "..."]
python3 <skill>/scripts/flow.py done <ID> [--owner "Name"]
python3 <skill>/scripts/flow.py drop <ID> [--reason "..."]
python3 <skill>/scripts/flow.py handoff <ID> [--batch Bx]
python3 <skill>/scripts/flow.py archive <ID> [--reason "..."]
python3 <skill>/scripts/flow.py whoami
python3 <skill>/scripts/flow.py release --channel staging [--confirm "..."] [--confirmed-by "Name"]
python3 <skill>/scripts/flow.py reconcile
python3 <skill>/scripts/flow.py extensions
```

- `init` writes what is missing and never replaces a file that exists: the
  profile (this install's version, the detected mainline), the required entry
  documents, and a routing block in `AGENTS.md` (after the title when one
  exists). Then it runs `check` and prints the next step. `--adopt` prints the
  ramp for a project that already has code and documents; `--baseline` records
  `HEAD` as `[reconcile] baseline` on a clean tree, so history before adoption is
  a baseline and not debt.
- `new` allocates `{date}-{type}-{time}` and creates
  `<work_dir>/<YYYY-MM>/<id>-<slug>/item.md`; the slug follows the title's script
  (Chinese stays Chinese, 30 characters max). It needs an identity (`--owner`,
  `$LITE_DEV_OWNER`, or `git config lite-dev.owner`).
- `check` validates fields, AC, design rules, evidence, and document hygiene
  (links, reachability, counts, decisions, exemptions); `--work` limits it to
  one item. A partial test report is a warning while the item is open.
- `design` copies `templates/design.md` into the item and fills `item:`; it
  refuses an unclarified item and an existing design.
- `design-ready` refuses an incomplete, unconfirmed, wrong-item, out-of-order,
  or cyclic design and writes `status: ready`.
- `gate` validates the item under `--work` (or the whole project), then runs the
  profile's commands for a level.
- `claim` reassigns the owner; commit it so teammates see the change. Another
  person's open item needs `--takeover --reason "..."`; a closed or archived
  item cannot be claimed.
- `done` refuses unchecked AC, a missing required design, a design that exists
  but is not ready, a missing `test-report.md`, a verdict other than PASS, an AC
  with no evidence row, a missing identity, and no recorded full-level gate PASS
  for the item. It records `closed_by` and warns when the closer is not the owner.
- `drop` retires an item that will not be delivered: it writes
  `closed: dropped`, `closed_by`, and the reason. It is the only supported way
  to reach the `dropped` state; a closed item cannot be dropped again.
- `status` shows `required` when the profile wants a design and `ready!` (with a
  warning) when a ready design no longer validates; `--stale` lists open items
  nobody has touched for more than `--days` (default 30), derived from git. It
  reports and exits 0.
- `handoff` prints a cold-start prompt built from the artifacts: paths, the
  handoff summary, batch progress, the next batch, dependencies, warnings, the
  gate command, and (for the full prompt) the commit gate. A blocked batch is
  named as blocked, a done batch is not dispatched again, and a draft design is
  not announced as confirmed. Use it at a session boundary; `--batch` prints
  the implement dispatch for one batch.
- `archive` moves a closed item to `<work_dir>/_archive/<YYYY-MM>/` and records
  it in that directory's README; `unarchive` moves it back. Archived items are
  read-only through the flow: `unarchive` before `done`, `claim`, `drop`, or
  `design-ready`. `--force` needs `--reason`.
- `whoami` prints the resolved identity and where it came from; run it on every
  machine.
- `release` plans; `--record` runs the gate and writes the channel record. A
  release that only adds records/archive commits is not debt; a clone behind its
  upstream is refused, and an unfetched clone cannot be detected, so pull first.
  `--confirmed-by` names the authorizer separately from the recorder.
- `reconcile` reports commits that bypassed the flow; it never blocks. With no
  release record yet it uses `[reconcile] baseline` (or `--since`), so a project
  that adopted the flow mid-history can see its debt; with neither it refuses and
  names the fix. It labels record-only commits as bookkeeping, still flags risky
  paths that carry an item id, and knows archived item ids.
- `extensions` shows what each enabled extension adds, including required docs
  and reconcile risk paths.

An id may be abbreviated to a unique prefix. Two matches is an error with the
candidates listed: use the full id, never guess.

### 5.1 Release and reconcile

- A release record is written only by `release --record`. It runs `check`, runs
  the configured `release.gate_level`, and refuses a dirty tree, a channel
  branch, an empty `--rollback`, a clone behind its upstream, or undocumented
  no-work-item commits.
- With `[release] confirm_risk_paths`, a source range that touches
  `[design] risk_paths` needs `--confirm "<the human's words>"`; `--confirmed-by`
  names the authorizer when it is not the recorder. Prose in the record is the
  point: a rollback answers "how do we undo it", confirmation answers "who
  said we may".
- Commits without work items are allowed. Write the debt into `--note`; never
  fabricate a work item to make the report green. Commits that only add release
  records or archive a work item are bookkeeping, not debt. `## Work items`
  never claims an id that does not exist; it labels it `(missing)`.
- `reconcile` is advisory and exits 0. It is not an approval gate. Two
  `risk_paths` lists exist: `[reconcile]` colours its report, `[design]` drives
  `--confirm`; a path in only one list is reported so the difference is visible.
- Details: [references/release-channels.md](references/release-channels.md),
  [references/reconcile.md](references/reconcile.md).

### 5.2 Extensions

Extensions may add commands, gate steps, required docs, and risk paths. They may
not replace a command, change a gate level, remove a rule, or alter the state
machine. The loader rejects unknown keys and incompatible `requires` ranges.
A bundled extension ships its scripts inside the skill and names them with
`{skill}`; the loader expands it, so nothing is hardcoded per machine.
Details: [references/extensions.md](references/extensions.md).

## 6. Writing a design

Only for sizes listed in `design.required_for` (normally M/L) or a change under
`risk_paths`. M is still one session; its design is the record of the plan.
Speak the plan in conversation first, then write the file. Start from
`templates/design.md` with `flow.py design <ID>`; do not hand-build the scaffold.

Required sections: Handoff, Diagram, Confirmation, Approach, Batches, Impact,
Verification, Rollback; Open Decisions must be empty. Handoff must stand alone:
Goal, Scope, Out, Verify, Rollback. The section headings are a parsing contract:
translate the prose, not the heading.

Batch rules: list every `B1..Bn` up front, in order, with no gaps; every AC
appears in at least one batch; a dependency must name an earlier batch (no
forward edges, no cycles, no self-dependency); contracts and data model first,
backend before frontend; after each batch the main branch builds and passes the
gate.

## 7. Gates

- Levels and commands come from `docs/flow/profile.toml`. Never invent a command.
- `l1` runs on every batch, `l2` before batch acceptance, `l3` before commit or release.
- A failing gate is fixed, not argued with. The same failure three times means stop and ask.
- `gate --work <ID>` validates that item and the profile's required documents,
  then runs the commands. `done` requires a PASS for the item at the strictest
  level in *this* clone; a project-wide run does not name the item. A bare
  `check` and a release still validate the project.
- `done` closes on the strictest level the profile defines, and `status`,
  `init`, and `done` say which one that is when it is not `l3`. l3 must be
  runnable locally; if it only exists in CI, wrap it as a local command that
  waits for that CI run.
- A change under `[gate] fallback_paths` (lock files, schema runs, toolchain pins)
  invalidates the cheap level: the gate says to run the strictest one.
- The strictest level's last PASS is remembered per clone. `status` and a cheaper
  gate tell you when it is stale; this is advisory, never a block.
- `[design] risk_paths` makes a change structural: without a ready design the gate
  warns, or blocks when `risk_gate = "block"`. `risk_exempt` is what keeps a
  documentation change about those paths from tripping the rule.

## 8. Independent verification

Implement and verify in different contexts. The verifier reads the AC and the
change, not the implementer's rationale. Every item—including S—has one
cumulative `test-report.md`: one row per AC with the command and its output.
A later batch appends its rows (or another `## Evidence` block); it never
overwrites an earlier batch's evidence. An implementer saying "tested" is not
evidence, and `done` refuses any item without a passing report, without one row
per AC, without a recorded full-level gate PASS, or without an identity.

## 9. Stop conditions (ask the human)

- The requirement is unclear or a business trade-off is needed.
- The plan is not confirmed.
- An irreversible action (data, permissions, credentials, release) has no rollback.
- A destructive schema change is required.
- The gate fails three times, or a batch fails verification twice.
- Scope must grow, or work must be borrowed from another item.
- Context is nearly exhausted: update `## Implementation`, then hand off.

## 10. Red lines

- Design or code before clarification.
- Writing `design.md` before the human agrees, or asking for a second review after agreement.
- Writing a status by hand.
- Skipping the gate, or calling a checklist "tested".
- Closing any item without a passing `test-report.md`, a recorded full-level
  gate PASS, and an identity; or filling an evidence cell with a placeholder.
- Recording a release over a risk path without the confirmation the profile asks for.
- Recording a release without `--record`, with a dirty tree, a behind clone, or
  with hidden debt.
- Letting an extension weaken a rule instead of adding one.
- A verifier approving their own implementation.
- Listing only "this round" of batches and deferring the rest.
- Leaving half-done work on main without a flag.
- Guessing which item an ambiguous id means, or editing an id by hand.
- Taking over someone's open item without `--takeover --reason "..."`.
- Claiming or dropping a closed item, or mutating an archived item instead of
  unarchiving it.
- Editing a recorded release's `source` or `previous`.
- Pinning a version, port, or date in an entry document instead of linking its one authority.
- Archiving an open item without `--force --reason`, or editing an archived item
  instead of unarchiving it.
- Force push, rewriting shared history, committing secrets.
- Weakening a core rule through an extension.

## References

- [Clarify](references/clarify.md)
- [One-shot vs two-phase](references/one-shot-vs-two-phase.md)
- [Roles](references/roles.md)
- [Harness modes](references/harness-modes.md)
- [Teams and machines](references/collaboration.md)
- [Release channels](references/release-channels.md)
- [Reconcile](references/reconcile.md)
- [Docs hygiene](references/docs-hygiene.md)
- [Extensions](references/extensions.md)
- [Anti-patterns](references/anti-patterns.md)
- [Invariants (source of truth)](references/invariants.md)
