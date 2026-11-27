"""Adoption as a derived rung, not a flag.

A project that introduces lite-dev is not "installed" or "not installed": it is
somewhere on one ladder. Every rung is computed from files, so no adoption state
is stored anywhere — deleting this module's output loses nothing, and two clones
always agree.

Only the first rung (`S1 wired`) blocks the gate. Everything above it is a
visible backlog, because a project must be able to adopt the flow mid-history and
still make its next change.

Writes are always two-phase: detectors propose, `--apply` writes. The profile is
executable input, so no detector may rewrite it on its own, and a proposal is
invalid the moment the value it expected to replace has changed.
"""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from . import artifacts, checks, docs, fsio, git, identity, release, scaffold
from . import profile as profile_mod
from .errors import FlowError
from .profile import Profile, ProfileError

# Each rung names one fact that turns a scaffold into a working project. The
# order is dependency order, not importance: you cannot anchor history you have
# not wired a gate for.
ABSENT = object()
DEFAULT_PLAN_COMMAND = "init --plan"


@dataclass
class Rung:
    id: str
    name: str
    done: bool
    detail: str = ""
    command: str = ""


@dataclass
class Ladder:
    rungs: list[Rung]

    @property
    def done(self) -> int:
        """Consecutive rungs from S0. A later rung does not count past a gap."""
        count = 0
        for rung in self.rungs:
            if not rung.done:
                break
            count += 1
        return count

    @property
    def current(self) -> Rung | None:
        for rung in self.rungs:
            if not rung.done:
                return rung
        return None

    def by_id(self, rung_id: str) -> Rung | None:
        for rung in self.rungs:
            if rung.id == rung_id:
                return rung
        return None


def ladder(
    profile: Profile,
    *,
    items: list[artifacts.Item] | None = None,
    check_errors: list[str] | None = None,
    identity_name: str | None = None,
    resolved: bool | None = None,
) -> Ladder:
    """Compute every rung from files. Callers may pass work they already did.

    `resolved=False` forces the identity rung open for a caller that has just
    checked it; `identity_name` carries the name for the detail line.
    """
    rungs: list[Rung] = []

    rungs.append(Rung("S0", "scaffolded", True, profile.path.name, "status"))

    wiring = profile_mod.wiring_problems(profile)
    rungs.append(
        Rung(
            "S1",
            "wired",
            not wiring,
            wiring[0] if wiring else "",
            DEFAULT_PLAN_COMMAND,
        )
    )

    if check_errors is None:
        check_errors, _ = checks.check_project(profile)
    silence = docs.switch_warnings(profile)
    bounded = not check_errors and not silence
    bounded_detail = ""
    if check_errors:
        bounded_detail = check_errors[0]
        if len(check_errors) > 1:
            bounded_detail += f" (+{len(check_errors) - 1} more; run check)"
    elif silence:
        bounded_detail = silence[0]
    rungs.append(Rung("S2", "bounded", bounded, bounded_detail, "check"))

    baseline = profile.reconcile_baseline
    if baseline:
        anchored_detail = f"baseline {baseline[:7]}"
        anchored = True
    else:
        anchored, anchored_detail = _release_anchor(profile)
    rungs.append(Rung("S3", "anchored", anchored, anchored_detail, "init --baseline"))

    if resolved is None:
        found = identity.try_resolve_for(profile)
        resolved = found is not None
        identity_name = found[0] if found else None
    if resolved:
        owned_detail = identity_name or "this machine has an identity"
        owned = True
    else:
        owned_detail = 'no identity; run git config --global lite-dev.owner "Your Name"'
        owned = False
    rungs.append(Rung("S4", "owned", owned, owned_detail, "whoami"))

    if items is None:
        items = artifacts.all_items(profile) + artifacts.archived_items(profile)
    closed = [item for item in items if item.status == "done"]
    practiced = bool(closed)
    practice_detail = (
        f"{len(closed)} item(s) closed through the flow"
        if practiced
        else "no item has been closed yet; the loop has not run end to end"
    )
    rungs.append(
        Rung(
            "S5",
            "practiced",
            practiced,
            practice_detail,
            'new --title "..." --type REQ --size S',
        )
    )
    return Ladder(rungs)


def _release_anchor(profile: Profile) -> tuple[bool, str]:
    """A release record anchors history too, and it is what S3 really means."""
    for channel in profile.release_channels:
        try:
            record = release.tip(profile, channel)
        except (FlowError, git.GitError, ProfileError):
            record = None
        if record is not None:
            return True, f"release {channel} at {record.source[:7]}"
    return False, "no [reconcile] baseline and no release record"


def render_ladder(
    ladder: Ladder, invocation: str = "flow.py", indent: str = ""
) -> list[str]:
    """The ladder as output lines, with the one next command and why."""
    total = len(ladder.rungs)
    current = ladder.current
    if current is None:
        return [indent + f"adoption: {ladder.done}/{total} — every rung is done"]
    lines = [f"adoption: {ladder.done}/{total} — next {current.id} {current.name}"]
    if current.detail:
        label = "blocked" if current.id == "S1" else "because"
        lines.append(f"  {label}: {current.detail}")
    if current.command:
        lines.append(f"  run:     {invocation} {current.command}")
    return [indent + line for line in lines]


# --------------------------------------------------------------------------
# Proposals: read-only detection, then an explicit write.
# --------------------------------------------------------------------------


@dataclass
class Proposal:
    """One value a detector would write, with the value it expects to replace.

    `section`/`key` make it machine-appliable; a proposal without them is a
    snippet a human pastes. `expect` guards the write: if the profile no longer
    holds that value, the plan is stale and the write is refused.
    """

    id: str
    value: object
    source: str
    section: str = ""
    key: str = ""
    expect: object = ABSENT
    invocation: str = "flow.py init"

    @property
    def applicable(self) -> bool:
        return bool(self.section and self.key)

    @property
    def literal(self) -> str:
        return toml_literal(self.value)


@dataclass
class Plan:
    proposals: list[Proposal] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)

    def find(self, proposal_id: str) -> Proposal | None:
        for proposal in self.proposals:
            if proposal.id == proposal_id:
                return proposal
        return None


def plan(profile: Profile, *, check_errors: list[str] | None = None) -> Plan:
    """Everything the repository says about the profile, as proposals."""
    result = Plan()
    proposals: list[Proposal] = []

    name = _detect_name(profile)
    if name is not None:
        proposals.append(name)
    language = _detect_language(profile)
    if language is not None:
        proposals.append(language)

    wiring = profile_mod.wiring_problems(profile)
    if wiring:
        proposals.extend(_detect_commands(profile))
        if not any(proposal.id.startswith("commands.") for proposal in proposals):
            result.notes.append(
                "no runnable command recognised; set [commands] test by hand, "
                "then add it to [gate]"
            )

    stores = _detect_stores(profile)
    if stores is not None:
        proposals.append(stores)

    result.proposals = proposals
    result.notes.extend(_layout_notes(profile))
    result.notes.extend(_ci_notes(profile))
    result.advice.extend(_exemption_advice(profile, check_errors))
    return result


def upgrade_plan(profile_path: Path) -> Plan:
    """The same idea, for a profile the loader cannot accept yet.

    A version pin from an older install fails to load, so this path reads the
    raw TOML instead of a `Profile`. It never guesses a command: only the pin is
    a proposal, and the rest is advice.
    """
    result = Plan()
    try:
        raw = tomllib.loads(profile_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FlowError(f"cannot read {profile_path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise FlowError(f"{profile_path}: invalid TOML: {exc}") from exc

    flow_table = raw.get("flow") or {}
    requires = flow_table.get("requires", "")
    if not isinstance(requires, str):
        raise FlowError("[flow] requires must be a string")
    current = _compat_range()
    if requires.strip() != current:
        result.proposals.append(
            Proposal(
                id="flow.requires",
                value=current,
                source=f"this install is {profile_mod.__version__}",
                section="flow",
                key="requires",
                expect=requires,
                invocation="flow.py init --upgrade",
            )
        )
    commands = raw.get("commands") or {}
    unconfigured = sorted(
        name for name, command in commands.items()
        if isinstance(command, str) and profile_mod.is_unconfigured(command)
    )
    if unconfigured:
        result.notes.append(
            "commands still unconfigured: " + ", ".join(unconfigured)
            + "; run init --plan after the upgrade to propose real ones"
        )
    result.notes.extend(_raw_layout_notes(raw))
    return result


def _compat_range() -> str:
    """The pin a fresh scaffold writes. One derivation, in the scaffolder."""
    return scaffold.compat_range(profile_mod.__version__)


def _detect_name(profile: Profile) -> Proposal | None:
    if profile.name != "my-project":
        return None
    name = profile.root.name
    if not name or name == "my-project":
        return None
    return Proposal(
        id="project.name",
        value=name,
        source="the project directory name",
        section="project",
        key="name",
        expect=profile.name,
    )


def _detect_language(profile: Profile) -> Proposal | None:
    """Chinese prose means the entry documents should be Chinese too."""
    if profile.language != "en":
        return None
    sample = ""
    for relative in ("README.md", Path(profile.docs_dir) / "README.md"):
        path = profile.root / relative
        if path.is_file():
            try:
                sample += path.read_text(encoding="utf-8")[:5000]
            except OSError:
                continue
    if not sample:
        return None
    visible = [char for char in sample if not char.isspace()]
    if not visible:
        return None
    cjk = sum(1 for char in visible if "\u4e00" <= char <= "\u9fff")
    if cjk / len(visible) < 0.05:
        return None
    return Proposal(
        id="project.language",
        value="zh",
        source="the entry documents are mostly Chinese",
        section="project",
        key="language",
        expect=profile.language,
    )


def _referenced(profile: Profile, name: str) -> bool:
    return any(name in steps for steps in profile.gate.values())


def _detect_commands(profile: Profile) -> list[Proposal]:
    """Wire the commands a gate level already names, from repository evidence."""
    proposals: list[Proposal] = []
    candidates = _command_candidates(profile)
    for name in ("test", "lint"):
        if not _referenced(profile, name):
            continue
        if not profile_mod.is_unconfigured(profile.commands.get(name, "")):
            continue
        match = candidates.get(name)
        if not match:
            continue
        command, source = match
        proposals.append(
            Proposal(
                id=f"commands.{name}",
                value=command,
                source=source,
                section="commands",
                key=name,
                expect=profile.commands.get(name, ""),
            )
        )
    return proposals


def _command_candidates(profile: Profile) -> dict[str, tuple[str, str]]:
    """`{command name: (command, evidence)}`, first match wins.

    The order goes from the most explicit repository convention to the most
    specific ecosystem: a Makefile usually delegates to the rest, and an
    extension detector is an explicit opt-in. Nothing here is a project fact;
    these are ecosystem conventions, and every match is only a proposal.
    """
    root = profile.root
    found: dict[str, tuple[str, str]] = {}
    for detector in profile.extension_detectors:
        marker = root / detector["file"]
        if marker.exists() and "test" not in found:
            source = f"{detector['file']} (extension {detector['name']})"
            found["test"] = (detector["command"], detector.get("note") or source)

    makefile = _read(root / "Makefile")
    if makefile and re.search(r"(?m)^test\s*:", makefile) and "test" not in found:
        found["test"] = ("make test", "Makefile 'test' target")
    if makefile and re.search(r"(?m)^lint\s*:", makefile) and "lint" not in found:
        found["lint"] = ("make lint", "Makefile 'lint' target")

    package = root / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts") or {}
        except (OSError, ValueError):
            scripts = {}
        runner = "npm"
        if (root / "pnpm-lock.yaml").is_file():
            runner = "pnpm"
        elif (root / "yarn.lock").is_file():
            runner = "yarn"
        elif (root / "bun.lockb").is_file():
            runner = "bun"
        if isinstance(scripts, dict):
            if scripts.get("test") and "test" not in found:
                command = f"{runner} test" if runner != "bun" else "bun run test"
                found["test"] = (command, f"package.json scripts.test ({runner})")
            if scripts.get("lint") and "lint" not in found:
                found["lint"] = (
                    f"{runner} run lint" if runner != "npm" else "npm run lint",
                    f"package.json scripts.lint ({runner})",
                )

    if "test" not in found:
        test_command = _python_test_command(root)
        if test_command:
            found["test"] = test_command
    if "lint" not in found and (root / "ruff.toml").is_file():
        found["lint"] = ("python3 -m ruff check .", "ruff.toml")
    elif "lint" not in found and _has_pyproject_tool(root, "ruff"):
        found["lint"] = ("python3 -m ruff check .", "pyproject.toml [tool.ruff]")

    ecosystem = (
        ("go.mod", "go test ./...", "go.mod"),
        ("Cargo.toml", "cargo test", "Cargo.toml"),
        ("pom.xml", _maven_command(root), "pom.xml"),
        ("build.gradle", _gradle_command(root), "build.gradle"),
        ("build.gradle.kts", _gradle_command(root), "build.gradle.kts"),
    )
    for marker, command, label in ecosystem:
        if (root / marker).is_file() and "test" not in found:
            found["test"] = (command, label)
    composer = root / "composer.json"
    if composer.is_file() and "test" not in found:
        try:
            scripts = json.loads(composer.read_text(encoding="utf-8")).get("scripts") or {}
        except (OSError, ValueError):
            scripts = {}
        if isinstance(scripts, dict) and scripts.get("test"):
            found["test"] = ("composer test", "composer.json scripts.test")
    return found


def _maven_command(root: Path) -> str:
    return "./mvnw -q test" if (root / "mvnw").is_file() else "mvn -q test"


def _gradle_command(root: Path) -> str:
    return "./gradlew test" if (root / "gradlew").is_file() else "gradle test"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _has_pyproject_tool(root: Path, tool: str) -> bool:
    path = root / "pyproject.toml"
    if not path.is_file():
        return False
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return tool in (raw.get("tool") or {})


def _python_test_command(root: Path) -> tuple[str, str] | None:
    pytest_evidence = (
        (root / "pytest.ini").is_file()
        or (root / "conftest.py").is_file()
        or _has_pyproject_tool(root, "pytest")
    )
    if pytest_evidence:
        return "python3 -m pytest", "pytest configuration"
    tests = root / "tests"
    if tests.is_dir() and any(tests.glob("test_*.py")):
        return (
            "python3 -m unittest discover -s tests -q",
            "tests/test_*.py with no pytest configuration",
        )
    return None


STORE_NAMES = {"prd", "prds", "requirements", "resources", "assets", "exports"}


def _detect_stores(profile: Profile) -> Proposal | None:
    """Directories that look like record stores, not documents to navigate."""
    docs_root = profile.docs_path
    if not docs_root.is_dir():
        return None
    existing = list(profile.docs_stores)
    skip = {
        profile.work_dir,
        profile.release_dir,
        f"{profile.docs_dir}/flow",
        f"{profile.docs_dir}/work",
    }
    found: list[str] = []
    for path in _walk_dirs(docs_root, depth=3):
        relative = path.relative_to(profile.root).as_posix()
        if any(relative == base or relative.startswith(base + "/") for base in skip):
            continue
        if path.name.lower() not in STORE_NAMES or (path / "README.md").is_file():
            continue
        if relative in existing:
            continue
        if sum(1 for _ in path.rglob("*") if _.is_file()) < 5:
            continue
        found.append(relative)
        if len(found) >= 3:
            break
    if not found:
        return None
    return Proposal(
        id="docs.stores",
        value=existing + found,
        source="record-like directories with no index: " + ", ".join(found),
        section="docs",
        key="stores",
        expect=existing,
    )


def _walk_dirs(root: Path, depth: int):
    if depth <= 0:
        return
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return
    for entry in entries:
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        yield entry
        yield from _walk_dirs(entry, depth - 1)


def _layout_notes(profile: Profile) -> list[str]:
    notes: list[str] = []
    if not profile.workspace:
        repos = [
            entry.name
            for entry in sorted(profile.root.iterdir())
            if entry.is_dir() and not entry.name.startswith(".") and entry.name != profile.docs_dir
            and _is_repo(entry)
        ] if profile.root.is_dir() else []
        if repos:
            notes.append(
                "more than one repository here ("
                + ", ".join(repos)
                + "); declare [workspace] and [[workspace.repo]] by hand "
                "(see references/workspace.md)"
            )
    if not profile.release_channels:
        notes.append(
            "no release channel is bound; `release` stays unavailable until "
            "[release] channels names one"
        )
    return notes


def _is_repo(path: Path) -> bool:
    """A repository of its own, not a directory inside one.

    `git rev-parse` succeeds in any subdirectory of a work tree, so asking git
    would call every `src/` a repository. A nested repository is the one with
    its own `.git` (a directory or, for a worktree, a file).
    """
    return (path / ".git").exists()


def _ci_notes(profile: Profile) -> list[str]:
    root = profile.root
    found: list[str] = []
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        found.extend(path.name for path in sorted(workflows.glob("*.y*ml")))
    for name in (".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml"):
        if (root / name).is_file():
            found.append(name)
    if not found:
        return []
    return [
        "CI entrypoints found: "
        + ", ".join(found)
        + "; l3 must be runnable locally, so wrap the CI wait as a command"
    ]


# --------------------------------------------------------------------------
# Bounded silences: show the shape, never invent the reason or the expiry.
# --------------------------------------------------------------------------


_CHECK_PATTERNS = (
    # Only checks that block S2 can be advised: an exemption silences an error,
    # and a warning does not block. Keep this list honest.
    ("link target does not exist", "links"),
    ("broken link", "links"),
    ("duplicate '##", "heading"),
)


def _exemption_advice(profile: Profile, errors: list[str] | None = None) -> list[str]:
    if errors is None:
        errors, _ = checks.check_project(profile)
    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for error in errors:
        check = next((name for marker, name in _CHECK_PATTERNS if marker in error), "")
        if not check:
            continue
        path = _error_path(error, profile)
        if not path:
            continue
        key = (check, path)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(key)
        if len(candidates) >= 5:
            break
    if not candidates:
        return []
    until = (date.today() + timedelta(days=90)).isoformat()
    blocks = [
        "these conflicts are real; fix them or record a bounded silence "
        "(edit the reason and the expiry before pasting):"
    ]
    for check, path in candidates:
        blocks.append(
            "[[exempt]]\n"
            f'check = "{check}"\n'
            f"path = {toml_literal(path)}\n"
            'reason = "TODO: why this is acceptable"\n'
            f'until = "{until}"'
        )
    return blocks


def _error_path(error: str, profile: Profile) -> str:
    head = error.split(":", 1)[0].strip()
    if "/" not in head and not head.endswith(".md"):
        return ""
    if Path(head).is_absolute() or head.startswith(".."):
        return ""
    return head


def _raw_layout_notes(raw: dict) -> list[str]:
    notes: list[str] = []
    if "workspace" in raw:
        notes.append(
            "this profile declares a workspace; check projects and repositories "
            "with `flow.py status` after the upgrade"
        )
    if "exempt" in raw:
        notes.append(
            "[[exempt]] entries are not migrated; expired ones are reported by `check`"
        )
    return notes


# --------------------------------------------------------------------------
# Apply: one atomic write, guarded by the value the plan expected.
# --------------------------------------------------------------------------


def apply(
    profile_path: Path,
    proposals: list[Proposal],
    ids: list[str],
    *,
    root: Path | None = None,
) -> list[str]:
    """Write the selected proposals. All or nothing."""
    if not ids:
        raise FlowError("--apply needs at least one proposal id (run init --plan)")
    selected: list[Proposal] = []
    known = {proposal.id: proposal for proposal in proposals}
    for proposal_id in ids:
        proposal = known.get(proposal_id)
        if proposal is None:
            raise FlowError(
                f"unknown proposal '{proposal_id}'; run init --plan to see the current ones"
            )
        if not proposal.applicable:
            raise FlowError(
                f"proposal '{proposal_id}' is not machine-appliable; paste it by hand"
            )
        selected.append(proposal)

    if root is None:
        return _apply_selected(profile_path, selected)
    with fsio.project_lock(root):
        return _apply_selected(profile_path, selected)


def _apply_selected(profile_path: Path, selected: list[Proposal]) -> list[str]:
    text = profile_path.read_text(encoding="utf-8")
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise FlowError(f"{profile_path}: invalid TOML: {exc}") from exc

    for proposal in selected:
        current = (raw.get(proposal.section) or {}).get(proposal.key, ABSENT)
        expected = proposal.expect
        if expected is ABSENT:
            if current is not ABSENT:
                raise FlowError(
                    f"{proposal.id}: profile already sets this value; run init --plan "
                    "again and edit it by hand"
                )
        elif current is ABSENT and expected in ([], ""):
            pass
        elif current != expected:
            raise FlowError(
                f"{proposal.id}: the profile changed since the plan (expected "
                f"{toml_literal(expected)}, found {toml_literal(current)}); "
                "run init --plan again"
            )
        text = set_value(text, proposal.section, proposal.key, proposal.literal)

    fsio.atomic_write_text(profile_path, text)
    return [proposal.id for proposal in selected]


def render_plan(plan: Plan) -> list[str]:
    """Proposals, their evidence, and the exact command that applies each."""
    lines: list[str] = []
    if plan.proposals:
        lines.append(f"plan: {len(plan.proposals)} proposal(s)")
        for proposal in plan.proposals:
            lines.append(f"  {proposal.id}  {proposal.literal}")
            lines.append(f"    source: {proposal.source}")
            if proposal.applicable:
                lines.append(f"    apply:  {proposal.invocation} --apply {proposal.id}")
            else:
                lines.append("    apply:  paste by hand")
    else:
        lines.append("plan: nothing to propose")
    if plan.notes:
        lines.append("notes:")
        lines.extend(f"  - {note}" for note in plan.notes)
    if plan.advice:
        lines.append("bounded:")
        for block in plan.advice:
            lines.extend(f"  {line}" for line in block.splitlines())
    return lines


def toml_literal(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(toml_literal(item) for item in value) + "]"
    if isinstance(value, tuple):
        return "[" + ", ".join(toml_literal(item) for item in value) + "]"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _value_start(line: str) -> tuple[int, str]:
    """(index after '=', trailing comment) for a `key = value` line."""
    index = line.find("=")
    if index < 0:
        return -1, ""
    rest = line[index + 1 :]
    quote = ""
    cut = len(rest)
    for position, char in enumerate(rest):
        if quote:
            if char == quote and rest[position - 1 : position] != "\\":
                quote = ""
            continue
        if char in ('"', "'"):
            quote = char
        elif char == "#":
            cut = position
            break
    comment = rest[cut:].strip()
    return index + 1, comment


def set_value(text: str, section: str, key: str, literal: str) -> str:
    """Set one key inside one section, preserving a trailing comment.

    Line-oriented on purpose: the profile is a hand-written file, and a full
    TOML round-trip would delete every comment in it. The section header and the
    key are matched literally; anything else is left byte for byte.
    """
    lines = text.splitlines(keepends=True)
    header = re.compile(r"(?m)^\[" + re.escape(section) + r"\][ \t]*(?:#.*)?$")
    start = -1
    for index, line in enumerate(lines):
        if header.match(line.rstrip("\n")):
            start = index
            break
    if start < 0:
        suffix = "" if text.endswith("\n") or not text else "\n"
        return f"{text}{suffix}\n[{section}]\n{key} = {literal}\n"

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].lstrip().startswith("["):
            end = index
            break

    key_line = re.compile(r"^\s*" + re.escape(key) + r"\s*=")
    for index in range(start + 1, end):
        if key_line.match(lines[index]):
            stop = _value_end(lines, index, end)
            _, comment = _value_start(lines[index])
            newline = "\n" if lines[stop - 1].endswith("\n") else ""
            replacement = f"{key} = {literal}"
            if comment:
                replacement += f"  # {comment.lstrip('# ').strip()}"
            lines[index:stop] = [replacement + newline]
            return "".join(lines)

    # Insert directly under the header: comments that introduce the table stay
    # attached to the keys they document. A header at EOF needs its newline
    # first, or the new key would be glued to it.
    if not lines[start].endswith("\n"):
        lines[start] += "\n"
    lines.insert(start + 1, f"{key} = {literal}\n")
    return "".join(lines)


def _value_end(lines: list[str], index: int, end: int) -> int:
    """One past the last line of a value, so multi-line arrays are replaced whole."""
    depth = 0
    quote = ""
    started = False
    for position in range(index, end):
        line = lines[position]
        segment = line
        if position == index:
            at = line.find("=")
            segment = line[at + 1 :] if at >= 0 else line
        for offset, char in enumerate(segment):
            if quote:
                if char == quote and segment[offset - 1 : offset] != "\\":
                    quote = ""
                continue
            if char in ('"', "'"):
                quote = char
            elif char in "[{":
                depth += 1
                started = True
            elif char in "]}":
                depth -= 1
                started = True
            elif char == "#":
                break
        if not started or depth <= 0:
            return position + 1
    return end
