"""A per-clone record of gate runs, used only to warn about stale evidence.

The ledger lives inside the git directory, never in the working tree: a gate run
must not make the tree dirty and must not become a file somebody has to commit.
It is a local signal, not a shared fact — a teammate's clone has its own.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from . import git
from .profile import Profile

FILE_PREFIX = "gate-log"


def path_for(profile: Profile) -> Path | None:
    """One ledger per profile, so two projects in one repository do not mix."""
    try:
        directory = git.git_dir(profile.root)
    except git.GitError:
        return None
    if directory is None:
        return None
    digest = hashlib.sha1(str(profile.path).encode("utf-8")).hexdigest()[:8]
    return directory / "lite-dev" / f"{FILE_PREFIX}-{digest}.jsonl"


def record(profile: Profile, level: str, ok: bool, item: str = "") -> None:
    path = path_for(profile)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "date": date.today().isoformat(),
            "level": level,
            "ok": bool(ok),
            "item": item,
        }
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        # The ledger is advisory; a read-only checkout must not fail the gate.
        return


def entries(profile: Profile) -> list[dict]:
    path = path_for(profile)
    if path is None or not path.is_file():
        return []
    found: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                found.append(entry)
    except OSError:
        return []
    return found


def last_pass(profile: Profile, level: str) -> dict | None:
    latest = None
    for entry in entries(profile):
        if entry.get("level") != level or not entry.get("ok"):
            continue
        if latest is None or str(entry.get("date", "")) >= str(latest.get("date", "")):
            latest = entry
    return latest


def last_pass_for(profile: Profile, level: str, item: str) -> dict | None:
    """The item's own PASS, not a project-wide run it happened to share.

    `done` uses this: closing an item is a claim that its gate passed, and a
    project-wide run does not name the item. The ledger is per clone, so a
    teammate must run the gate on their clone before closing.
    """
    latest = None
    for entry in entries(profile):
        if entry.get("level") != level or not entry.get("ok"):
            continue
        if str(entry.get("item", "")) != item:
            continue
        if latest is None or str(entry.get("date", "")) >= str(latest.get("date", "")):
            latest = entry
    return latest


def _age(day: str) -> int | None:
    try:
        return (date.today() - date.fromisoformat(day)).days
    except (TypeError, ValueError):
        return None


def stale_line(profile: Profile, level: str) -> str | None:
    """One advisory line when the full level's last PASS is old or missing."""
    record_found = last_pass(profile, level)
    if record_found is None:
        return (
            f"{level} has no PASS recorded in this clone; "
            f"`gate --level {level}` is the only evidence for it"
        )
    age = _age(str(record_found.get("date", "")))
    if age is None or age <= profile.gate_fresh_days:
        return None
    return (
        f"{level} last passed {age} days ago (profile allows {profile.gate_fresh_days}); "
        f"a cheaper level does not replace it — run `gate --level {level}`"
    )
