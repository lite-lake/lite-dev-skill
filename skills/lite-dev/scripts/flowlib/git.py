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


def dirty(root: Path) -> list[str]:
    return [line for line in _run(root, "status", "--porcelain").splitlines() if line.strip()]


def commits(root: Path, since: str | None = None, limit: int | None = None) -> list[Commit]:
    revision = f"{since}..HEAD" if since else "HEAD"
    args = ["log", f"--format=%H%x1f%s%x1f%b%x1e", revision]
    if limit:
        args[1:1] = ["-n", str(limit)]
    output = _run(root, *args)
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


def total_commits(root: Path, since: str | None = None) -> int:
    revision = f"{since}..HEAD" if since else "HEAD"
    output = _run(root, "rev-list", "--count", revision).strip()
    return int(output or 0)


def files(root: Path, sha: str) -> list[str]:
    output = _run(root, "show", "--pretty=format:", "--name-only", sha)
    return [line.strip() for line in output.splitlines() if line.strip()]
