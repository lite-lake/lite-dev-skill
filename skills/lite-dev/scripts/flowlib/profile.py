"""Load and validate docs/flow/profile.toml, then apply enabled extensions.

The profile is the only place where project-specific facts live. No module in
this package may contain a project name, repository name, or build command.
"""
from __future__ import annotations

import re
import shlex
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import __version__

PROFILE_REL = ("docs", "flow", "profile.toml")
SKILL_ROOT = Path(__file__).resolve().parents[2]
SKILL_TOKEN = "{skill}"
TYPES = ("REQ", "BUG", "TD", "OPS", "IDEA")
SIZES = ("S", "M", "L")
PRIORITIES = ("P0", "P1", "P2", "P3")
MODES = ("one-shot", "two-phase")
LEVELS = ("l1", "l2", "l3")
TIME_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
TIME_LEN = 6
EXTENSION_KEYS = {"name", "version", "description", "requires", "commands", "gate", "docs", "reconcile"}
# Checks an exemption may silence. Evidence is deliberately absent: an exemption
# records drift, it does not waive an invariant.
EXEMPT_CHECKS = ("links", "index", "artifact", "archive_link", "zero_fact", "heading")


class ProfileError(Exception):
    """The profile or one of its extensions is missing or inconsistent."""


@dataclass
class Exemption:
    """A bounded silence: one check, one path, a reason, and an expiry date."""

    check: str
    path: str
    reason: str
    until: str


@dataclass
class Profile:
    root: Path
    path: Path
    name: str
    language: str
    owners: list[str]
    docs_dir: str
    work_dir: str
    id_format: str
    commands: dict[str, str]
    gate: dict[str, list[str]]
    design_required_for: list[str]
    design_require_confirmed: bool
    design_risk_paths: list[str]
    design_risk_exempt: list[str]
    design_risk_gate: str
    required_docs: list[str]
    docs_check_links: bool
    docs_zero_fact: bool
    docs_decisions: str
    exemptions: list[Exemption]
    release_channels: list[str]
    release_dir: str
    release_gate_level: str
    release_mainline: str
    release_require_artifacts: bool
    release_confirm_risk_paths: bool
    risk_paths: list[str]
    gate_fallback_paths: list[str]
    gate_fresh_days: int
    extensions_enabled: list[str]
    extensions_dir: str
    extension_info: list[dict]
    requires: str
    id_pattern: re.Pattern

    @property
    def work_path(self) -> Path:
        return self.root / self.work_dir

    @property
    def docs_path(self) -> Path:
        return self.root / self.docs_dir

    @property
    def release_path(self) -> Path:
        return self.root / self.release_dir

    @property
    def full_level(self) -> str | None:
        """The strictest defined level: the one a cheap level cannot replace."""
        for level in ("l3", "l2", "l1"):
            if self.gate.get(level):
                return level
        return None


def find_profile(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for base in (current, *current.parents):
        candidate = base.joinpath(*PROFILE_REL)
        if candidate.is_file():
            return candidate
    raise ProfileError(
        "no docs/flow/profile.toml found; run from the project root or pass --profile"
    )


def _require(table: dict, key: str, where: str, kind: type = str):
    if key not in table:
        raise ProfileError(f"{where}: missing '{key}'")
    value = table[key]
    if not isinstance(value, kind):
        raise ProfileError(f"{where}: '{key}' must be {kind.__name__}")
    return value


def _string_list(value, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProfileError(f"{where} must be a list of strings")
    return list(value)


def _allow_keys(table: dict, allowed: tuple[str, ...], where: str) -> None:
    unknown = set(table) - set(allowed)
    if unknown:
        raise ProfileError(f"{where}: unknown key(s) {', '.join(sorted(unknown))}")


def _exemptions(value) -> list[Exemption]:
    """Parse `[[exempt]]`: a check, a path prefix, a reason, and an expiry.

    A silence without a reason or an end date is the failure this replaces: the
    old `check_links = false` switch silenced the whole project forever. Every
    field is required, and `check` reports an expired entry instead of honouring
    it, so the exemption cannot outlive the reason for it.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProfileError("[[exempt]] must be an array of tables")
    result: list[Exemption] = []
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(value, 1):
        where = f"[[exempt]] #{index}"
        if not isinstance(entry, dict):
            raise ProfileError(f"{where} must be a table")
        _allow_keys(entry, ("check", "path", "reason", "until"), where)
        for key in ("check", "path", "reason", "until"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ProfileError(f"{where}: '{key}' is required and must be a non-empty string")
        check = entry["check"].strip()
        if check not in EXEMPT_CHECKS:
            raise ProfileError(
                f"{where}: unknown check '{check}'; use one of {', '.join(EXEMPT_CHECKS)}"
            )
        path = entry["path"].strip().rstrip("/")
        if Path(path).is_absolute():
            raise ProfileError(f"{where}: 'path' must be relative to the project root")
        until = entry["until"].strip()
        try:
            date.fromisoformat(until)
        except ValueError as exc:
            raise ProfileError(f"{where}: 'until' must be a date, e.g. 2027-03-31") from exc
        key = (check, path)
        if key in seen:
            raise ProfileError(f"{where}: duplicate exemption for {check} on {path}")
        seen.add(key)
        result.append(Exemption(check=check, path=path, reason=entry["reason"].strip(), until=until))
    return result


def _parse_version(text: str) -> tuple[int, int, int]:
    parts = text.strip().lstrip("v").split(".")
    if not 1 <= len(parts) <= 3 or any(not part.isdigit() for part in parts):
        raise ProfileError(f"invalid version {text!r}; use MAJOR[.MINOR[.PATCH]]")
    numbers = [int(part) for part in parts] + [0, 0]
    return numbers[0], numbers[1], numbers[2]


def satisfies(version: str, spec: str) -> bool:
    """Check a version against a comma-separated range.

    '>=0.2,<0.3' is explicit. A bare version is a line, not an exact match:
    '0.2' means >=0.2.0,<0.3.0 and '1' means >=1.0.0,<2.0.0. A full X.Y.Z
    without an operator means exactly that version.
    """
    current = _parse_version(version)
    if not spec.strip():
        raise ProfileError("extension requires must not be empty")
    for clause in spec.split(","):
        clause = clause.strip()
        match = re.match(r"^(>=|<=|==|>|<)?\s*(.+)$", clause)
        if not match:
            raise ProfileError(f"invalid version range {spec!r}")
        operator = match.group(1)
        raw = match.group(2)
        if operator is None:
            pieces = raw.lstrip("v").split(".")
            if len(pieces) == 3:
                if current != _parse_version(raw):
                    return False
            elif len(pieces) in (1, 2):
                base = _parse_version(raw)
                if len(pieces) == 1:
                    upper = (base[0] + 1, 0, 0)
                else:
                    upper = (base[0], base[1] + 1, 0)
                if not (base <= current < upper):
                    return False
            else:
                raise ProfileError(f"invalid version {raw!r}")
            continue
        wanted = _parse_version(raw)
        if operator == ">=" and not current >= wanted:
            return False
        if operator == ">" and not current > wanted:
            return False
        if operator == "<=" and not current <= wanted:
            return False
        if operator == "<" and not current < wanted:
            return False
        if operator == "==" and not current == wanted:
            return False
    return True


def _expand(command: str) -> str:
    """Replace `{skill}` with the installed skill root, shell-quoted.

    A bundled extension ships scripts inside the skill; this is how its command
    names one without hardcoding a machine path. The value comes from the
    installed skill, never from project input.
    """
    if SKILL_TOKEN not in command:
        return command
    return command.replace(SKILL_TOKEN, shlex.quote(str(SKILL_ROOT)))


def _id_pattern(id_format: str) -> re.Pattern:
    tokens = re.split(r"(\{[^}]+\})", id_format)
    parts: list[str] = []
    for token in tokens:
        if token == "{date}":
            parts.append(r"\d{8}")
        elif token == "{type}":
            parts.append(r"[A-Z]+")
        elif token == "{time}":
            parts.append(f"[{TIME_ALPHABET}]{{{TIME_LEN}}}")
        elif token.startswith("{"):
            raise ProfileError(
                f"[id] format has unknown placeholder {token}; "
                "supported: {date}, {type}, {time}"
            )
        else:
            parts.append(re.escape(token))
    return re.compile(r"(?<![A-Za-z0-9])" + "".join(parts) + r"(?![A-Za-z0-9])")


def _merge_extension(
    name: str,
    path: Path,
    source: str,
    commands: dict[str, str],
    gate: dict[str, list[str]],
    required_docs: list[str],
    risk_paths: list[str],
) -> dict:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProfileError(f"cannot read extension {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{path}: invalid TOML: {exc}") from exc

    unknown = set(raw) - EXTENSION_KEYS
    if unknown:
        raise ProfileError(
            f"extension '{name}': unknown key(s) {', '.join(sorted(unknown))}; "
            "extensions may only add commands, gate steps, docs and risk paths"
        )
    if raw.get("name") != name:
        raise ProfileError(f"extension '{name}': name in extension.toml must match the directory")
    requires = raw.get("requires")
    if not isinstance(requires, str) or not requires.strip():
        raise ProfileError(f"extension '{name}': 'requires' is required, e.g. '>=0.2,<0.3'")
    if not satisfies(__version__, requires):
        raise ProfileError(
            f"extension '{name}' requires lite-dev {requires}, but this is {__version__}; "
            "install the matching skill version or lower the extension's requires"
        )

    ext_commands = raw.get("commands") or {}
    if not isinstance(ext_commands, dict):
        raise ProfileError(f"extension '{name}': [commands] must be a table")
    for command_name, command in ext_commands.items():
        if not isinstance(command, str) or not command.strip():
            raise ProfileError(f"extension '{name}': command {command_name!r} must be non-empty")
        if command_name in commands and commands[command_name] != command:
            raise ProfileError(
                f"extension '{name}': command '{command_name}' collides with an existing "
                "definition; extensions may add, not replace"
            )
        commands.setdefault(command_name, command)

    ext_gate = raw.get("gate") or {}
    if not isinstance(ext_gate, dict):
        raise ProfileError(f"extension '{name}': [gate] must be a table")
    for level, steps in ext_gate.items():
        if level not in LEVELS:
            raise ProfileError(f"extension '{name}': unknown gate level '{level}'")
        steps = _string_list(steps, f"extension '{name}': [gate] {level}")
        gate.setdefault(level, [])
        for step in steps:
            if step not in gate[level]:
                gate[level].append(step)

    ext_docs = raw.get("docs") or {}
    if not isinstance(ext_docs, dict) or set(ext_docs) - {"required"}:
        raise ProfileError(f"extension '{name}': [docs] may only contain 'required'")
    for relative in _string_list(
        ext_docs.get("required", []), f"extension '{name}': [docs] required"
    ):
        if relative not in required_docs:
            required_docs.append(relative)

    ext_reconcile = raw.get("reconcile") or {}
    if not isinstance(ext_reconcile, dict) or set(ext_reconcile) - {"risk_paths"}:
        raise ProfileError(
            f"extension '{name}': [reconcile] may only contain 'risk_paths'"
        )
    for risk in _string_list(
        ext_reconcile.get("risk_paths", []), f"extension '{name}': [reconcile] risk_paths"
    ):
        if risk not in risk_paths:
            risk_paths.append(risk)

    return {
        "name": name,
        "version": str(raw.get("version", "") or ""),
        "description": str(raw.get("description", "") or ""),
        "requires": requires,
        "source": source,
        "gate": {level: list(steps) for level, steps in ext_gate.items()},
        "commands": sorted(ext_commands),
        "docs": list(
            dict.fromkeys(
                item
                for item in _string_list(
                    ext_docs.get("required", []), f"extension '{name}': [docs] required"
                )
            )
        ),
        "risk_paths": list(
            dict.fromkeys(
                item
                for item in _string_list(
                    ext_reconcile.get("risk_paths", []),
                    f"extension '{name}': [reconcile] risk_paths",
                )
            )
        ),
    }


def _apply_extensions(
    root: Path,
    table: dict,
    commands: dict[str, str],
    gate: dict[str, list[str]],
    required_docs: list[str],
    risk_paths: list[str],
) -> tuple[list[str], str, list[dict]]:
    if not isinstance(table, dict):
        raise ProfileError("[extensions] must be a table")
    enabled = _string_list(table.get("enabled", []), "[extensions] enabled")
    extensions_dir = table.get("dir", "docs/flow/extensions")
    if not isinstance(extensions_dir, str) or not extensions_dir.strip():
        raise ProfileError("[extensions] dir must be a non-empty relative path")
    if Path(extensions_dir).is_absolute():
        raise ProfileError("[extensions] dir must be relative to the project root")

    bundled_root = Path(__file__).resolve().parents[2] / "extensions"
    info: list[dict] = []
    for name in dict.fromkeys(enabled):
        project_path = root / extensions_dir / name / "extension.toml"
        bundled_path = bundled_root / name / "extension.toml"
        if project_path.is_file() and bundled_path.is_file():
            raise ProfileError(
                f"extension '{name}' exists both in {extensions_dir}/ and in the skill; "
                "keep exactly one copy"
            )
        if project_path.is_file():
            path, source = project_path, "project"
        elif bundled_path.is_file():
            path, source = bundled_path, "bundled"
        else:
            raise ProfileError(
                f"extension '{name}' not found in {extensions_dir}/ or the skill's extensions/"
            )
        info.append(
            _merge_extension(name, path, source, commands, gate, required_docs, risk_paths)
        )
    return enabled, extensions_dir, info


def load(path: Path | str | None = None) -> Profile:
    profile_path = Path(path).resolve() if path else find_profile()
    try:
        raw = tomllib.loads(profile_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProfileError(f"cannot read {profile_path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{profile_path}: invalid TOML: {exc}") from exc

    for key in ("project", "id", "flow", "commands", "gate"):
        if not isinstance(raw.get(key), dict):
            raise ProfileError(f"[{key}] table is required")

    project = raw["project"]
    id_table = raw["id"]
    commands = dict(raw["commands"])
    gate_table = raw["gate"]
    # Validate the raw table first: filtering before validation used to drop a
    # typo like `l4 = [...]` silently, leaving a gate level that looked defined.
    _allow_keys(gate_table, (*LEVELS, "fallback_paths", "fresh_days"), "[gate]")
    for level in LEVELS:
        if level in gate_table and not isinstance(gate_table[level], list):
            raise ProfileError(f"[gate] {level} must be a list of command names")
    gate = {
        level: list(steps)
        for level, steps in gate_table.items()
        if level in LEVELS and isinstance(steps, list)
    }
    design = raw.get("design") or {}
    docs = raw.get("docs") or {}
    release = raw.get("release") or {}
    reconcile = raw.get("reconcile") or {}
    extensions = raw.get("extensions") or {}
    flow_table = raw.get("flow") or {}

    _allow_keys(
        project, ("name", "language", "owners", "docs_dir", "work_dir"), "[project]"
    )
    _allow_keys(id_table, ("format",), "[id]")
    _allow_keys(
        design,
        ("required_for", "require_confirmed", "risk_paths", "risk_exempt", "risk_gate"),
        "[design]",
    )
    _allow_keys(docs, ("required", "check_links", "zero_fact", "decisions"), "[docs]")
    _allow_keys(
        release,
        (
            "channels",
            "dir",
            "gate_level",
            "mainline",
            "require_artifacts",
            "confirm_risk_paths",
        ),
        "[release]",
    )
    _allow_keys(reconcile, ("risk_paths",), "[reconcile]")
    _allow_keys(extensions, ("enabled", "dir"), "[extensions]")
    _allow_keys(flow_table, ("requires",), "[flow]")
    _allow_keys(gate, (*LEVELS, "fallback_paths", "fresh_days"), "[gate]")

    name = _require(project, "name", "[project]")
    language = project.get("language", "en")
    if language not in ("en", "zh"):
        raise ProfileError("[project] language must be 'en' or 'zh'")

    owners = _string_list(project.get("owners", []), "[project] owners")
    owners = list(dict.fromkeys(owner.strip() for owner in owners if owner.strip()))

    docs_dir = project.get("docs_dir", "docs")
    work_dir = project.get("work_dir", f"{docs_dir}/work")
    for label, value in (("docs_dir", docs_dir), ("work_dir", work_dir)):
        if not isinstance(value, str) or not value.strip():
            raise ProfileError(f"[project] {label} must be a non-empty relative path")
        if Path(value).is_absolute():
            raise ProfileError(f"[project] {label} must be relative to the project root")

    id_format = _require(id_table, "format", "[id]")
    for token in ("{date}", "{type}", "{time}"):
        if token not in id_format:
            raise ProfileError(
                f"[id] format must contain {{date}}, {{type}} and {{time}}; got {id_format!r}"
            )

    required_for = design.get("required_for", ["L"])
    if not isinstance(required_for, list) or any(size not in SIZES for size in required_for):
        raise ProfileError("[design] required_for must be a subset of S, M, L")
    require_confirmed = design.get("require_confirmed", True)
    if not isinstance(require_confirmed, bool):
        raise ProfileError("[design] require_confirmed must be true or false")
    design_risk_paths = _string_list(design.get("risk_paths", []), "[design] risk_paths")
    design_risk_exempt = _string_list(design.get("risk_exempt", []), "[design] risk_exempt")
    design_risk_gate = design.get("risk_gate", "warn")
    if design_risk_gate not in ("warn", "block"):
        raise ProfileError("[design] risk_gate must be 'warn' or 'block'")

    required_docs = _string_list(docs.get("required", []), "[docs] required")
    docs_check_links = docs.get("check_links", True)
    docs_zero_fact = docs.get("zero_fact", True)
    for label, value in (("check_links", docs_check_links), ("zero_fact", docs_zero_fact)):
        if not isinstance(value, bool):
            raise ProfileError(f"[docs] {label} must be true or false")
    docs_decisions = docs.get("decisions", "")
    if not isinstance(docs_decisions, str):
        raise ProfileError("[docs] decisions must be a relative path or empty")
    docs_decisions = docs_decisions.strip()
    if docs_decisions and Path(docs_decisions).is_absolute():
        raise ProfileError("[docs] decisions must be relative to the project root")

    gate_fallback_paths = _string_list(
        gate_table.get("fallback_paths", []), "[gate] fallback_paths"
    )
    gate_fresh_days = gate_table.get("fresh_days", 5)
    if not isinstance(gate_fresh_days, int) or isinstance(gate_fresh_days, bool) or gate_fresh_days < 0:
        raise ProfileError("[gate] fresh_days must be a non-negative integer")

    release_channels = _string_list(
        release.get("channels", []), "[release] channels"
    )
    release_dir = release.get("dir", "docs/releases")
    if not isinstance(release_dir, str) or not release_dir.strip():
        raise ProfileError("[release] dir must be a non-empty relative path")
    if Path(release_dir).is_absolute():
        raise ProfileError("[release] dir must be relative to the project root")
    release_gate_level = release.get("gate_level", "l3")
    if release_gate_level not in LEVELS:
        raise ProfileError("[release] gate_level must be one of l1, l2, l3")
    release_mainline = release.get("mainline", "")
    if not isinstance(release_mainline, str):
        raise ProfileError("[release] mainline must be a branch name")
    release_mainline = release_mainline.strip()
    if release_channels and not release_mainline:
        raise ProfileError(
            '[release] mainline is required when channels are configured, e.g. mainline = "main"'
        )
    release_require_artifacts = release.get("require_artifacts", False)
    if not isinstance(release_require_artifacts, bool):
        raise ProfileError("[release] require_artifacts must be true or false")
    release_confirm_risk_paths = release.get("confirm_risk_paths", False)
    if not isinstance(release_confirm_risk_paths, bool):
        raise ProfileError("[release] confirm_risk_paths must be true or false")
    if release_confirm_risk_paths and not design_risk_paths:
        raise ProfileError(
            "[release] confirm_risk_paths needs [design] risk_paths; "
            "nothing would ever require confirmation"
        )
    exemptions = _exemptions(raw.get("exempt"))

    requires = _require(flow_table, "requires", "[flow]").strip()
    if not requires:
        raise ProfileError(
            "[flow] requires must be a version range, e.g. '>=0.3,<0.4'"
        )
    if not satisfies(__version__, requires):
        raise ProfileError(
            f"this project requires lite-dev {requires}, but this is {__version__}; "
            "install the matching skill version"
        )

    risk_paths = _string_list(
        reconcile.get("risk_paths", []), "[reconcile] risk_paths"
    )

    # Normally <root>/docs/flow/profile.toml. Prefer the repository root when
    # there is a .git; otherwise honor the conventional three-level path and
    # fall back to the profile's own directory for a custom --profile file.
    root = None
    for parent in profile_path.parents:
        if (parent / ".git").exists():
            root = parent
            break
    if root is None:
        if profile_path.parent.name == "flow" and profile_path.parent.parent.name == "docs":
            root = profile_path.parents[2]
        else:
            root = profile_path.parent
    extensions_enabled, extensions_dir, extension_info = _apply_extensions(
        root, extensions, commands, gate, required_docs, risk_paths
    )

    if not commands:
        raise ProfileError("[commands] must define at least one command")
    for command_name, command in commands.items():
        if not isinstance(command, str):
            raise ProfileError(f"[commands] {command_name} must be a string")
    for level, steps in gate.items():
        if level not in LEVELS:
            raise ProfileError(f"[gate] unknown level '{level}'; use l1, l2 or l3")
        if not isinstance(steps, list) or not all(isinstance(step, str) for step in steps):
            raise ProfileError(f"[gate] {level} must be a list of command names")
        for command_name in steps:
            if command_name not in commands:
                raise ProfileError(
                    f"[gate] {level} references unknown command '{command_name}'"
                )
            if not commands[command_name].strip():
                raise ProfileError(f"[commands] {command_name} is empty")
    if not gate:
        raise ProfileError("[gate] must define at least one of l1/l2/l3")
    if release_channels and release_gate_level not in gate:
        raise ProfileError(
            f"[release] gate_level '{release_gate_level}' is not defined in [gate]"
        )

    id_pattern = _id_pattern(id_format)
    try:
        id_format.format(date="20000101", type="REQ", time="222222")
    except (KeyError, IndexError, ValueError) as exc:
        raise ProfileError(f"[id] format is invalid: {exc}") from exc

    return Profile(
        root=root,
        path=profile_path,
        name=name,
        language=language,
        owners=owners,
        docs_dir=docs_dir,
        work_dir=work_dir,
        id_format=id_format,
        commands={key: _expand(value) for key, value in commands.items()},
        gate={level: list(steps) for level, steps in gate.items()},
        design_required_for=list(required_for),
        design_require_confirmed=require_confirmed,
        design_risk_paths=list(design_risk_paths),
        design_risk_exempt=list(design_risk_exempt),
        design_risk_gate=design_risk_gate,
        required_docs=list(required_docs),
        docs_check_links=docs_check_links,
        docs_zero_fact=docs_zero_fact,
        docs_decisions=docs_decisions,
        exemptions=list(exemptions),
        release_channels=list(release_channels),
        release_dir=release_dir,
        release_gate_level=release_gate_level,
        release_mainline=release_mainline,
        release_require_artifacts=release_require_artifacts,
        release_confirm_risk_paths=release_confirm_risk_paths,
        risk_paths=list(risk_paths),
        gate_fallback_paths=list(gate_fallback_paths),
        gate_fresh_days=gate_fresh_days,
        extensions_enabled=list(extensions_enabled),
        extensions_dir=extensions_dir,
        extension_info=extension_info,
        requires=requires,
        id_pattern=id_pattern,
    )
