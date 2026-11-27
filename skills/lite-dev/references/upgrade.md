# Upgrading lite-dev

The version has three components, and each means a different amount of work.

| Change | Meaning | What the tool does |
|---|---|---|
| Z (patch) | a compatible fix | loads; no warning |
| Y (minor) | may be incompatible | loads; `status`, `check`, `gate` warn; `init --upgrade` shows the CHANGELOG; applying `flow.reviewed` records the review |
| X (major) | a contract change | refuses to load; `init --upgrade` shows the breaking sections and the checklist; applying needs `--accept-major` |

The project's record is `[flow] reviewed` in `docs/flow/profile.toml`: the exact
version it was last reconciled with. `[flow] requires` is the window the tool
derives, not a value to tune by hand.

## Read the drift first

```bash
flow.py version          # running, reviewed, drift, and the next command
flow.py version --json   # the same facts for a script
```

`version` answers even when the profile cannot load, which is exactly when a
major crossing needs it. `drift` is one of `patch`, `minor`, `major`,
`older-minor`, `older-major`, or `unknown` (no recorded baseline).

## A minor (Y) review

1. Run `flow.py init --upgrade`. It prints `review:` and every CHANGELOG
   section between `reviewed` and the running version.
2. Read them. Look for profile keys, template changes, and new checks; the
   tool shows the evidence, not a verdict.
3. Run `flow.py init --plan` for values the repository proves, and
   `flow.py extensions` to confirm every enabled extension admits the version.
4. Run `flow.py check`, then the strictest gate level the project wires.
5. Apply both proposals:

   ```bash
   flow.py init --upgrade --apply flow.requires --apply flow.reviewed
   ```

6. Commit the profile with the change that needed the upgrade. The warning
   clears because `reviewed` now equals the running version.

`--apply flow.requires` alone is not enough: `reviewed` would sit outside the
new window, and `profile.load` rejects that, so the profile does not load until
`flow.reviewed` is applied too. Applying only `flow.reviewed` leaves the old
window in place; the tool prints a note while `flow.requires` is still pending.

## A major (X) check

The tool prints the same sections, marks breaking ones with `[breaking]`, and
adds this checklist. `--apply` refuses until it sees `--accept-major`.

1. Read every section in the range, especially the breaking ones.
2. Re-read `invariants.md` and `SKILL.md`. Headings are a parsing contract, and
   a rule may have gained a check.
3. Run `flow.py extensions`; a bundled extension may have moved its own
   `requires`.
4. Run `flow.py init --plan`; a new required document or profile key may be a
   rung now.
5. Run `flow.py check` and the strictest gate level on the project.
6. Record the outcome in the item, design, or release note, then rerun with
   `--accept-major`.

## Downgrades

Do not lower `reviewed` to make an older install load. `requires` refuses a
version below its floor, and `version` names the version to install. If the
review itself was wrong, correct it with a new commit and a reason; the profile
is the record, not a place to escape a warning.

## What is not stored

There is no "upgraded" flag and no upgrade log beyond the profile change and the
CHANGELOG. `reviewed` plus the committed profile is the whole state, so two
clones agree on what was reviewed.
