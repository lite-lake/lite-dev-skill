"""Reconcile: make release debt visible without blocking anything."""
from __future__ import annotations

from dataclasses import dataclass, field

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
    dirty: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        """Debt that must be written into the release notes before recording."""
        return bool(self.no_item or self.missing_item)

    @property
    def empty(self) -> bool:
        return not (self.no_item or self.missing_item or self.risky_no_item or self.dirty)


def collect(profile: Profile, channel: str, since: str | None = None) -> Debt:
    git.ensure_repo(profile.root)
    known = {item.id for item in artifacts.all_items(profile)}
    debt = Debt(
        channel=channel,
        since=since,
        head=git.head(profile.root),
        total=git.total_commits(profile.root, since),
    )
    for commit in git.commits(profile.root, since):
        text = f"{commit.subject}\n{commit.body}"
        ids = list(dict.fromkeys(profile.id_pattern.findall(text)))
        if not ids:
            debt.no_item.append(commit)
            if profile.risk_paths:
                touched = [
                    path
                    for path in git.files(profile.root, commit.sha)
                    if any(path.startswith(risk) for risk in profile.risk_paths)
                ]
                if touched:
                    debt.risky_no_item.append((commit, ", ".join(touched)))
            continue
        missing = [item_id for item_id in ids if item_id not in known]
        if missing:
            debt.missing_item.append((commit, missing[0]))
    debt.dirty = git.dirty(profile.root)
    return debt


def render(debt: Debt, root=None, verbose: bool = False) -> str:
    lines = [
        f"channel: {debt.channel}",
        f"range: {(debt.since[:7] + '..HEAD') if debt.since else 'HEAD'} ({debt.total} commit(s))",
        f"clean: {'yes' if not debt.dirty else 'no'}",
        f"no work item ({len(debt.no_item)}):",
    ]
    for commit in debt.no_item:
        lines.append(f"  - {commit.short} {commit.subject}")
        if verbose and root is not None:
            for path in git.files(root, commit.sha):
                lines.append(f"      {path}")
    lines.append(f"missing work item ({len(debt.missing_item)}):")
    for commit, item_id in debt.missing_item:
        lines.append(f"  - {commit.short} {item_id} {commit.subject}")
    lines.append(f"risky path without item ({len(debt.risky_no_item)}):")
    for commit, paths in debt.risky_no_item:
        lines.append(f"  - {commit.short} {paths} {commit.subject}")
    lines.append(f"uncommitted ({len(debt.dirty)}):")
    for entry in debt.dirty:
        lines.append(f"  - {entry}")
    return "\n".join(lines)


def as_dict(debt: Debt) -> dict:
    return {
        "channel": debt.channel,
        "since": debt.since,
        "head": debt.head,
        "total": debt.total,
        "no_item": [{"sha": commit.sha, "subject": commit.subject} for commit in debt.no_item],
        "missing_item": [
            {"sha": commit.sha, "subject": commit.subject, "item": item_id}
            for commit, item_id in debt.missing_item
        ],
        "risky_no_item": [
            {"sha": commit.sha, "subject": commit.subject, "paths": paths}
            for commit, paths in debt.risky_no_item
        ],
        "dirty": debt.dirty,
        "blocking": debt.blocking,
    }
