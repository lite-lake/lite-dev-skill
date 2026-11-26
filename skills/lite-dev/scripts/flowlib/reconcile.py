"""Reconcile: make release debt visible without blocking anything."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import artifacts, git
from .profile import Profile


@dataclass
class Debt:
    channel: str
    since: str | None
    head: str
    total: int
    no_item: list[git.Commit] = field(default_factory=list)
    missing_item: list[tuple[git.Commit, str]] = field(default_factory=list)
    risky_no_item: list[tuple[git.Commit, str]] = field(default_factory=list)
    risky_with_item: list[tuple[git.Commit, str, list[str]]] = field(default_factory=list)
    bookkeeping: list[git.Commit] = field(default_factory=list)
    dirty: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        """Debt that must be written into the release notes before recording."""
        return bool(self.no_item or self.missing_item)

    @property
    def empty(self) -> bool:
        return not (
            self.no_item
            or self.missing_item
            or self.risky_no_item
            or self.risky_with_item
            or self.dirty
        )


def _under(path: str, prefix: str) -> bool:
    prefix = prefix.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def _bookkeeping(profile: Profile, paths: list[str]) -> bool:
    """True when a commit only touches the flow's own record stores.

    Every release writes a record and tells the operator to commit it; every
    archive move is a commit too; and adopting the flow changes the profile.
    Those commits cannot carry a work item, so treating them as debt guarantees
    a permanent false positive and teaches people to type filler notes. They
    stay visible in `bookkeeping`. Risk paths are reported before this check, so
    a profile change that touches one is still named.
    """
    if not paths:
        return False
    try:
        profile_path = profile.path.relative_to(profile.root).as_posix()
    except ValueError:
        profile_path = ""
    stores = (
        profile.release_path.relative_to(profile.root).as_posix(),
        profile.work_path.relative_to(profile.root).as_posix(),
    )
    return all(
        any(_under(path, store) for store in stores)
        or (profile_path and path == profile_path)
        for path in paths
    )


def _risky(profile: Profile, paths: list[str]) -> list[str]:
    if not profile.risk_paths:
        return []
    found = {
        path
        for path in paths
        if any(_under(path, risk) for risk in profile.risk_paths)
    }
    return sorted(found)


def collect(profile: Profile, channel: str, since: str | None = None) -> Debt:
    git.ensure_repo(profile.root)
    known = {
        item.id
        for item in artifacts.all_items(profile) + artifacts.archived_items(profile)
        if item.id
    }
    debt = Debt(
        channel=channel,
        since=since,
        head=git.head(profile.root),
        total=git.total_commits(profile.root, since),
    )
    for commit in git.commits(profile.root, since):
        text = f"{commit.subject}\n{commit.body}"
        ids = list(dict.fromkeys(profile.id_pattern.findall(text)))
        paths = git.files(profile.root, commit.sha)
        risky = _risky(profile, paths)
        valid = [item_id for item_id in ids if item_id in known]
        if risky:
            if valid:
                debt.risky_with_item.append((commit, ", ".join(risky), valid))
            else:
                debt.risky_no_item.append((commit, ", ".join(risky)))
        if _bookkeeping(profile, paths):
            debt.bookkeeping.append(commit)
            continue
        if not ids:
            debt.no_item.append(commit)
            continue
        missing = [item_id for item_id in ids if item_id not in known]
        if missing:
            debt.missing_item.append((commit, missing[0]))
    debt.dirty = git.dirty(profile.root)
    return debt


def _files(root: Path | None, sha: str, verbose: bool) -> list[str]:
    if not verbose or root is None:
        return []
    try:
        return git.files(root, sha)
    except git.GitError:
        return []


def render(debt: Debt, root: Path | None = None, verbose: bool = False) -> str:
    lines = [
        f"channel: {debt.channel}",
        f"range: {(debt.since[:7] + '..HEAD') if debt.since else 'HEAD'} ({debt.total} commit(s))",
        f"clean: {'yes' if not debt.dirty else 'no'}",
        f"no work item ({len(debt.no_item)}):",
    ]
    for commit in debt.no_item:
        lines.append(f"  - {commit.short} {commit.subject}")
        for path in _files(root, commit.sha, verbose):
            lines.append(f"      {path}")
    lines.append(f"missing work item ({len(debt.missing_item)}):")
    for commit, item_id in debt.missing_item:
        lines.append(f"  - {commit.short} {item_id} {commit.subject}")
    lines.append(f"risky path without item ({len(debt.risky_no_item)}):")
    for commit, paths in debt.risky_no_item:
        lines.append(f"  - {commit.short} {paths} {commit.subject}")
    lines.append(f"risky path with item ({len(debt.risky_with_item)}):")
    for commit, paths, item_ids in debt.risky_with_item:
        lines.append(
            f"  - {commit.short} {paths} {', '.join(item_ids)} {commit.subject}"
        )
    if debt.bookkeeping:
        lines.append(f"bookkeeping ignored ({len(debt.bookkeeping)}):")
        for commit in debt.bookkeeping:
            lines.append(f"  - {commit.short} {commit.subject}")
    lines.append(f"uncommitted ({len(debt.dirty)}):")
    for entry in debt.dirty:
        lines.append(f"  - {entry}")
    return "\n".join(lines)


def as_dict(
    debt: Debt, root: Path | None = None, verbose: bool = False
) -> dict:
    def commit_entry(commit: git.Commit) -> dict:
        entry = {"sha": commit.sha, "subject": commit.subject}
        if verbose:
            entry["files"] = _files(root, commit.sha, verbose)
        return entry

    return {
        "channel": debt.channel,
        "since": debt.since,
        "head": debt.head,
        "total": debt.total,
        "no_item": [commit_entry(commit) for commit in debt.no_item],
        "missing_item": [
            {
                **commit_entry(commit),
                "item": item_id,
            }
            for commit, item_id in debt.missing_item
        ],
        "risky_no_item": [
            {**commit_entry(commit), "paths": paths}
            for commit, paths in debt.risky_no_item
        ],
        "risky_with_item": [
            {**commit_entry(commit), "paths": paths, "items": item_ids}
            for commit, paths, item_ids in debt.risky_with_item
        ],
        "bookkeeping": [commit_entry(commit) for commit in debt.bookkeeping],
        "dirty": debt.dirty,
        "blocking": debt.blocking,
    }
