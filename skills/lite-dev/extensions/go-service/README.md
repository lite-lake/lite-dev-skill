# go-service extension

A bundled, declarative extension for Go services. It only **adds**:

- commands: `go_build`, `go_test`, `go_vet`
- gate steps: `l1 += go_build`, `l2 += go_test`, `l3 += go_vet`
- reconcile risk paths: `migrations/`, `internal/auth/`

Enable it in the project profile:

```toml
[extensions]
enabled = ["go-service"]
```

Rules:

- An extension may add commands, gate steps, required docs, and risk paths.
- It may not replace a command, change a gate level, remove a document, or
  change the state machine. Collisions and unknown keys are errors.
- `requires` is mandatory; the loader refuses an incompatible lite-dev version.

A framework can publish its own extension in the same shape: keep it in the
framework repository and copy it to `docs/flow/extensions/<name>/`, or ship it
next to the skill.
