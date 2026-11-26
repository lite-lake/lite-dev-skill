# AGENTS.md — minimal

This project uses lite-dev. Before implementing, fixing, designing, or releasing
anything, read `<path-to-lite-dev-skill>/skills/lite-dev/SKILL.md`.

- Profile: `docs/flow/profile.toml` (commands and gate levels live there).
- Start every session with `python3 <path-to-lite-dev-skill>/skills/lite-dev/scripts/flow.py status`.
- Work items live in `docs/work/`. Do not edit a status by hand; the tool derives it.
- Ids are generated; an owner is required. Take over an item with `flow.py claim <ID>`.
- The gate is the project's own commands. Do not invent a different one.

Sizes S and M run as one-shot. Size L requires `design.md` and a human-confirmed
plan before any code.
