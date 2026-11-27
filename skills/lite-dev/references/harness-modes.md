# Harness modes

The flow assumes two contexts can exist: one that implements and one that
verifies. How you get them depends on the harness.

## Mode A: subagents available

- Start a fresh subagent per role and per batch.
- Pass only ids and paths; the subagent reads the artifacts.
- This is the intended mode: it prevents the implementer's assumptions from
  leaking into verification.
- A subagent that returns nothing gets one retry with the same task, including
  when it fails for transport reasons; check that the tree holds no half-done
  work before resending, and pass the paths of what it already produced so the
  retry does not start from zero. If the retry also returns nothing, treat it as
  a blockage: record it and continue the batches that do not need it; stop and
  ask only when it blocks every remaining batch. Do not reinterpret silence as
  success.

## Mode B: single context only

This is a weaker mode. Say so in `implementation.md`; a one-shot item with no
`implementation.md` declares it in `## Notes` of `item.md`. Do not pretend the
independence is real.

- Between roles, write a handoff file and re-read only the artifacts:
  item, design batch row, changed diff, test report.
- Do not carry the implementation narrative into verification. If you remember
  why a shortcut was taken, state it as a risk, not as a justification.
- Verify from the AC list, in a fixed order, and record the command output.
- Prefer smaller batches: the longer one context runs, the more the roles blur.

## Mode C: no file system access

Not supported. The flow depends on artifacts on disk being the source of truth.
Use a harness that can read and write the project.
