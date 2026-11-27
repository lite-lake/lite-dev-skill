"""Read the skill's own changelog for the version-drift review.

A Y (minor) change may be incompatible, so the agent has to see what changed.
The changelog ships next to the skill, which is why a copied install and an
offline machine can show the same text; the repository's release check keeps
that copy byte-identical to the root file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import FlowError
from .profile import SKILL_ROOT, parse_version

# When the skill is a clone (not a copy), the root changelog is two levels up.
REPO_ROOT = SKILL_ROOT.parent.parent
URL = "https://github.com/lite-lake/lite-dev-skill/blob/main"

_VERSION = re.compile(r"^##\s+(\d+\.\d+\.\d+)\b")
_HEADING = re.compile(r"^##\s+")
_BREAKING = re.compile(r"(?mi)^###\s+(Breaking|破坏性变更)\b")


@dataclass
class Section:
    version: str
    body: str


def skill_path(language: str = "en") -> Path:
    """The bundled changelog, falling back to the repository root in a clone."""
    name = (
        "CHANGELOG.zh.md"
        if (language or "en").lower().startswith("zh")
        else "CHANGELOG.md"
    )
    bundled = SKILL_ROOT / name
    return bundled if bundled.is_file() else REPO_ROOT / name


def sections(path: Path) -> list[Section]:
    """Release sections in file order; `Unreleased` and non-version H2s are skipped."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise FlowError(f"cannot read {path}: {exc}") from exc

    result: list[Section] = []
    version = ""
    body: list[str] = []

    def flush() -> None:
        if version:
            result.append(Section(version, "\n".join(body).strip()))

    for line in text.splitlines():
        match = _VERSION.match(line)
        if match:
            flush()
            version = match.group(1)
            body = []
            continue
        if _HEADING.match(line):
            flush()
            version = ""
            body = []
            continue
        if version:
            body.append(line)
    flush()
    return result


def between(path: Path, low: str, high: str) -> list[Section]:
    """Sections newer than `low` and at most `high`, oldest first.

    An empty `low` means no recorded baseline: show only `high`, not the whole
    history the skill ever shipped.
    """
    top = parse_version(high)
    floor = parse_version(low) if low else None
    picked = [
        section
        for section in sections(path)
        if parse_version(section.version) <= top
        and (
            parse_version(section.version) > floor
            if floor is not None
            else parse_version(section.version) == top
        )
    ]
    return sorted(picked, key=lambda section: parse_version(section.version))


def render(items: list[Section], *, mark_breaking: bool = False) -> list[str]:
    """Render sections for the terminal, marking breaking ones when asked."""
    lines: list[str] = []
    for item in items:
        marker = " [breaking]" if mark_breaking and _BREAKING.search(item.body) else ""
        lines.append(f"## {item.version}{marker}")
        if item.body:
            lines.extend(item.body.splitlines())
        lines.append("")
    return lines
