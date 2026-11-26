"""Document hygiene: reachability, one index per directory, and no drifting facts.

Every rule here is a mechanism, not a policy: which documents exist is the
profile's `[docs] required`, which directories are indexed is the tree itself.
A document that no index links is unreachable; an entry document that pins a
version is a copy of a fact whose authority lives somewhere else.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import artifacts
from .profile import Profile

FENCE_PREFIXES = ("```", "~~~")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
ENTRY_NAMES = {"readme.md", "agents.md"}

VERSION_PIN_RE = re.compile(
    r"\b(?:go|golang|node|nodejs|python|java|rust|php|ruby|mysql|mariadb|postgres|"
    r"postgresql|redis|mongo|mongodb|vue|react|angular|svelte|typescript|django|"
    r"rails|laravel|flutter|kotlin|swift)\s*v?\d+(?:\.\d+)+",
    re.I,
)
PORT_RE = re.compile(r"\b(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]):\d{2,5}\b")
DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")

SKIP_TARGET_PREFIXES = ("http://", "https://", "mailto:", "#")


def _is_hidden(relative: Path) -> bool:
    return any(part.startswith(".") for part in relative.parts)


def markdown_files(profile: Profile) -> list[Path]:
    """Required documents plus every markdown file under the docs directory."""
    found: set[Path] = set()
    for relative in profile.required_docs:
        path = profile.root / relative
        if path.is_file() and path.suffix.lower() in (".md", ".markdown"):
            found.add(path)
    docs = profile.docs_path
    if docs.is_dir():
        for path in docs.rglob("*.md"):
            if path.is_file() and not _is_hidden(path.relative_to(profile.root)):
                found.add(path)
    return sorted(found)


def _strip_code(text: str) -> str:
    """Drop fenced blocks and inline code so examples are not parsed as links."""
    lines: list[str] = []
    fenced = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if any(stripped.startswith(prefix) for prefix in FENCE_PREFIXES):
            fenced = not fenced
            continue
        if fenced:
            continue
        lines.append(INLINE_CODE_RE.sub("", line))
    return "\n".join(lines)


def _targets(text: str) -> list[str]:
    targets: list[str] = []
    for match in artifacts.LINK_RE.finditer(text):
        target = match.group(1).strip()
        if not target or target.startswith(SKIP_TARGET_PREFIXES):
            continue
        target = target.split("#", 1)[0].strip()
        if not target or "://" in target:
            continue
        # Template tokens and `${...}` are prose about a path, not a path.
        if any(token in target for token in ("{", "}", "<", ">", "$", "|")):
            continue
        targets.append(target)
    return targets


def _resolves(base: Path, target: str) -> bool:
    candidate = (base / target).resolve()
    if candidate.exists():
        return True
    if not Path(target).suffix:
        for suffix in (".md", "/README.md", "/index.md"):
            if (base / f"{target}{suffix}").exists():
                return True
    return False


def link_errors(profile: Profile) -> list[str]:
    errors: list[str] = []
    for path in markdown_files(profile):
        text = _strip_code(artifacts.read_text(path))
        seen: set[str] = set()
        for target in _targets(text):
            if target in seen:
                continue
            seen.add(target)
            if not _resolves(path.parent, target):
                errors.append(
                    f"{path.relative_to(profile.root)}: link target does not exist: {target}"
                )
    return errors


def _index_dirs(profile: Profile) -> list[Path]:
    dirs: list[Path] = []
    docs = profile.docs_path
    if docs.is_dir():
        for readme in sorted(docs.rglob("README.md")):
            relative = readme.relative_to(profile.root)
            if readme.is_file() and not _is_hidden(relative):
                dirs.append(readme.parent)
    if profile.docs_decisions:
        decisions = profile.root / profile.docs_decisions
        if decisions.is_dir() and decisions not in dirs:
            dirs.append(decisions)
    return dirs


def index_warnings(profile: Profile) -> list[str]:
    """Every markdown file in a directory is linked from that directory's README.

    A file nobody links is a file nobody reads; the warning names both sides.
    """
    warnings: list[str] = []
    for directory in _index_dirs(profile):
        readme = directory / "README.md"
        if not readme.is_file():
            continue
        text = _strip_code(artifacts.read_text(readme))
        linked = {Path(target).name for target in _targets(text)}
        for path in sorted(directory.glob("*.md")):
            if path.name == "README.md":
                continue
            if path.name not in linked:
                warnings.append(
                    f"{path.relative_to(profile.root)}: not linked from "
                    f"{readme.relative_to(profile.root)}"
                )
    return warnings


ARTIFACT_NAMES = ("design.md", "implementation.md", "test-report.md")


def artifact_warnings(profile: Profile) -> list[str]:
    """Files that exist inside an item must be mentioned by its item.md."""
    warnings: list[str] = []
    for item in artifacts.all_items(profile):
        text = artifacts.read_text(item.path)
        for name in ARTIFACT_NAMES:
            if (item.directory / name).is_file() and name not in text:
                warnings.append(
                    f"{item.directory.name}/{name}: exists but item.md never mentions it; "
                    "link it so the next session finds it"
                )
    return warnings


def heading_errors(profile: Profile) -> list[str]:
    """Append-only records must not repeat a heading: two entries would collide."""
    errors: list[str] = []
    release = profile.release_path
    if not release.is_dir():
        return errors
    for path in sorted(release.rglob("*.md")):
        headings: dict[str, int] = {}
        for line in artifacts.read_text(path).splitlines():
            match = re.match(r"^##\s+(.+?)\s*$", line)
            if not match:
                continue
            heading = match.group(1)
            headings[heading] = headings.get(heading, 0) + 1
        duplicates = sorted(name for name, count in headings.items() if count > 1)
        for name in duplicates:
            errors.append(
                f"{path.relative_to(profile.root)}: duplicate '## {name}'; "
                "append a distinct heading or fold the entry into the existing one"
            )
    return errors


def _entry_docs(profile: Profile) -> list[Path]:
    entries: list[Path] = []
    for relative in profile.required_docs:
        path = profile.root / relative
        if path.is_file() and path.name.lower() in ENTRY_NAMES:
            entries.append(path)
    return entries


def zero_fact_warnings(profile: Profile) -> list[str]:
    """Entry documents may not pin versions, ports, or dates.

    Each of those is a fact with a single authority elsewhere; a copy in a
    README is a copy that will drift.
    """
    warnings: list[str] = []
    checks = (
        (VERSION_PIN_RE, "pins a version"),
        (PORT_RE, "hardcodes a port"),
        (DATE_RE, "hardcodes a date"),
    )
    for path in _entry_docs(profile):
        for number, line in enumerate(artifacts.read_text(path).splitlines(), 1):
            for pattern, label in checks:
                match = pattern.search(line)
                if match:
                    warnings.append(
                        f"{path.relative_to(profile.root)}:{number}: {label} "
                        f"({match.group(0)}); link to its single source instead"
                    )
    return warnings


def archive_link_warnings(profile: Profile) -> list[str]:
    """Live documents link the archive index, never an archived item directly."""
    warnings: list[str] = []
    for path in markdown_files(profile):
        if artifacts.ARCHIVE_DIR in path.parts:
            continue
        for target in _targets(_strip_code(artifacts.read_text(path))):
            resolved = (path.parent / target).resolve()
            if artifacts.ARCHIVE_DIR in resolved.parts:
                warnings.append(
                    f"{path.relative_to(profile.root)}: links into {artifacts.ARCHIVE_DIR}/ "
                    f"({target}); link the archive index instead"
                )
    return warnings


def decisions_errors(profile: Profile) -> list[str]:
    if not profile.docs_decisions:
        return []
    directory = profile.root / profile.docs_decisions
    errors: list[str] = []
    if not directory.is_dir():
        errors.append(f"docs.decisions points at a missing directory: {profile.docs_decisions}")
    elif not (directory / "README.md").is_file():
        errors.append(
            f"{profile.docs_decisions}/README.md is missing; it is the index of decisions"
        )
    return errors


def problems(profile: Profile) -> tuple[list[str], list[str]]:
    """All document checks, each behind its profile toggle."""
    errors: list[str] = []
    warnings: list[str] = []
    if profile.docs_check_links:
        errors.extend(link_errors(profile))
    errors.extend(heading_errors(profile))
    errors.extend(decisions_errors(profile))
    warnings.extend(index_warnings(profile))
    warnings.extend(artifact_warnings(profile))
    warnings.extend(archive_link_warnings(profile))
    if profile.docs_zero_fact:
        warnings.extend(zero_fact_warnings(profile))
    return errors, warnings
