# Teams, machines, and parallel sessions

lite-dev assumes a trunk-based flow: one mainline per repository, short-lived
branches merged quickly, everyone running the gate. A workspace with several
repositories has one mainline each; a channel names the repository it records. Coordination is files plus git; there is no
server and no lease. Four rules make that safe.

## Identity

Set one identity per person, once, on every machine:

```bash
git config --global lite-dev.owner "Your Name"
```

`new`, `claim`, and `release --record` take `--owner` (or `--by`), then fall
back to `$LITE_DEV_OWNER`, then to that config. `done` has no flag: it reads the
environment and the config. There is no fallback to `user.name`: a wrong owner
is worse than a clear error. The owner is written into `item.md`, so teammates
and `status --mine` see it.

`flow.py whoami` prints the identity that will be used and which of the three
sources it came from. Run it after setting up a second machine; an env var that
disagrees with the global config is the usual way one person becomes two owners.

A team can pin the canonical spellings:

```toml
[project]
owners = ["Alice Chen", "Bob Li"]
```

`check` then warns about any item owned by someone outside the list, and about a
non-canonical spelling of a rostered name (for example `Alice  Chen` when the
roster says `Alice Chen`). It is a warning, not an error: a one-off helper may
still own an item. Without a roster, `check` still warns when two owners differ
only by case or spacing.

## Ids

An id is `{date}-{type}-{time}` (for example `20261126-REQ-3yharx`). `{time}` is
the millisecond of the local day in six characters, so ids list in creation
order for one timezone and one day, and a clone allocates one without a lock or
a pull. Two creators that stamp the same millisecond get the same code: `check`
reports the duplicate id instead of merging them, and `new` bumps past any code
already on disk. That is the one case where pulling first matters. `find_item`
accepts the full id or a unique prefix; if a prefix matches more than one item
it lists them and exits 2. It never guesses. Never hand-write an id: `check`
validates it against `[id] format`.

The directory slug follows the title's script: `Fix-Login-Bug` for English,
`修复登录超时` for Chinese, with no transliteration either way. A Chinese slug
caps at 30 characters and `check` warns past 20. The rule reads the title, not
`[project] language`, so a Chinese title in an English-language project keeps its
characters. Set `git config core.quotepath false` in the project, or `git status`
prints those paths as `\346\226...` escapes; `check` warns once such an item
exists and the setting is not off.

`{time}` is local wall-clock time. It orders items created on the same local day
and nowhere else: two machines in different timezones, or a clock that moves
backwards (a daylight-saving fall-back hour, an NTP correction), can hand out a
code that sorts before an earlier one. That is safe because the code is a label
and a sort key, never a watermark — release order comes from the commit graph.
The only real collision is the same millisecond, described above.

## Claiming

`new` sets the owner. `claim <ID>` reassigns it. When the item is still open and
someone else owns it, `claim` refuses until you pass
`--takeover --reason "..."`: a mistyped id must not silently take work away from
a teammate, and the reason is written into the item (`takeover_by`,
`takeover_reason`). A closed item cannot be claimed; create a new item instead.
An archived item is read-only until `unarchive`. `status --mine` lists your
items. Ownership is a coordination signal, not a lock: two people editing one
item still merge their work.

`done` requires an identity, writes `closed_by` into the item, and warns when
the closer is not the owner. It still closes: the verifier may be a different
person from the implementer, and invariant 5 wants exactly that. The closer
must also have run the item's full-level gate in that clone; the ledger is
local, so a teammate cannot close on your PASS.

If two people really need one item, one owns it and the other reviews. Parallel
edits to the same `item.md` — AC ticks, the progress row, the clarify answers —
will conflict, and git will ask you to decide which facts to keep.

## The gate is scoped, the release is not

`gate --work <ID>` validates that item plus the profile's required documents. A
teammate's broken WIP item does not block your batch. A bare `check` and
`release --record` validate the whole project; that is the integration point.

Pin `[flow] requires` and `[flow] reviewed` in the profile. They are required:
a machine outside the window stops with a profile error, and a machine on a
different minor still loads but warns. That is why a teammate sees the same
CHANGELOG range you reviewed, instead of a gate that quietly changed rules.

## Releases

- Only a channel's mainline branch may record: its `[[release.channel]]`
  `mainline`, or `[release] mainline` when the channel does not name one. A
  feature branch, a detached HEAD, or a channel branch is refused.
- The watermark is the ancestry tip of the channel's records, not the newest
  filename. A record whose `source` is not in your clone means "fetch first".
- Your HEAD must descend from the recorded tip, and `release --record` refuses
  a clone that is behind its upstream. An **unfetched** clone cannot be
  detected locally: `behind 0` proves nothing until you fetch. Pull before you
  record; this is a hard precondition, not a suggestion.
- Divergent records, a broken `previous` chain, or an unreadable record stop the
  release. Do not edit a record. If a stale clone already recorded one, revert
  the commit that added the bad record (a new commit), then record again from
  the true tip.
- Commit the record before the next release. That commit is bookkeeping, not
  debt; `reconcile` will not make you write a note for it. Include `--artifact`
  when the profile requires artefacts.

## One person, several machines

1. Set `lite-dev.owner` globally, not per repository, and keep `$LITE_DEV_OWNER`
   out of your shell profile unless it holds the same string. Run `whoami` on
   each machine; it names the source it used.
2. `new`, then commit and push the item before switching machines. An uncommitted
   item does not exist anywhere else.
3. Pull before `new`: it is still safe without pulling (the time code rarely
   collides), but your `status` is otherwise blind to teammates' work.
4. `status` prints `checkout <branch> <sha> (upstream: behind N, ahead M)` from
   the remote-tracking ref, so it costs no network and is only as fresh as your
   last fetch. In a workspace it prints one `repos` line instead — control,
   then each declared repository with its branch, HEAD, distance, and dirty
   count — and says which declared repositories are not checked out here.
   `status --repo <path>` narrows the item list to the ones that repository's
   history mentions. `behind 0` on a clone that has not fetched proves nothing.
5. Never record a release from a machine that has not pulled the last record.
6. `status` reflects the current checkout only; switch branches or pull before
   asking where an item stands. In a workspace a stale repository is visible as
   `behind N` on its own line. `status --json` is the same data for a script or
   a dashboard. "Work is never half-done on main" stays a human rule.

## Conflicts

- `## Implementation` rows and AC checkboxes are the shared edit surface. Only
  the orchestrator updates the progress row; only the verifier ticks AC.
- A merge conflict in `item.md` is resolved by keeping both sides' facts: AC
  ticks from the verifier, progress from the orchestrator. Never re-tick an AC
  you cannot prove.
- A conflict in `docs/releases/` means two machines recorded independently. The
  filename is derived from channel, day, and source, so the same source on two
  clones collides on purpose. Stop, inspect with `reconcile`, and record again
  from the true tip. If the two records were merged anyway, the chain refuses
  them on the next release: two records cannot both follow the tip.
