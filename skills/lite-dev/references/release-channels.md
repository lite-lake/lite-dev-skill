# Release channels

Channels are declared in the profile; the flow does not assume that staging or
prod exists. A small project may have none. A framework may add a release train.

```toml
[release]
channels = ["staging", "prod"]
dir = "docs/releases"
gate_level = "l3"        # must exist in [gate]
mainline = "main"        # required once a channel exists
require_artifacts = false
confirm_risk_paths = false   # opt-in: a structural range needs --confirm
```

## Commands

```bash
flow.py release                              # channels and the last record per channel
flow.py release --channel staging            # plan only: source, previous, commits, debt
flow.py release --channel staging --record \
  --rollback "redeploy <previous tag>" \
  --artifact "app@sha256:..." \
  --note "two chore commits have no work item"
flow.py release --channel prod --record \
  --rollback "redeploy <previous tag>" \
  --confirm "ops approved the schema change on 2026-11-26"
```

`--record` is the only way to write a release. It enforces, in order:

1. `check` passes: broken artifacts block a release.
2. The working tree is clean.
3. The current branch is `[release] mainline`; a feature branch and a detached
   HEAD are refused. A clone behind its upstream is refused; an unfetched clone
   cannot be detected, so pull first.
4. The channel's records form one unbroken chain, and HEAD descends from its tip.
5. `--rollback` is non-empty; `--artifact` is present when the profile requires it.
6. Commits without work items must be listed in `--note`. Commits that only
   touch the profile, work items, or release records are bookkeeping and need no
   note.
7. With `confirm_risk_paths`, a range that touches `[design] risk_paths` has
   `--confirm`; `--confirmed-by` names the authorizer when it is not the
   recorder. The record keeps the human's words verbatim.
8. `gate_level` passes: FAIL means no record. The gate runs inside `--record`;
   a previous run is not evidence.
9. `--since` may start earlier than the recorded tip (a first-release baseline)
   but never later; it cannot skip debt between the tip and HEAD.

The recorder and the tool version are stored in the record (`by`, `tool`).

## Watermark

Records are ordered by the **commit graph**, never by filename or local clock.
The tip is the record no other record descends from, so two machines that record
independently cannot disagree about which one is latest.

- `source` is the commit the release was cut from; `previous` is the source of
  the record before it, or `none` for the first one.
- A record whose `source` or `previous` is missing from the clone stops the
  release: fetch first.
- A source that is not a descendant of the tip means this clone is behind or on
  a different history. Pull or rebase; the tool will not record an older source.
- Two records that are not on one history are divergent. Do not delete or edit
  the evidence. If the bad record came from a stale clone, revert the commit
  that added it (a new commit), then record again from the true tip. The tool
  refuses to record while the chain is ambiguous; the revert is the repair.
- An unreadable record (missing or non-sha `source`) is an error, not a record
  to skip.

Do not edit a recorded `source` or `previous`; write a new record instead.

## One channel per repository

A commit belongs to one repository, so in a workspace a channel names its
repository and the chain is ordered by that repository's history:

```toml
[[release.channel]]
name = "svc-a"
repo = "svc-a"
mainline = "main"
```

A name in `channels` keeps its old meaning — the control repository. The record
gains `repo:`, and a record without that field is read as the control repository,
so an existing record store needs no migration. `--record` refuses when the
channel's repository or the control repository is dirty; another repository
being dirty is a warning, because its uncommitted work is not part of this
release. A change that ships several repositories writes one record per channel;
the records are the evidence, an umbrella note is a convenience.

## Channels that ship together

When several channels go out as one event, declare a group:

```toml
[[release.group]]
name = "platform"
channels = ["svc-a", "svc-b"]
```

`release --group platform` plans every channel and prints each one; `--record`
refuses if any channel is not recordable (naming it), runs the gate once for the
whole group, writes each channel's record, then writes one index record:

```
docs/releases/group-platform-2026-11-30.md
```

The index lists `Channel | Repo | Source | Record` and carries no `channel` or
`source` of its own. That is deliberate: the chains remain per repository, so the
index can never become a watermark and can never diverge from them. Losing it
loses a summary, not evidence.

The record is rendered from `templates/release.md`; headings and frontmatter
keys are a parsing contract. The filename contains the ISO date and the short
source (`staging-2026-10-31-a1b2c3.md`), so records from different machines do
not collide. Commit the record before the next release; otherwise the working tree
is dirty and `--record` refuses to run.

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

Before switching to main, park dirty WIP (stash or a pushed WIP commit); git
will refuse to switch over it. A hotfix under `[design] risk_paths` still needs
a short ready design at any size, or a range that avoids the path; there is no
size exemption. With `confirm_risk_paths`, the record needs `--confirm` and,
when the authorizer is not the recorder, `--confirmed-by`.
