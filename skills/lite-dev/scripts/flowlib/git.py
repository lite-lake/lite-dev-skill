"""Thin git wrapper. Release and reconcile need facts, not a git library."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    """Git is missing, or the directory is not a repository."""


@dataclass
class Commit:
    sha: str
    subject: str
    body: str

    @property
    def short(self) -> str:
        return self.sha[:7]


def _run(root: Path, *args: str, check: bool = True) -> str:
    process = _exec(root, *args)
    if check and process.returncode != 0:
        message = (process.stderr or process.stdout).strip()
        raise GitError(message or f"git {' '.join(args)} failed")
    return process.stdout


def _exec(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc


def is_repo(root: Path) -> bool:
    output = _run(root, "rev-parse", "--is-inside-work-tree", check=False).strip()
    return output == "true"


def git_dir(root: Path) -> Path | None:
    """The absolute git directory, or None outside a repository.

    Local state (the gate ledger) lives here: inside the repository but outside
    the working tree, so it is never a dirty path and never gets committed.
    """
    process = _exec(root, "rev-parse", "--absolute-git-dir")
    if process.returncode != 0:
        return None
    text = process.stdout.strip()
    return Path(text) if text else None


def config_get(root: Path, key: str) -> str:
    """Read a git config value; empty when it is not set."""
    return _run(root, "config", "--get", key, check=False).strip()


def has_commit(root: Path, sha: str) -> bool:
    if not sha or sha == "none":
        return False
    return _exec(root, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def is_ancestor(root: Path, older: str, newer: str) -> bool:
    """True when `older` is `newer` or reachable from it."""
    if older == newer:
        return True
    return _exec(root, "merge-base", "--is-ancestor", older, newer).returncode == 0


def rev_list(root: Path, *args: str) -> list[str]:
    """Run rev-list and return full shas in the order git prints them."""
    output = _run(root, "rev-list", *args)
    return [line.strip() for line in output.splitlines() if line.strip()]


def ensure_repo(root: Path) -> None:
    if not is_repo(root):
        raise GitError(f"{root} is not a git repository; release and reconcile need git")


def head(root: Path) -> str:
    return _run(root, "rev-parse", "HEAD").strip()


def branch(root: Path) -> str:
    return _run(root, "branch", "--show-current").strip()


def default_branch(root: Path) -> str:
    """The branch to record a release on: current, else the remote's default.

    A scaffold run happens before any release, so guessing is allowed here but
    silent guessing is not: `flow.py init` prints what it detected, and the
    project can correct the profile.
    """
    try:
        current = branch(root)
    except GitError:
        current = ""
    if current:
        return current
    process = _exec(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if process.returncode == 0:
        remote = process.stdout.strip()
        if remote.startswith("origin/"):
            return remote[len("origin/"):]
    return "main"


def upstream_counts(root: Path) -> tuple[int, int] | None:
    """(ahead, behind) against the configured upstream; None when there is none.

    Read from the remote-tracking ref, so it never touches the network: a clone
    that has not fetched is told what its last fetch saw, not what is on the
    server now.
    """
    process = _exec(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
    if process.returncode != 0:
        return None
    parts = process.stdout.split()
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def dirty(root: Path) -> list[str]:
    """Porcelain lines with untracked files listed individually.

    `-uall` matters for the risk gate: `?? db/` would hide which file changed.
    """
    return [
        line
        for line in _run(root, "status", "--porcelain", "-uall").splitlines()
        if line.strip()
    ]


def _porcelain_path(line: str) -> str:
    """The path part of a porcelain line, with renames resolved to the new name."""
    entry = line[3:] if len(line) > 3 else ""
    if " -> " in entry:
        entry = entry.split(" -> ", 1)[1]
    entry = entry.strip()
    if len(entry) >= 2 and entry[0] == entry[-1] == '"':
        entry = entry[1:-1]
    return entry


def worktree_paths(root: Path) -> list[str]:
    """Paths changed in the working tree, tracked or not."""
    return [path for path in (_porcelain_path(line) for line in dirty(root)) if path]


def files_many(root: Path, shas: list[str]) -> list[str]:
    """Paths touched by a set of commits, in one `git show` call."""
    if not shas:
        return []
    output = _run(root, "show", "--pretty=format:", "--name-only", *shas)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _parse_log(output: str) -> list[Commit]:
    result: list[Commit] = []
    for chunk in output.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk.strip():
            continue
        parts = chunk.split("\x1f")
        if len(parts) < 2:
            continue
        result.append(
            Commit(
                sha=parts[0].strip(),
                subject=parts[1].strip(),
                body=parts[2].strip() if len(parts) > 2 else "",
            )
        )
    return result


def commits(root: Path, since: str | None = None, limit: int | None = None) -> list[Commit]:
    revision = f"{since}..HEAD" if since else "HEAD"
    args = ["log", f"--format=%H%x1f%s%x1f%b%x1e", revision]
    if limit:
        args[1:1] = ["-n", str(limit)]
    return _parse_log(_run(root, *args))


def commits_matching(root: Path, needle: str) -> list[Commit]:
    """Commits whose message mentions `needle`, across all of HEAD's history.

    Deliberately unbounded: an item that spans days can have its earliest
    commits slide out of any fixed window, and a scan that stopped early would
    turn "this change touches no risk path" into a lie. `--fixed-strings` keeps
    an id from being read as a pattern; `--grep=<needle>` as one argument keeps
    a needle starting with '-' from being parsed as an option.
    """
    if not needle:
        return []
    output = _run(
        root,
        "log",
        f"--format=%H%x1f%s%x1f%b%x1e",
        "--fixed-strings",
        f"--grep={needle}",
        "HEAD",
    )
    return _parse_log(output)


def total_commits(root: Path, since: str | None = None) -> int:
    revision = f"{since}..HEAD" if since else "HEAD"
    output = _run(root, "rev-list", "--count", revision).strip()
    return int(output or 0)


def files(root: Path, sha: str) -> list[str]:
    output = _run(root, "show", "--pretty=format:", "--name-only", sha)
    return [line.strip() for line in output.splitlines() if line.strip()]


def files_in_range(root: Path, since: str | None) -> list[str]:
    """Every path touched in `since..HEAD`, or in all of HEAD's history."""
    revision = f"{since}..HEAD" if since else "HEAD"
    output = _run(root, "log", "--format=", "--name-only", revision)
    return list(dict.fromkeys(line.strip() for line in output.splitlines() if line.strip()))


def activity_dates(root: Path, base: str) -> dict[str, str]:
    """Latest commit date per directory two levels below `base`.

    `<work_dir>` holds `<YYYY-MM>/<item>/`; one walk answers "when did anyone
    last touch this item" without a git call per item. The date is a label for
    a report, not a watermark: ordering still comes from the commit graph.
    """
    try:
        output = _run(root, "log", "--date=short", "--format=@@%ad", "--name-only", "--", base)
    except GitError:
        return {}
    base_parts = tuple(part for part in Path(base).parts if part not in ("", "."))
    result: dict[str, str] = {}
    current: str | None = None
    for line in output.splitlines():
        if line.startswith("@@"):
            current = line[2:].strip()
            continue
        path = line.strip().replace("\\", "/")
        if not current or not path.endswith(".md"):
            continue
        parts = tuple(path.split("/"))
        if len(parts) < len(base_parts) + 2 or parts[: len(base_parts)] != base_parts:
            continue
        key = "/".join(parts[: len(base_parts) + 2])
        result.setdefault(key, current)
    return result
