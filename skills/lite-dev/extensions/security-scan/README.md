# security-scan extension

A bundled extension that fails the gate when a **git-tracked** file looks like a
committed credential. It only adds:

- command: `security_scan`
- gate step: `l3 += security_scan`

Enable it in the project profile:

```toml
[extensions]
enabled = ["security-scan"]
```

## What it checks

Shapes, not specific values:

| Rule | Shape |
|---|---|
| `private-key` | `-----BEGIN ... PRIVATE KEY-----` |
| `cloud-access-key` | `AKIA`/`ASIA`/`LTAI` prefixed identifiers |
| `credentialed-url` | `scheme://user:password@host` |
| `secret-assignment` | `secret/token/password/api_key = "…"` with a long value |
| `jwt` | three base64url segments |
| tracked sensitive file | `.env`, `*.pem`, `*.key`, `.p12`, `.pfx`, `.keystore`, `.jks`, `.netrc` |

It scans `git ls-files`, so nothing untracked and nothing inside `.git` is read;
binary files and files over 512 KiB are skipped.

## Allowlist

A pattern that is genuinely fine goes in `docs/flow/security-allow.txt`, one
path prefix per line (`#` starts a comment). A single line can also be cleared
inline with a `lite-dev: allow` comment.

```text
tests/fixtures/keys/     # test fixtures, not real credentials
docs/examples/*.md
```

Prefer the allowlist to a loose rule: a scan that is easy to silence becomes
silenced everywhere.

## Limits

- It is a shape matcher, not a secret scanner. Rotating a leaked value is still
  the only fix; removing the line is not enough.
- The allowlist is project data. Turning the rule off for a whole language or
  directory is how this check stops finding anything.
- The command prints findings and exits 1; a project that wants a warning
  instead can append the step to `l2` rather than `l3` in its own copy.
