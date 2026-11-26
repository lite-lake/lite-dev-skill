"""Document hygiene: reachability, one index per directory, and no drifting facts.

Every rule here is a mechanism, not a policy: which documents exist is the
profile's `[docs] required`, which directories are indexed is the tree itself.
A document that no index links is unreachable; an entry document that pins a
version is a copy of a fact whose authority lives somewhere else.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import artifacts
from .profile import Exemption, Profile

FENCE_PREFIXES = ("```", "~~~")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
ENTRY_NAMES = {"readme.md", "agents.md"}
INDEX_NAMES = ("README.md", "index.md")
DECISION_STATUSES = ("proposed", "accepted", "rejected", "superseded", "deprecated")

VERSION_PIN_RE = re.compile(
    r"\b(?:go|golang|node|nodejs|python|java|rust|php|ruby|mysql|mariadb|postgres|"
    r"postgresql|redis|mongo|mongodb|vue|react|angular|svelte|typescript|django|"
    r"rails|laravel|flutter|kotlin|swift)\s*v?\d+(?:\.\d+)+",
    re.I,
)
PORT_RE = re.compile(r"\b(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]):\d{2,5}\b")
DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
COUNT_RE = re.compile(
    r"\b\d+\s+(?:apps?|applications?|services?|modules?|packages?|tables?|endpoints?)\b"
    r"|\d+\s*(?:个应用|个服务|个模块|个包|张表|个接口|种语言|处路由|个扩展|个仓库|个技能)",
    re.I,
)

SKIP_TARGET_PREFIXES = ("http://", "https://", "mailto:", "#")


def _is_hidden(relative: Path) -> bool:
    return any(part.startswith(".") for part in relative.parts)


def _under(relative: str, prefix: str) -> bool:
    prefix = prefix.rstrip("/")
    return relative == prefix or relative.startswith(prefix + "/")


class _Exemptions:
    """Which silences apply right now, and whether each one still earns its keep.

    An expired exemption is reported and ignored; an exemption that suppressed
    nothing is reported as unused. Both are how a bounded silence stays bounded.
    """

    def __init__(self, profile: Profile) -> None:
        self.profile = profile
        self.entries: list[Exemption] = list(profile.exemptions)
        self.today = date.today().isoformat()
        self.used: set[int] = set()

    def allows(self, check: str, path: Path | str) -> bool:
        relative = path if isinstance(path, str) else path.relative_to(self.profile.root).as_posix()
        relative = relative.rstrip("/")
        for index, entry in enumerate(self.entries):
            if entry.check != check:
                continue
            if entry.until < self.today:
                continue  # expired silences nothing
            if _under(relative, entry.path):
                self.used.add(index)
                return True
        return False

    def reports(self) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        for index, entry in enumerate(self.entries):
            if entry.until < self.today:
                errors.append(
                    f"exemption for {entry.check} on {entry.path} expired on {entry.until}; "
                    "fix the issue or extend the date with a new reason"
                )
                continue
            if index not in self.used:
                warnings.append(
                    f"exemption for {entry.check} on {entry.path} matched no issue; "
                    f"remove it ({entry.reason})"
                )
        return errors, warnings


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


def link_errors(profile: Profile, exempt: _Exemptions) -> list[str]:
    errors: list[str] = []
    for path in markdown_files(profile):
        text = _strip_code(artifacts.read_text(path))
        seen: set[str] = set()
        for target in _targets(text):
            if target in seen:
                continue
            seen.add(target)
            if _resolves(path.parent, target):
                continue
            if exempt.allows("links", path):
                continue
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


def index_warnings(profile: Profile, exempt: _Exemptions) -> list[str]:
    """Every markdown file in a directory is linked from that directory's README.

    A file nobody links is a file nobody reads; the warning names both sides.
    """
    warnings: list[str] = []
    for directory in _index_dirs(profile):
        if _excluded_from_index(profile, directory):
            continue
        readme = directory / "README.md"
        if not readme.is_file():
            continue
        text = _strip_code(artifacts.read_text(readme))
        linked = {Path(target).name for target in _targets(text)}
        for path in sorted(directory.glob("*.md")):
            if path.name == "README.md":
                continue
            if path.name in linked:
                continue
            if exempt.allows("index", path):
                continue
            warnings.append(
                f"{path.relative_to(profile.root)}: not linked from "
                f"{readme.relative_to(profile.root)}"
            )
    return warnings


def _excluded_from_index(profile: Profile, path: Path) -> bool:
    """Record stores and history are not part of the document tree.

    Items live under `work_dir` and are listed by `status`; release records are
    ordered by the commit graph. Neither is reached by following README links,
    and demanding an index for them would be noise.
    """
    relative = path.relative_to(profile.root)
    if _is_hidden(relative):
        return True
    if artifacts.ARCHIVE_DIR in relative.parts:
        return True
    for store in (profile.work_path, profile.release_path):
        try:
            path.relative_to(store)
        except ValueError:
            continue
        return True
    return False


def _edge_target(path: Path, target: str) -> Path | None:
    """The file a link points at, resolving a directory to its index."""
    candidate = path.parent / target
    if candidate.is_file():
        return candidate.resolve()
    if candidate.is_dir():
        for name in INDEX_NAMES:
            index = candidate / name
            if index.is_file():
                return index.resolve()
    if not Path(target).suffix:
        plain = path.parent / f"{target}.md"
        if plain.is_file():
            return plain.resolve()
    return None


def index_graph_warnings(profile: Profile, exempt: _Exemptions) -> list[str]:
    """Every index is reachable from the root index, and every directory has one.

    The per-directory rule above only covers directories that already have a
    README, so a subtree nobody links was invisible. This walks the link graph
    from `docs_dir/README.md` and reports the indexes it cannot reach.
    """
    docs = profile.docs_path
    if not docs.is_dir():
        return []
    files = [
        path
        for path in docs.rglob("*.md")
        if path.is_file() and not _excluded_from_index(profile, path)
    ]
    if not files:
        return []

    warnings: list[str] = []
    root_index = docs / "README.md"
    root_relative = root_index.relative_to(profile.root).as_posix()
    nodes = {path.resolve() for path in files}
    reachable: set[Path] = set()
    if not root_index.is_file():
        if root_relative not in profile.required_docs:
            warnings.append(
                f"{root_relative}: no index at the root of the document tree; "
                "add one and link every directory index from it"
            )
    else:
        queue = [root_index.resolve()]
        while queue:
            current = queue.pop()
            if current in reachable:
                continue
            reachable.add(current)
            if current not in nodes:
                continue
            for target in _targets(_strip_code(artifacts.read_text(current))):
                following = _edge_target(current, target)
                if following and following in nodes and following not in reachable:
                    queue.append(following)

        for path in files:
            if path.name != "README.md" or path.resolve() in reachable:
                continue
            if exempt.allows("index", path):
                continue
            warnings.append(
                f"{path.relative_to(profile.root)}: index is not reachable from "
                f"{root_relative}; link it from an indexed document"
            )

    for directory in sorted({path.parent for path in files}):
        if directory == docs or (directory / "README.md").is_file():
            continue
        relative = directory.relative_to(profile.root).as_posix() + "/"
        if exempt.allows("index", relative):
            continue
        warnings.append(
            f"{relative}: has markdown files but no README.md; its documents have no index"
        )
    return warnings


ARTIFACT_NAMES = ("design.md", "implementation.md", "test-report.md")


def artifact_warnings(profile: Profile, exempt: _Exemptions) -> list[str]:
    """Files that exist inside an item must be mentioned by its item.md."""
    warnings: list[str] = []
    for item in artifacts.all_items(profile):
        text = artifacts.read_text(item.path)
        for name in ARTIFACT_NAMES:
            artifact = item.directory / name
            if not artifact.is_file() or name in text:
                continue
            if exempt.allows("artifact", artifact):
                continue
            warnings.append(
                f"{item.directory.name}/{name}: exists but item.md never mentions it; "
                "link it so the next session finds it"
            )
    return warnings


def archive_index_warnings(profile: Profile, exempt: _Exemptions) -> list[str]:
    """The archive index is the record store's entry point; keep it honest."""
    base = profile.work_path / artifacts.ARCHIVE_DIR
    items = artifacts.archived_items(profile)
    if not items:
        return []
    index = base / "README.md"
    if not index.is_file():
        return [
            f"{index.relative_to(profile.root)}: archived items exist but the index is missing; "
            "run flow.py archive/unarchive to rebuild it"
        ]
    text = artifacts.read_text(index)
    if exempt.allows("artifact", index):
        return []
    linked: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells:
            continue
        match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", cells[0])
        if match:
            linked.add(match.group(1))
    warnings: list[str] = []
    for item in items:
        if item.id not in text:
            warnings.append(
                f"{item.directory.name}: archived item has no row in "
                f"{index.relative_to(profile.root)}; restore it with unarchive/archive"
            )
    known = {item.id for item in items}
    for item_id in sorted(linked - known):
        if exempt.allows("artifact", index):
            continue
        warnings.append(
            f"{index.relative_to(profile.root)}: row for {item_id} has no archived item; "
            "restore the item or remove the row"
        )
    return warnings


def heading_errors(profile: Profile, exempt: _Exemptions) -> list[str]:
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
            if exempt.allows("heading", path):
                continue
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


def zero_fact_warnings(profile: Profile, exempt: _Exemptions) -> list[str]:
    """Entry documents may not pin versions, ports, dates, or counts.

    Each of those is a fact with a single authority elsewhere; a copy in a
    README is a copy that will drift.
    """
    warnings: list[str] = []
    checks = (
        (VERSION_PIN_RE, "pins a version"),
        (PORT_RE, "hardcodes a port"),
        (DATE_RE, "hardcodes a date"),
        (COUNT_RE, "hardcodes a count"),
    )
    for path in _entry_docs(profile):
        for number, line in enumerate(artifacts.read_text(path).splitlines(), 1):
            for pattern, label in checks:
                match = pattern.search(line)
                if not match:
                    continue
                if exempt.allows("zero_fact", path):
                    continue
                warnings.append(
                    f"{path.relative_to(profile.root)}:{number}: {label} "
                    f"({match.group(0)}); link to its single source instead"
                )
    return warnings


def archive_link_warnings(profile: Profile, exempt: _Exemptions) -> list[str]:
    """Live documents link the archive index, never an archived item directly."""
    warnings: list[str] = []
    for path in markdown_files(profile):
        if artifacts.ARCHIVE_DIR in path.parts:
            continue
        for target in _targets(_strip_code(artifacts.read_text(path))):
            resolved = (path.parent / target).resolve()
            if artifacts.ARCHIVE_DIR not in resolved.parts:
                continue
            if exempt.allows("archive_link", path):
                continue
            warnings.append(
                f"{path.relative_to(profile.root)}: links into {artifacts.ARCHIVE_DIR}/ "
                f"({target}); link the archive index instead"
            )
    return warnings


def _decision_field(text: str, *names: str) -> str:
    for name in names:
        # `[ \t]` matters: `\s` crossed the newline and made an empty field
        # swallow the next bullet, so the shipped decision template failed its
        # own checker.
        match = re.search(
            rf"^[ \t]*[-*][ \t]*(?:\*\*)?{re.escape(name)}(?:\*\*)?[ \t]*[:：][ \t]*"
            r"(.+?)[ \t]*$",
            text,
            re.M | re.I,
        )
        if match:
            return match.group(1).strip()
    return ""


def _decision_target(value: str, directory: Path) -> tuple[str, Path | None]:
    """The file a supersede pointer names, tolerating a markdown link."""
    value = value.strip().strip("`")
    match = artifacts.LINK_RE.search(value)
    target = match.group(1) if match else value
    target = target.split("#", 1)[0].strip()
    if not target or target.lower() in {"none", "-", "—", "n/a"}:
        return "", None
    return target, directory / target


def decisions_errors(profile: Profile) -> list[str]:
    """A decision is superseded, never rewritten: the pointers must form a chain.

    The template promises this; without a check the promise was prose. Status is
    an enum, a superseded decision names its successor, the successor exists in
    the same directory, and following the pointers terminates.
    """
    if not profile.docs_decisions:
        return []
    directory = profile.root / profile.docs_decisions
    errors: list[str] = []
    if not directory.is_dir():
        errors.append(f"docs.decisions points at a missing directory: {profile.docs_decisions}")
        return errors
    if not (directory / "README.md").is_file():
        errors.append(
            f"{profile.docs_decisions}/README.md is missing; it is the index of decisions"
        )

    files = [path for path in sorted(directory.glob("*.md")) if path.name != "README.md"]
    seen_ids: dict[str, Path] = {}
    successors: dict[Path, Path] = {}
    for path in files:
        if path.stem in seen_ids:
            errors.append(
                f"{path.relative_to(profile.root)}: duplicate decision id '{path.stem}' "
                f"(also {seen_ids[path.stem].name}); one decision per id"
            )
        else:
            seen_ids[path.stem] = path

        text = artifacts.read_text(path)
        label = path.relative_to(profile.root).as_posix()
        status = _decision_field(text, "Status", "状态").lower()
        if not status:
            errors.append(f"{label}: missing '- Status:'")
            continue
        if status not in DECISION_STATUSES:
            errors.append(
                f"{label}: status {status!r} must be one of {', '.join(DECISION_STATUSES)}"
            )

        pointer = _decision_field(text, "Superseded by", "被取代")
        supersedes = _decision_field(text, "Supersedes", "取代")
        if status == "superseded":
            target, resolved = _decision_target(pointer, directory)
            if not target:
                errors.append(f"{label}: status is superseded but '- Superseded by:' is empty")
            elif resolved is None or not resolved.is_file() or resolved.parent != directory:
                errors.append(
                    f"{label}: '- Superseded by: {target}' does not name a decision "
                    "in this directory"
                )
            else:
                successors[path.resolve()] = resolved.resolve()
        elif pointer and _decision_target(pointer, directory)[0]:
            errors.append(
                f"{label}: names a successor but status is {status!r}; "
                "set '- Status: superseded' or remove '- Superseded by:'"
            )

        target, resolved = _decision_target(supersedes, directory)
        if target and (resolved is None or not resolved.is_file()):
            errors.append(f"{label}: '- Supersedes: {target}' does not exist")

    reported: set[frozenset[Path]] = set()
    for start in sorted(successors):
        seen: list[Path] = []
        current: Path | None = start
        while current is not None and current in successors:
            if current in seen:
                cycle = frozenset(seen[seen.index(current) :])
                if cycle not in reported:
                    reported.add(cycle)
                    names = ", ".join(path.name for path in sorted(cycle))
                    errors.append(f"decision supersede chain cycles: {names}")
                break
            seen.append(current)
            current = successors[current]
    return errors


def switch_warnings(profile: Profile) -> list[str]:
    """A check that is off, or on but inert, must say so on every run.

    `check_links = false` and `zero_fact = false` predate `[[exempt]]` and are
    migration switches, not settings. Leaving them unreported is how a project
    ends up believing a check ran. An enabled check with no entry document in
    `[docs] required` is the same failure with extra steps: nothing fails, and
    nothing is inspected.
    """
    warnings: list[str] = []
    if not profile.docs_check_links:
        warnings.append(
            "[docs] check_links = false: relative-link validation is off for this "
            "project; replace it with [[exempt]] entries (one path, a reason, an "
            "expiry) and declare the switch in AGENTS.md"
        )
    if not profile.docs_zero_fact:
        warnings.append(
            "[docs] zero_fact = false: entry documents may pin versions, ports, "
            "dates, and counts; replace it with [[exempt]] entries and declare the "
            "switch in AGENTS.md"
        )
    if profile.docs_zero_fact and not _entry_docs(profile):
        warnings.append(
            "zero_fact is enabled but [docs] required lists no entry document "
            "(README.md or AGENTS.md), so the check inspects nothing; add one to "
            "[docs] required"
        )
    return warnings


def problems(profile: Profile) -> tuple[list[str], list[str]]:
    """All document checks, each behind its profile toggle."""
    exempt = _Exemptions(profile)
    errors: list[str] = []
    warnings: list[str] = []
    warnings.extend(switch_warnings(profile))
    if profile.docs_check_links:
        errors.extend(link_errors(profile, exempt))
    errors.extend(heading_errors(profile, exempt))
    errors.extend(decisions_errors(profile))
    warnings.extend(index_warnings(profile, exempt))
    warnings.extend(index_graph_warnings(profile, exempt))
    warnings.extend(artifact_warnings(profile, exempt))
    warnings.extend(archive_index_warnings(profile, exempt))
    warnings.extend(archive_link_warnings(profile, exempt))
    if profile.docs_zero_fact:
        warnings.extend(zero_fact_warnings(profile, exempt))
    exemption_errors, exemption_warnings = exempt.reports()
    errors.extend(exemption_errors)
    warnings.extend(exemption_warnings)
    return errors, warnings
