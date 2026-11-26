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
> Tools: `new`, `status`, `check`, `design-ready`, `gate`, `done`, `release`,
> `reconcile`, `extensions`.

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
| Any task starts | [references/clarify.md](references/clarify.md) | `flow.py status` |
| S/M, one session | nothing else | `new` → edit → `check` |
| L, risky, multi-batch | [references/one-shot-vs-two-phase.md](references/one-shot-vs-two-phase.md) | `new` → design → `design-ready` |
| Phase B implementation | [references/roles.md](references/roles.md) | `gate --level l1` per batch |
| Harness has no subagents | [references/harness-modes.md](references/harness-modes.md) | sequential roles |
| Releasing | [references/release-channels.md](references/release-channels.md) | `release --channel <name>` |
| Others bypassed the flow | [references/reconcile.md](references/reconcile.md) | `reconcile` |
| A project ships an extension | [references/extensions.md](references/extensions.md) | `extensions` |
| Stuck or repeated failure | [references/anti-patterns.md](references/anti-patterns.md) | — |

Read only the rows you need. SKILL.md plus one reference is usually enough.

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
| one-shot | 1 | copy, style, one-line bug; S/M; expected within half a day |
| two-phase | 2 | L, over five person-days, schema/permissions/new module, multi-batch |

Phase A is the design session. Phase B is a scheduling session that dispatches
**every** batch. Details: [references/one-shot-vs-two-phase.md](references/one-shot-vs-two-phase.md).

## 5. Work item commands

```bash
python3 <skill>/scripts/flow.py new --title "Export CSV" --type REQ --size M
python3 <skill>/scripts/flow.py status
python3 <skill>/scripts/flow.py check
python3 <skill>/scripts/flow.py design-ready <ID>
python3 <skill>/scripts/flow.py gate --level l1 --work <ID>
python3 <skill>/scripts/flow.py done <ID>
python3 <skill>/scripts/flow.py release --channel staging
python3 <skill>/scripts/flow.py reconcile
python3 <skill>/scripts/flow.py extensions
```

- `new` allocates the id and creates `<work_dir>/<id>-<slug>/item.md`.
- `check` validates fields, AC, links, and design rules; exit 1 on errors.
- `design-ready` refuses an incomplete design and writes `status: ready`.
- `gate` runs the profile's commands for a level; `check` runs first.
- `done` refuses unchecked AC and a missing required design.
- `release` plans; `--record` runs the gate and writes the channel record.
- `reconcile` reports commits that bypassed the flow; it never blocks.
- `extensions` shows what each enabled extension adds.

### 5.1 Release and reconcile

- A release record is written only by `release --record`. It runs `check`, runs
  the configured `release.gate_level`, and refuses a dirty tree, a channel
  branch, an empty `--rollback`, or undocumented no-work-item commits.
- Commits without work items are allowed. Write the debt into `--note`; never
  fabricate a work item to make the report green.
- `reconcile` is advisory and exits 0. It is not an approval gate.
- Details: [references/release-channels.md](references/release-channels.md),
  [references/reconcile.md](references/reconcile.md).

### 5.2 Extensions

Extensions may add commands, gate steps, required docs, and risk paths. They may
not replace a command, change a gate level, remove a rule, or alter the state
machine. The loader rejects unknown keys and incompatible `requires` ranges.
Details: [references/extensions.md](references/extensions.md).

## 6. Writing a design

Only for sizes listed in `design.required_for` (usually M/L) or risky changes.
Speak the plan in conversation first, then write the file.

Required sections: Handoff, Diagram, Confirmation, Approach, Batches, Impact,
Verification, Rollback; Open Decisions must be empty. Handoff must stand alone:
Goal, Scope, Out, Verify, Rollback.

Batch rules: list every `B1..Bn` up front; every AC appears in at least one
batch; contracts and data model first, backend before frontend; after each
batch the main branch builds and passes the gate.

## 7. Gates

- Levels and commands come from `docs/flow/profile.toml`. Never invent a command.
- `l1` runs on every batch, `l2` before batch acceptance, `l3` before commit or release.
- A failing gate is fixed, not argued with. The same failure three times means stop and ask.
- `gate` runs `check` first: broken artifacts cannot pass a gate.

## 8. Independent verification

Implement and verify in different contexts. The verifier reads the AC and the
change, not the implementer's rationale. Evidence goes into `test-report.md`.
An implementer saying "tested" is not evidence.

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
- Recording a release without `--record`, with a dirty tree, or with hidden debt.
- Letting an extension weaken a rule instead of adding one.
- A verifier approving their own implementation.
- Listing only "this round" of batches and deferring the rest.
- Leaving half-done work on main without a flag.
- Force push, rewriting shared history, committing secrets.
- Weakening a core rule through an extension.

## References

- [Clarify](references/clarify.md)
- [One-shot vs two-phase](references/one-shot-vs-two-phase.md)
- [Roles](references/roles.md)
- [Harness modes](references/harness-modes.md)
- [Release channels](references/release-channels.md)
- [Reconcile](references/reconcile.md)
- [Extensions](references/extensions.md)
- [Anti-patterns](references/anti-patterns.md)
- [Invariants (source of truth)](references/invariants.md)
