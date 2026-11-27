# Clarify

Purpose: turn a vague request into a checkable one without guessing.

## Ask at most five questions, once

Every question carries a recommended default, so the human can answer "yes" or
change one thing:

| # | Question | Recommended default |
|---|---|---|
| 1 | Who uses this, in what situation? | the current user and the main path |
| 2 | What is explicitly in, and what is explicitly out? | smallest change that meets the need |
| 3 | What happens to existing data? | no migration; read-only compatibility |
| 4 | Who can see or change it? | current permissions, no new role |
| 5 | How is acceptance proven, and which release channel? | one observable check; no release |

Add domain questions only when they change the answer. Never ask a question you
can answer from the repository.

## Record the answers

In `item.md`:

```markdown
## Clarify

- Status: clarified
- Questions:
  - Q: ...
    A: ...
- Confirmed assumptions:
  - ...
```

`flow.py` reads the `Status` line; `design-ready` refuses an unclarified item,
and so does `check` once a `design.md` already exists. If nothing needs asking,
write `None` and still set
`clarified`: the status means "the ambiguity was resolved", not "a meeting happened".

## Signs you are doing it wrong

- Asking while starting to code, and treating silence as agreement.
- More than five questions, or a second round of questions before any work.
- Questions without defaults, which push every decision back to the human.
- Recording answers only in chat, so the next session cannot see them.
