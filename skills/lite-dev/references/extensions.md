# Extensions

An extension is a declarative add-on. It lets a framework, a platform
convention, or a language profile ship its commands and extra constraints
without forking the flow.

## Enable

```toml
[extensions]
enabled = ["go-service"]
dir = "docs/flow/extensions"
```

Resolution order: `<project>/<dir>/<name>/extension.toml`, then
`<skill>/extensions/<name>/extension.toml`. If both exist, that is an error:
keep exactly one copy.

## Format

```toml
name = "go-service"
version = "1.0.0"
description = "Go service commands"
requires = ">=0.7.0,<1.0"

[commands]
go_build = "go build ./..."

[gate]
l1 = ["go_build"]

[docs]
required = ["docs/design/README.md"]

[reconcile]
risk_paths = ["migrations/"]
```

- `requires` is mandatory. `>=0.2,<0.3` is explicit; a bare `0.2` means
  `>=0.2.0,<0.3.0`; a full `X.Y.Z` means exactly that version.
- `version` is the extension's own version.
- Allowed keys only: `name`, `version`, `description`, `requires`, `commands`,
  `gate`, `docs`, `reconcile`, `detect`. Anything else is an error, so a typo
  cannot silently do nothing.
- `[docs]` may only contain `required`; `[reconcile]` may only contain `risk_paths`.
- `[[detect]]` proposes adoption values, it does not merge into the profile:
  `file` is a marker path, `command` is what follows from it, `note` replaces the
  evidence line. `init --plan` offers it when the marker exists; only
  `init --apply` writes. See [adoption](adoption.md).
- A command may contain `{skill}`. The loader replaces it with the installed
  skill directory (shell-quoted), which is how a bundled extension runs a script
  it ships next to its `extension.toml` without hardcoding a machine path.

## Merge rules

| Key | Effect |
|---|---|
| `[commands]` | added; a name collision with a different command is an error |
| `[gate]` | steps appended to the level, deduplicated; level must be l1/l2/l3 |
| `[docs] required` | appended, deduplicated |
| `[reconcile] risk_paths` | appended, deduplicated |
| `[[detect]]` | offered by `init --plan`; never written without `--apply` |

Additions only. An extension cannot replace a command, change a gate level,
remove a required document, alter the state machine, or waive an invariant.

## Inspect

```bash
flow.py extensions
```

Prints the lite-dev version, each extension's source (project or bundled), its
`requires` range, and exactly what it adds: commands, gate steps, required
documents, and reconcile risk paths.

## Bundled

| Extension | Adds | Use when |
|---|---|---|
| `go-service` | build/vet/test commands and Go risk paths; build output goes to a temp directory | the repository is a Go service |
| `security-scan` | `security_scan` at l3; fails on credentials in the index or untracked non-ignored files | always, unless another scanner covers it |
| `deploy-lane` | `deploy_check` at l3; validates deployment manifests | one commit ships to more than one environment |

Bundled extensions ship their scripts inside
`extensions/<name>/`; copy the directory into `docs/flow/extensions/<name>/` to
change its behaviour, and keep exactly one copy.

## Shipping an extension from a framework

Keep `extension.toml` and a README in the framework repository, for example
`flow/extension.toml`, and tell users to copy or symlink it to
`docs/flow/extensions/<name>/`. Bump `requires` when the flow's invariants
change. An extension is trusted project configuration: it contains shell
commands, so review it like a build script.

Bundled examples: `extensions/go-service/`, `extensions/security-scan/`,
`extensions/deploy-lane/`.
