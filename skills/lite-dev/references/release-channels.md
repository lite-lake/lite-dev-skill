# Release channels

Channels are declared in the profile; the flow does not assume that staging or
prod exists. A small project may have none. A framework may add a release train.

```toml
[release]
channels = ["staging", "prod"]
dir = "docs/releases"
gate_level = "l3"        # must exist in [gate]
```

## Commands

```bash
flow.py release                              # channels and the last record per channel
flow.py release --channel staging            # plan only: source, previous, commits, debt
flow.py release --channel staging --record \
  --rollback "redeploy <previous tag>" \
  --note "two chore commits have no work item"
```

`--record` is the only way to write a release. It enforces, in order:

1. `check` passes: broken artifacts block a release.
2. `gate_level` passes: FAIL means no record.
3. The working tree is clean.
4. The current branch is not one of the release channels.
5. `--rollback` is non-empty.
6. Commits without work items are written into `--note`.

The gate runs inside `--record`; a previous run is not evidence.

## Watermark

The latest record for the channel is the watermark. `source` is the commit the
release was cut from, `previous` is the record before it. `reconcile` and the
next `release` use `source` to decide what is new. Do not edit a recorded
`source`; write a new record instead.

The record is rendered from `templates/release.md`; headings and frontmatter
keys are a parsing contract. Commit the record before the next release;
otherwise the working tree is dirty and `--record` refuses to run.

## Promotion and rollback

The tool records; it does not push branches, build, or deploy.

- A channel branch accepts fast-forwards only. Never commit directly to it.
- After pushing, return to the main line; do not leave the workspace on a channel.
- Every channel needs a rollback target before the first irreversible step.
- A release with debt is allowed; a release with hidden debt is not.

## Hotfix

A hotfix is a one-shot item on the main line, released through the same path.
It still passes the gate and still writes a record; urgency lowers scope, not
evidence.
