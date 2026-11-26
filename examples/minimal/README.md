# minimal

A runnable single-repo example for lite-dev. It exists to be copied and to be
used as an end-to-end acceptance test for the flow tool.

## Run the flow

From this directory:

```bash
SKILL=/path/to/lite-dev-skill/skills/lite-dev
git config --global lite-dev.owner "Your Name"   # once per person, per machine
python3 $SKILL/scripts/flow.py whoami            # what this machine resolves
python3 $SKILL/scripts/flow.py status
python3 $SKILL/scripts/flow.py new --title "Export CSV" --type REQ --size S
python3 $SKILL/scripts/flow.py check
python3 $SKILL/scripts/flow.py gate --level l1
python3 $SKILL/scripts/flow.py handoff <ID>      # the prompt for the next session
```

`flow.py` walks up from the current directory and finds `docs/flow/profile.toml`.

## What to look at

- `docs/flow/profile.toml` — the only project-specific file. Note that the gate
  levels map to commands the project already has.
- `docs/work/` — one directory per item, created by `flow.py new`.
- `src/calc.py`, `tests/test_calc.py` — something real for the gate to run.

## Typical first item

1. `new` with size S. Open `item.md`, answer or dismiss the clarifying questions,
   set `- Status: clarified`.
2. For S/M, no design is required: implement, run `check`, run `gate --level l3`.
3. Tick the AC boxes you can prove, then `flow.py done <ID>`.
4. `flow.py archive <ID>` when the item is history; `status` then counts it as
   archived instead of listing it.

For an L item, copy `design.md` from the skill's templates, speak the plan to a
human, record `Confirmed: yes`, run `design-ready`, then implement batch by batch.

## Notes

- On Windows, use `python` instead of `python3` if that is what your shell has.
- The example's `e2e` command is the same as `test` on purpose; replace it with a
  real end-to-end command in your own project.
- `[release] channels` is empty on purpose, so `flow.py release` only prints
  "no release channels configured". Add a channel and a runnable `gate_level`
  to try release recording; `release --record` runs the gate itself and refuses
  a dirty tree or an empty `--rollback`.
