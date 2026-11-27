#!/usr/bin/env python3
"""Keep the read-only cnb replica in step with GitHub.

`origin` (GitHub) is the only place history is written. `origin-cnb` is a
read-only replica that mainland-China users clone from, so it must never be
ahead of `origin` and should never lag behind it.

Usage (from the repository root):
    python3 scripts/push_mirror.py --check        # compare origin with the replica
    python3 scripts/push_mirror.py --sync         # make the replica equal origin
    python3 scripts/push_mirror.py --sync --force # the same, for a rewritten origin
    python3 scripts/push_mirror.py hook <remote> <url>   # called by pre-push

`hook` mirrors the refs git is already pushing, but only after a dry run against
`origin` passes, so a push git rejects can never leave the replica ahead. A cnb
outage stops the push with instructions: `git push --no-verify` pushes GitHub
alone, and `--sync` repairs the replica later. CI runs `--check`, so a bypassed
hook is visible rather than silent.

Nothing here knows the mirror's URL or the repository name; both live in git
config, and the URL a clone has is the URL it mirrors to.
"""
from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterable

ORIGIN = "origin"
MIRROR = "origin-cnb"
TIMEOUT = 120.0
IGNORED_PREFIXES = ("refs/pull/",)
# git runs pre-push for `git push --dry-run` too, so the pushes this tool makes
# must carry a mark that stops the hook re-entering itself.
BYPASS_ENV = "LITE_DEV_MIRRORING"


class MirrorError(RuntimeError):
    """A failure with a sentence a human can act on."""


def git(
    *args: str,
    stdin: str | None = None,
    timeout: float | None = None,
    mirroring: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, BYPASS_ENV: "1"} if mirroring else None
    try:
        return subprocess.run(
            ["git", *args],
            input=stdin,
            stdin=None if stdin is not None else subprocess.DEVNULL,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError as exc:
        raise MirrorError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise MirrorError(
            f"`git {' '.join(args)}` did not finish within {timeout:g}s"
        ) from exc


def first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return "no output"


def short(sha: str | None) -> str:
    return "-" if sha is None else sha[:7]


def has_remote(name: str) -> bool:
    return git("remote", "get-url", name).returncode == 0


def ls_remote(remote: str) -> dict[str, str]:
    """Every ref the remote has, minus the ones a replica never carries."""
    result = git("ls-remote", remote, timeout=TIMEOUT)
    if result.returncode != 0:
        raise MirrorError(
            f"`git ls-remote {remote}` failed: {first_line(result.stderr)}"
        )
    refs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        sha, tab, ref = line.partition("\t")
        if not tab or ref == "HEAD" or ref.startswith(IGNORED_PREFIXES):
            continue
        if ref.endswith("^{}"):  # the peeled value of an annotated tag
            continue
        refs[ref] = sha
    return refs


def is_zero_sha(value: str) -> bool:
    return bool(value) and set(value) == {"0"}


def refspecs_for_hook(lines: Iterable[str]) -> list[str]:
    """Turn pre-push stdin (`<local ref> <local sha> <remote ref> <remote sha>`)
    into refspecs the replica can take."""
    refspecs: list[str] = []
    for line in lines:
        parts = line.split()
        if len(parts) != 4:
            continue
        local_ref, local_sha, remote_ref, _remote_sha = parts
        if is_zero_sha(local_sha):
            refspecs.append(f":{remote_ref}")
        elif not local_ref.startswith("("):
            refspecs.append(f"{local_ref}:{remote_ref}")
    return refspecs


def mirror_failure(reason: str) -> int:
    print(f"mirror: {MIRROR} not updated: {reason}", file=sys.stderr)
    print(
        "  Re-run the push when cnb is reachable, or push GitHub alone with\n"
        "  `git push --no-verify` and repair the replica afterwards with\n"
        "  `python3 scripts/push_mirror.py --sync`.",
        file=sys.stderr,
    )
    return 1


def cmd_hook(remote: str, _url: str) -> int:
    if os.environ.get(BYPASS_ENV):
        return 0
    if remote != ORIGIN:
        # Pushing the replica itself (or any other remote): never re-enter,
        # or the hook would mirror its own mirror forever.
        return 0
    if not has_remote(MIRROR):
        # A clone without the replica — a fork, or a contributor who never
        # configured it. Nothing to keep in step.
        return 0

    refspecs = refspecs_for_hook(sys.stdin)
    if not refspecs:
        return 0

    preview = git(
        "push", "--dry-run", ORIGIN, *refspecs, timeout=TIMEOUT, mirroring=True
    )
    if preview.returncode != 0:
        print(
            f"mirror: {MIRROR} left untouched; {ORIGIN} would reject this push: "
            f"{first_line(preview.stderr)}",
            file=sys.stderr,
        )
        print(
            "  If the push should happen anyway, run it, then "
            "`python3 scripts/push_mirror.py --check`.",
            file=sys.stderr,
        )
        return 0

    try:
        result = git("push", MIRROR, *refspecs, timeout=TIMEOUT, mirroring=True)
    except MirrorError as exc:
        return mirror_failure(str(exc))
    if result.returncode != 0:
        return mirror_failure(first_line(result.stderr))

    targets = ", ".join(refspec.rsplit(":", 1)[-1] for refspec in refspecs)
    print(f"mirror: {len(refspecs)} ref(s) updated on {MIRROR}: {targets}")
    return 0


def drift(
    github: dict[str, str], replica: dict[str, str]
) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for ref in sorted(set(github) | set(replica)):
        want, have = github.get(ref), replica.get(ref)
        if want == have:
            continue
        if want is None:
            rows.append(("extra", ref, "-", short(have)))
        elif have is None:
            rows.append(("missing", ref, short(want), "-"))
        else:
            rows.append(("differs", ref, short(want), short(have)))
    return rows


def cmd_check() -> int:
    try:
        github = ls_remote(ORIGIN)
        replica = ls_remote(MIRROR)
    except MirrorError as exc:
        print(f"mirror check: {exc}", file=sys.stderr)
        print(
            f"  Check the {MIRROR} URL with `git remote -v`, then retry.",
            file=sys.stderr,
        )
        return 1

    rows = drift(github, replica)
    if not rows:
        print(f"mirror check: {len(github)} ref(s) on {MIRROR} match {ORIGIN}")
        return 0

    width = max(len(ref) for _, ref, _, _ in rows) + 2
    print(f"mirror check: {len(rows)} ref(s) out of step ({ORIGIN} is authoritative)")
    for state, ref, want, have in rows:
        print(f"  {state:<8} {ref:<{width}} {ORIGIN}={want:<7} {MIRROR}={have}")
    print(f"  run `python3 scripts/push_mirror.py --sync` to repair {MIRROR}")
    return 1


def cmd_sync(force: bool) -> int:
    """Make the replica equal `origin`, never a commit `origin` lacks."""
    try:
        github = ls_remote(ORIGIN)
        replica = ls_remote(MIRROR)
    except MirrorError as exc:
        print(f"mirror sync: {exc}", file=sys.stderr)
        return 1

    args = ["push", MIRROR]
    pushed = 0
    for ref in sorted(github):
        if force and ref in replica:
            args.append(f"--force-with-lease={ref}:{replica[ref]}")
        args.append(f"{ref}:{ref}")
        pushed += 1
    extras = sorted(set(replica) - set(github))
    args.extend(f":{ref}" for ref in extras)

    if not pushed and not extras:
        print(f"mirror sync: {MIRROR} has nothing to take")
        return cmd_check()

    try:
        result = git(*args, timeout=TIMEOUT, mirroring=True)
    except MirrorError as exc:
        print(f"mirror sync: {exc}", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print(
            f"mirror sync: {MIRROR} rejected the push: {first_line(result.stderr)}",
            file=sys.stderr,
        )
        print(
            "  A ref missing locally: run `git fetch origin --prune`, then retry.\n"
            "  A replica ref with history GitHub does not have: only a rewrite of\n"
            f"  {ORIGIN} explains that; re-run `--sync --force` once you are sure.",
            file=sys.stderr,
        )
        return 1

    print(f"mirror sync: {pushed} ref(s) sent to {MIRROR}")
    return cmd_check()


USAGE = """\
Keep the read-only cnb replica in step with GitHub.

    python3 scripts/push_mirror.py --check        compare origin with the replica
    python3 scripts/push_mirror.py --sync         make the replica equal origin
    python3 scripts/push_mirror.py --sync --force the same, for a rewritten origin

Exit codes: 0 in step, 1 out of step or failed. `hook` is called by
.githooks/pre-push; enable it once per clone with:

    git config core.hooksPath .githooks
"""


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(USAGE, end="")
        return 0
    if argv[0] == "hook":
        if len(argv) != 3:
            print("mirror: hook needs <remote> <url>", file=sys.stderr)
            return 2
        return cmd_hook(argv[1], argv[2])
    if argv[0] == "--check":
        return cmd_check()
    if argv[0] == "--sync":
        unknown = [arg for arg in argv[1:] if arg != "--force"]
        if unknown:
            print(f"mirror: unknown argument {unknown[0]}; see --help", file=sys.stderr)
            return 2
        return cmd_sync(force="--force" in argv[1:])
    print(f"mirror: unknown argument {argv[0]}; see --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
