# Teams, machines, and parallel sessions

lite-dev assumes a trunk-based flow: one mainline, short-lived branches merged
quickly, everyone running the gate. Coordination is files plus git; there is no
server and no lease. Four rules make that safe.

## Identity

Set one identity per person, once, on every machine:

```bash
git config --global lite-dev.owner "Your Name"
```

`new`, `claim`, and `release --record` read `--owner` (or `--by`), then
`$LITE_DEV_OWNER`, then that config. There is no fallback to `user.name`: a
wrong owner is worse than a clear error. The owner is written into `item.md`, so
teammates and `status --mine` see it.

## Ids

An id is `{date}-{type}-{time}` (for example `20261126-REQ-3yharx`). `{time}` is
the millisecond of the local day in six characters, so ids list in creation
order and a clone allocates one without a lock or a pull. Two creators that
stamp the same millisecond get the same code: `check` reports the duplicate id
instead of merging them, and `new` bumps past any code already on disk. That is
the one case where pulling first matters. `find_item` accepts the full id or a
unique prefix; if a prefix matches more than one item it lists them and exits 2.
It never guesses. Never hand-write an id: `check` validates it against
`[id] format`.

`{time}` is local wall-clock time. On a daylight-saving fall-back day the hour
repeats, so ids created then are not strictly ordered and could in principle
collide with one from the same hour before the change.

## Claiming

`new` sets the owner. To take over an item, run `claim <ID>` and commit the
change, otherwise nobody else can see it. `status --mine` lists your items.
Ownership is a coordination signal, not a lock: two people editing one item
still merge their work.

## The gate is scoped, the release is not

`gate --work <ID>` validates that item plus the profile's required documents. A
teammate's broken WIP item does not block your batch. A bare `check` and
`release --record` validate the whole project; that is the integration point.

Pin `[flow] requires` in the profile. It is required: a machine running a
different skill version stops with a profile error instead of running a gate
with different rules.

## Releases

- Only the `[release] mainline` branch may record. A feature branch, a detached
  HEAD, or a channel branch is refused.
- The watermark is the ancestry tip of the channel's records, not the newest
  filename. A record whose `source` is not in your clone means "fetch first".
- Your HEAD must descend from the recorded tip. A stale clone is refused instead
  of silently recording an older source.
- Divergent records, a broken `previous` chain, or an unreadable record stop the
  release. Resolve them; do not edit history.
- Commit the record before the next release. Include `--artifact` when the
  profile requires artefacts.

## One person, several machines

1. Set `lite-dev.owner` globally, not per repository.
2. `new`, then commit and push the item before switching machines. An uncommitted
   item does not exist anywhere else.
3. Pull before `new`: it is still safe without pulling (the time code rarely
   collides), but your `status` is otherwise blind to teammates' work.
4. Never record a release from a machine that has not pulled the last record.
5. `status` reflects the current checkout only. Switch branches or pull before
   asking where an item stands; "work is never half-done on main" stays a human
   rule.

## Conflicts

- `## Implementation` rows and AC checkboxes are the shared edit surface. Only
  the orchestrator updates the progress row; only the verifier ticks AC.
- A merge conflict in `item.md` is resolved by keeping both sides' facts: AC
  ticks from the verifier, progress from the orchestrator. Never re-tick an AC
  you cannot prove.
- A conflict in `docs/releases/` means two machines recorded independently. Stop,
  inspect with `reconcile`, and record again from the true tip.
