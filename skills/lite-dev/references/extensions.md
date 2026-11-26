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
requires = ">=0.3.1,<0.4"

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
  `gate`, `docs`, `reconcile`. Anything else is an error, so a typo cannot
  silently do nothing.
- `[docs]` may only contain `required`; `[reconcile]` may only contain `risk_paths`.

## Merge rules

| Key | Effect |
|---|---|
| `[commands]` | added; a name collision with a different command is an error |
| `[gate]` | steps appended to the level, deduplicated; level must be l1/l2/l3 |
| `[docs] required` | appended, deduplicated |
| `[reconcile] risk_paths` | appended, deduplicated |

Additions only. An extension cannot replace a command, change a gate level,
remove a required document, alter the state machine, or waive an invariant.

## Inspect

```bash
flow.py extensions
```

Prints the lite-dev version, each extension's source (project or bundled), its
`requires` range, and exactly what it adds.

## Shipping an extension from a framework

Keep `extension.toml` and a README in the framework repository, for example
`flow/extension.toml`, and tell users to copy or symlink it to
`docs/flow/extensions/<name>/`. Bump `requires` when the flow's invariants
change. An extension is trusted project configuration: it contains shell
commands, so review it like a build script.

Bundled example: `extensions/go-service/`.
