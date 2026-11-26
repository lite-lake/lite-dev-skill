"""Release records: parse, validate the ancestry chain, render, write.

Records are the only shared release state. Their order comes from the commit
graph, never from a filename or a local clock, so two machines cannot disagree
about which release is the latest one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import artifacts, git
from .errors import FlowError
from .profile import Profile

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "release.md"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass
class ReleaseRecord:
    path: Path
    channel: str
    date: str
    source: str
    previous: str
    by: str
    tool: str

    @property
    def short(self) -> str:
        return self.source[:7]


def load_records(profile: Profile) -> list[ReleaseRecord]:
    """Read every record. A configured channel's record must be complete."""
    directory = profile.release_path
    if not directory.is_dir():
        return []
    found: list[ReleaseRecord] = []
    for path in sorted(directory.glob("*.md")):
        meta, _ = artifacts.parse_frontmatter(artifacts.read_text(path))
        channel = (meta.get("channel") or "").strip()
        if not channel:
            continue
        source = (meta.get("source") or "").strip()
        previous = (meta.get("previous") or "").strip() or "none"
        if channel in profile.release_channels:
            if not source:
                raise FlowError(
                    f"{path.name}: release record has no 'source'; "
                    "do not edit a recorded release, write a new record instead"
                )
            if not SHA_RE.match(source):
                raise FlowError(
                    f"{path.name}: source {source!r} is not a full commit sha; "
                    "write a new record instead of editing this one"
                )
            if previous != "none" and not SHA_RE.match(previous):
                raise FlowError(
                    f"{path.name}: previous {previous!r} is not a full commit sha"
                )
        if not source:
            continue
        found.append(
            ReleaseRecord(
                path=path,
                channel=channel,
                date=(meta.get("date") or "").strip(),
                source=source,
                previous=previous,
                by=(meta.get("by") or "").strip(),
                tool=(meta.get("tool") or "").strip(),
            )
        )
    return found


def _ordered(profile: Profile, records: list[ReleaseRecord]) -> list[ReleaseRecord]:
    """Sort by one topological walk, so ancestry is O(1) per adjacent pair."""
    sources = sorted({record.source for record in records})
    rank = {
        sha: index
        for index, sha in enumerate(
            git.rev_list(profile.root, "--topo-order", "--reverse", *sources)
        )
    }
    return sorted(
        records,
        key=lambda record: (
            rank.get(record.source, len(rank)),
            record.date,
            record.path.name,
        ),
    )


def chain(profile: Profile, channel: str) -> list[ReleaseRecord]:
    """Order a channel's records by commit ancestry and validate the links.

    Raises FlowError when the clone is missing a commit, when two records
    diverged, or when `previous` does not match the record before it. A release
    must not proceed on a channel whose history is ambiguous.
    """
    git.ensure_repo(profile.root)
    records = [record for record in load_records(profile) if record.channel == channel]
    if not records:
        return []

    for record in records:
        if not git.has_commit(profile.root, record.source):
            raise FlowError(
                f"{record.path.name} references {record.short}, which is not in this clone; "
                "fetch the channel history before releasing"
            )
        if record.previous != "none" and not git.has_commit(profile.root, record.previous):
            raise FlowError(
                f"{record.path.name}: previous {record.previous[:7]} is not in this clone; "
                "fetch before releasing"
            )

    ordered = _ordered(profile, records)
    for index, record in enumerate(ordered):
        if index == 0:
            if record.previous != "none":
                raise FlowError(
                    f"{record.path.name}: previous {record.previous[:7]} does not follow "
                    "nothing; release records form one chain. Write a new record "
                    "instead of editing an old one."
                )
            continue
        before = ordered[index - 1]
        if not git.is_ancestor(profile.root, before.source, record.source):
            raise FlowError(
                f"channel {channel!r} has divergent release records: "
                f"{before.path.name} ({before.short}) and "
                f"{record.path.name} ({record.short}) are not on one history. "
                "A rewrite or a release from a branch happened; record again from "
                "the true mainline tip."
            )
        if record.previous != before.source:
            raise FlowError(
                f"{record.path.name}: previous {record.previous[:7]} does not follow "
                f"{before.path.name}; release records form one chain. Write a new "
                "record instead of editing an old one."
            )
    return ordered


def tip(profile: Profile, channel: str) -> ReleaseRecord | None:
    ordered = chain(profile, channel)
    return ordered[-1] if ordered else None


def next_path(profile: Profile, channel: str, day: str, source: str) -> Path:
    base = f"{channel}-{day}-{source[:6]}"
    candidate = profile.release_path / f"{base}.md"
    index = 2
    while candidate.exists():
        candidate = profile.release_path / f"{base}-{index}.md"
        index += 1
    return candidate


def render(
    channel: str,
    day: str,
    source: str,
    previous: str,
    by: str,
    tool: str,
    gate: str,
    commits: str,
    items: str,
    artifacts_text: str,
    rollback: str,
    notes: str,
) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    for token, value in {
        "<CHANNEL>": channel,
        "<DATE>": day,
        "<SHA>": source,
        "<PREVIOUS>": previous,
        "<BY>": by,
        "<TOOL>": tool,
        "<GATE>": gate,
        "<COMMITS>": commits,
        "<ITEMS>": items,
        "<ARTIFACTS>": artifacts_text,
        "<ROLLBACK>": rollback,
        "<NOTES>": notes,
    }.items():
        text = text.replace(token, value)
    return text
