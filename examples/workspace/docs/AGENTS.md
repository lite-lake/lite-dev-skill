# Agent instructions

This workspace uses lite-dev. Read the skill's `SKILL.md` before implementing,
fixing, designing, or releasing anything.

- Start every session with `flow.py status`; it lists the repositories and their
  checkouts.
- The profile is `docs/flow/profile.toml`; commands, gate levels, and the
  repository list live there.
- Work items live in `docs/work/`. Never edit a status by hand; the tool derives
  it.
- The gate runs this project's own commands, scoped to the repositories the
  change touches. Do not invent a different one.
- Product requirements live outside the work item; the item links them and owns
  the implementation record.
