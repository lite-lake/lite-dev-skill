"""Release records: scan the watermark, render the record, write it."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import artifacts
from .profile import Profile

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "release.md"


@dataclass
class ReleaseRecord:
    path: Path
    channel: str
    date: str
    source: str
    previous: str


def records(profile: Profile) -> list[ReleaseRecord]:
    directory = profile.release_path
    if not directory.is_dir():
        return []
    found: list[ReleaseRecord] = []
    for path in sorted(directory.glob("*.md")):
        meta, _ = artifacts.parse_frontmatter(artifacts.read_text(path))
        channel = (meta.get("channel") or "").strip()
        source = (meta.get("source") or "").strip()
        if not channel or not source:
            continue
        found.append(
            ReleaseRecord(
                path=path,
                channel=channel,
                date=(meta.get("date") or "").strip(),
                source=source,
                previous=(meta.get("previous") or "").strip(),
            )
        )
    return found


def latest(profile: Profile, channel: str) -> ReleaseRecord | None:
    candidates = [record for record in records(profile) if record.channel == channel]
    if not candidates:
        return None
    return max(candidates, key=lambda record: (record.date, record.path.name))


def next_path(profile: Profile, channel: str, day: str) -> Path:
    directory = profile.release_path
    base = f"{channel}-{day}"
    candidate = directory / f"{base}.md"
    index = 2
    while candidate.exists():
        candidate = directory / f"{base}-{index}.md"
        index += 1
    return candidate


def render(
    channel: str,
    day: str,
    source: str,
    previous: str,
    gate: str,
    commits: str,
    items: str,
    rollback: str,
    notes: str,
) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    for token, value in {
        "<CHANNEL>": channel,
        "<DATE>": day,
        "<SHA>": source,
        "<PREVIOUS>": previous,
        "<GATE>": gate,
        "<COMMITS>": commits,
        "<ITEMS>": items,
        "<ROLLBACK>": rollback,
        "<NOTES>": notes,
    }.items():
        text = text.replace(token, value)
    return text
