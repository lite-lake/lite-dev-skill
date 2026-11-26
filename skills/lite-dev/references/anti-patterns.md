# Anti-patterns

Each one is a real failure mode of agent-driven development. The fix is a rule,
not more effort.

1. **Clarify while coding.** Questions become retro-fitted justifications. Fix:
   no design or code before `Status: clarified`.

2. **Design theatre.** A long design written after the code, or a design that
   restates the ticket. Fix: Phase A speaks the plan before writing; the handoff
   must let a fresh session start without chat history.

3. **Status by hand.** A status field drifts from reality. Fix: derive it; the
   tool reads files.

4. **Batch amnesia.** Only the first batch is designed; later batches are invented
   mid-flight. Fix: every AC appears in the batch table before implementation.

5. **Self-verification.** The implementer writes "tested" and the same context
   approves. Fix: separate verify context, black-box AC, evidence file.

6. **Gate as ritual.** The gate is run after committing, or failures are waived.
   Fix: gate before commit, full level, no waiver. Three failures means stop.

7. **Context hoarding.** The main session keeps implementing after the design,
   then runs out of context with half a batch uncommitted. Fix: update progress
   and hand off; the next session reads artifacts.

8. **Process police.** Refusing to release someone else's undocumented commit.
   Fix: reconcile, record adhoc, keep channel rules.

9. **Extension as escape hatch.** A project extension disables a core rule. Fix:
   extensions may add constraints and command mappings, never remove invariants.

10. **Docs as a second codebase.** Duplicated facts drift. Fix: one authority per
    fact; everything else links. Entry documents contain no version numbers,
    ports, dates, or counts that will age.

11. **Upstream success as evidence.** CI green means the build passed, not that
    the new artifact is deployed; a previous gate PASS is not evidence for this
    commit. Fix: evidence names the command and its output for the artifact you
    are closing; `done` refuses a designed item without it.

12. **Sleeping on a build.** A fixed sleep pulls the old image or reads a stale
    report. Fix: poll the timestamp or the status, with a bound, and stop when
    the bound expires.
