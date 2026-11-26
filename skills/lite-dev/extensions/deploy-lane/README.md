# deploy-lane extension

A bundled extension for projects that deploy the same commit to more than one
environment. It only adds:

- command: `deploy_check`
- gate step: `l3 += deploy_check`

Enable it in the project profile:

```toml
[extensions]
enabled = ["deploy-lane"]
```

## The unit is a manifest

A deployment is recorded as one JSON file per environment, for example
`docs/releases/manifests/test-deployment.json`:

```json
{
  "environment": "test",
  "deployed_at": "2026-01-01T09:30:00Z",
  "operator": "alice",
  "git": { "api": "abc1234", "web": "def5678" },
  "images": [
    { "repo": "registry.example/api", "tag": "test-abc1234",
      "digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000" }
  ],
  "rollback": "test-abc0000"
}
```

The manifest is what makes a deployment repeatable: every component's commit,
every image's immutability, and one rollback target, in one file that a script
can read.

## What the check enforces

| Rule | Why |
|---|---|
| every field present and backfilled | a deployment recorded with `<placeholder>` did not happen |
| `deployed_at` is RFC3339 | free text cannot be ordered or diffed |
| `git.<component>` is a commit sha | "the latest one" is not a source |
| every image tag pins a commit, every digest is `sha256:` | promoting by alias ships something nobody tested |
| `rollback` is never blank | no rollback target, no irreversible step |
| `rollback: none` needs `first_deploy: true` | the first deployment has a different, stated risk |
| `--env <name>` matches every manifest | a test artifact cannot be recorded as a production one |

It checks **shape**, not content: the component names, registries, and
environments are the project's own.

## Two rules the check cannot enforce

- Each environment is built separately. An image built for one environment must
  never be deployed to another, even when the commit is identical: the digest is
  the only thing the record can be trusted on.
- After a deployment, observe it before calling it good. The window is a project
  decision; write the result into the same record.

## Relation to `release --record`

`flow.py release --record` records what **left this repository** on a channel:
source commit, gate result, rollback target. The manifest records what **arrived
in an environment**, component by component. Keep both: the release record is
the chain, the manifest is the destination.
