"""Move finished items out of the working set without deleting history.

The rule mirrors the source tree: an archived item keeps its month bucket under
`_archive/`, the index records where it went and why, and active documents are
not allowed to link into the archive. Nothing is deleted; `unarchive` reverses
the move and the index row.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import artifacts, fsio
from .checks import today
from .errors import FlowError
from .profile import Profile

INDEX_HEADER = """# Archive

Finished work items live here, filed under their created month. Archived items
are still resolvable by id, but they are not part of the working set.

Active documents must not link into this directory; link the archive index
instead.

| Item | Title | Archived | Reason |
|---|---|---|---|
"""


def index_path(profile: Profile) -> Path:
    return profile.work_path / artifacts.ARCHIVE_DIR / "README.md"


def target_for(profile: Profile, item: artifacts.Item) -> Path:
    month = artifacts.month_of(item.meta.get("created", ""))
    if not artifacts.MONTH_RE.match(month):
        raise FlowError(
            f"{item.id} has no created date; set 'created: YYYY-MM-DD' before archiving"
        )
    return profile.work_path / artifacts.ARCHIVE_DIR / month / item.directory.name


def _row(profile: Profile, item: artifacts.Item, reason: str) -> str:
    relative = target_for(profile, item).relative_to(index_path(profile).parent)
    title = item.meta.get("title", "").replace("|", "\\|")
    reason = (reason or "-").replace("|", "\\|")
    return f"| [{item.id}]({relative.as_posix()}) | {title} | {today()} | {reason} |"


def _read_index(profile: Profile) -> str:
    path = index_path(profile)
    if path.is_file():
        return artifacts.read_text(path)
    return INDEX_HEADER


def _write_index(profile: Profile, text: str) -> None:
    fsio.atomic_write_text(index_path(profile), text.rstrip("\n") + "\n")


def _with_row(profile: Profile, item: artifacts.Item, reason: str) -> str:
    text = _read_index(profile)
    if not text.strip():
        text = INDEX_HEADER
    lines = [line for line in text.rstrip("\n").splitlines()]
    if not any(line.startswith("|") and "](" in line and item.id in line for line in lines):
        lines.append(_row(profile, item, reason))
    return "\n".join(lines)


def _without_row(profile: Profile, item: artifacts.Item) -> str:
    lines = _read_index(profile).rstrip("\n").splitlines()
    kept = [
        line
        for line in lines
        if not (line.startswith("|") and "](" in line and item.id in line)
    ]
    return "\n".join(kept)


def is_archived(item: artifacts.Item) -> bool:
    return artifacts.ARCHIVE_DIR in item.directory.parts


def archive(profile: Profile, item_id: str, reason: str = "", force: bool = False) -> Path:
    item = artifacts.find_item(profile, item_id)
    if is_archived(item):
        raise FlowError(f"{item.id} is already archived ({item.directory})")
    closed = (item.meta.get("closed") or "").strip()
    if not closed and not force:
        raise FlowError(
            f"{item.id} is not closed ({item.status}); close it with flow.py done <ID>, "
            "or pass --force to archive it unfinished"
        )
    target = target_for(profile, item)
    if target.exists():
        raise FlowError(f"{target} already exists; resolve the duplicate before archiving")
    text = _with_row(profile, item, reason or (f"closed {closed}" if closed else "archived"))
    with fsio.project_lock(profile.root):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(item.directory), str(target))
        _write_index(profile, text)
    return target


def restore(profile: Profile, item_id: str) -> Path:
    item = artifacts.find_item(profile, item_id)
    if not is_archived(item):
        raise FlowError(f"{item.id} is not archived ({item.directory})")
    month = item.directory.parent.name
    target = profile.work_path / month / item.directory.name
    if target.exists():
        raise FlowError(f"{target} already exists; remove it before restoring")
    text = _without_row(profile, item)
    with fsio.project_lock(profile.root):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(item.directory), str(target))
        _write_index(profile, text)
    return target
