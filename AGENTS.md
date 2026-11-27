# AGENTS.md — working on lite-dev-skill

This repository is the distribution for the `lite-dev` skill. The skill name and
trigger stay `lite-dev`; the repository is `lite-dev-skill`.

Read `skills/lite-dev/references/invariants.md` first. It outranks this file and
every template.

## Rules

1. **No project facts inside the skill.** `skills/lite-dev/` must not contain a
   repository name, build command, branch model, or service name. Those belong in
   a project's `docs/flow/profile.toml`. If you need an example, use `.` and a
   generic command.
2. **Headings are a contract.** `## AC`, `## Batches`, `## Handoff`, etc. are
   parsed by `scripts/flowlib`. Renaming one is a breaking change.
3. **Keep `SKILL.md` small.** It is always loaded. Put depth in `references/` and
   add a row to the routing table instead of a new section.
4. **The deterministic layer is tested.** Run:

   ```bash
   python3 -m unittest discover -s skills/lite-dev/scripts/tests -v
   python3 -m unittest discover -s scripts/tests -v
   ```

   New parsing or derivation logic needs a test. The acceptance test runs the
   real CLI against a copy of `examples/minimal`.
5. **Extensions may add, never remove.** Do not add an escape hatch that waives
   an invariant in `spec/invariants.md`.
6. **Profile commands are executable input.** Never interpolate untrusted content
   into a command or a generated profile.
7. **Docs ship in two languages.** `README.md` pairs with `README.zh.md`, and
   `CHANGELOG.md` pairs with `CHANGELOG.zh.md`. Both halves of a pair change in
   the same commit, in the same section order, and every new section lands in
   both. The Chinese file mirrors the English structure section by section; only
   the prose is translated. Headings that `scripts/flowlib` parses stay English
   in both. Do not let one language drift ahead.
8. **Prefer the hardest carrier.** A new rule starts as far left as it fits:
   generator, gate step, check, template, prose, habit. `human` and `partly` in
   `references/invariants.md` are debts: when you add or change an invariant,
   name the mechanisation candidate. An escape hatch is a record with a reason
   and an expiry (`[[exempt]]`), never a permanent switch.

## Remotes

`origin` (GitHub) is the only place history is written. `origin-cnb`
(<https://cnb.cool/lite-lake/lite-dev-skill>) is a read-only replica that
mainland-China users clone from. cnb does not sync from GitHub, so keeping the
replica current is our job. It carries commits and tags; issues may be opened on
either, but GitHub is where they get discussed.

Enable the mirror once per clone:

```bash
git config core.hooksPath .githooks
```

A push to `origin` then also updates `origin-cnb`, but only after a dry run
against GitHub passes, so a push git would reject never moves the replica ahead.
When cnb is unreachable the push stops with the repair spelled out rather than
skipping quietly: `git push --no-verify` pushes GitHub alone, then
`python3 scripts/push_mirror.py --sync` repairs the replica. `--sync` sends only
refs GitHub has and prunes replica refs it does not; after GitHub's history is
rewritten, `--sync --force` is the deliberate repair.

## Before you finish

- Run the unit tests and the `examples/minimal` acceptance:
  `new → check → status → design-ready → gate → done`.
- Update `CHANGELOG.md` **and** `CHANGELOG.zh.md`; note breaking changes
  explicitly. Same for `README.md` / `README.zh.md`.
- `python3 scripts/push_mirror.py --check` passes: the cnb replica matches
  `origin`.
- Nothing is published before 1.0.0: change the protocol freely and keep both
  changelogs honest. From 1.0.0, a change to an invariant requires a major
  version bump and a breaking-change note.

## Style

- Python standard library only. No dependencies.
- Errors are actionable: say what to fix, not only what failed.
- English for code, headings, and tool output; prose files may be translated.
