"""Deterministic checks shared by `check`, `design-ready`, and `gate`."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from . import artifacts, docs, git, identity
from .errors import FlowError
from .profile import MODES, PRIORITIES, SIZES, TYPES, Profile

DESIGN_SECTIONS = (
    "Handoff",
    "Diagram",
    "Confirmation",
    "Approach",
    "Batches",
    "Impact",
    "Verification",
    "Rollback",
)
# Headings are a parsing contract: translate the prose, not the heading. These
# aliases exist only so the error can name the exact replacement instead of
# reporting a bare "missing '## Handoff'".
DESIGN_SECTION_ALIASES = {
    "Handoff": ("交接摘要",),
    "Diagram": ("方案图",),
    "Confirmation": ("方案确认",),
    "Approach": ("实现方案",),
    "Batches": ("实施批次",),
    "Impact": ("影响",),
    "Verification": ("怎么验",),
    "Rollback": ("怎么回滚",),
}
HANDOFF_LABELS = (
    ("Goal", "目标"),
    ("Scope", "改动范围"),
    ("Out", "不做"),
    ("Verify", "怎么验"),
    ("Rollback", "回滚"),
)
BATCH_ID_RE = re.compile(r"^B\d+$")
AC_ID_RE = re.compile(r"\bAC\d{2,3}\b")
PLACEHOLDER_WORDS = re.compile(r"\bTBD\b|待定|待补|TODO")
OPEN_DECISION_OK = {"", "none", "无", "-", "—", "n/a"}


def _handoff_errors(item: artifacts.Item) -> list[str]:
    handoff = artifacts.section(item.design_body, "Handoff", "交接摘要") or ""
    errors = []
    for english, chinese in HANDOFF_LABELS:
        pattern = rf"^\s*[-*]\s*(?:\*\*)?(?:{english}|{chinese})(?:\*\*)?\s*[:：]\s*(.*)$"
        match = re.search(pattern, handoff, re.M | re.I)
        if not match or not match.group(1).strip():
            errors.append(f"Handoff is missing '{english}' (or '{chinese}')")
    return errors


def design_errors(item: artifacts.Item, profile: Profile) -> list[str]:
    """Rules for a design that claims to be ready. Empty list means ready."""
    errors: list[str] = []
    if item.design_path is None:
        return [f"design.md is missing for {item.id}"]
    design_item = (item.design_meta.get("item") or "").strip()
    if design_item != item.id:
        errors.append(
            f"design.md frontmatter 'item' must be {item.id}, not {design_item or '(empty)'}"
        )
    if item.clarify_state not in artifacts.CLARIFIED:
        errors.append(
            "requirement is not clarified; set '- Status: clarified' in ## Clarify before designing"
        )

    found = artifacts.sections(item.design_body)
    for name in DESIGN_SECTIONS:
        if name in found:
            continue
        alias = next(
            (candidate for candidate in DESIGN_SECTION_ALIASES.get(name, ()) if candidate in found),
            "",
        )
        if alias:
            errors.append(
                f"design.md uses '## {alias}'; the parsed heading must stay '## {name}'. "
                "Translate the prose, not the heading."
            )
        else:
            errors.append(f"design.md is missing '## {name}'")

    errors.extend(_handoff_errors(item))

    diagram = artifacts.section(item.design_body, "Diagram", "方案图") or ""
    if diagram and not re.search(r"```[^\n]*\n.+?```", diagram, re.S):
        errors.append("## Diagram needs a fenced code block (ASCII or Mermaid)")

    if profile.design_require_confirmed:
        confirmation = artifacts.section(item.design_body, "Confirmation", "方案确认") or ""
        if not re.search(
            r"^\s*[-*]\s*(?:Confirmed|确认|开发人员确认)\s*[:：]\s*(yes|是|true|已确认|同意)\s*$",
            confirmation,
            re.M | re.I,
        ):
            errors.append("## Confirmation must say '- Confirmed: yes' after the human agreed")
        if not re.search(
            r"^\s*[-*]\s*(?:Date|日期|确认时间)\s*[:：]\s*\d{4}-\d{2}-\d{2}",
            confirmation,
            re.M | re.I,
        ):
            errors.append("## Confirmation must record a date (YYYY-MM-DD)")

    if PLACEHOLDER_WORDS.search(item.design_body):
        errors.append("design.md still contains TBD/TODO/待定/待补")

    if item.ac_total == 0:
        errors.append("item.md has no AC; add at least one observable acceptance criterion")
    for entry in item.ac:
        if not entry["text"] or artifacts.PLACEHOLDER_RE.search(entry["text"]):
            errors.append(f"{entry['id']} has no concrete description")

    batches = item.batches
    needed = item.size in profile.design_required_for or item.mode == "two-phase"
    if needed or batches:
        errors.extend(_batch_errors(item, batches))

    verification = artifacts.section(item.design_body, "Verification", "怎么验") or ""
    for ac_id in artifacts.ac_ids(item):
        if ac_id not in verification:
            errors.append(f"{ac_id} is not referenced in ## Verification")

    rollback = artifacts.section(item.design_body, "Rollback", "怎么回滚") or ""
    if not rollback.strip() or PLACEHOLDER_WORDS.search(rollback):
        errors.append("## Rollback must describe a real rollback (not empty, not TBD)")

    decisions = artifacts.section(item.design_body, "Open Decisions", "决策与未决")
    if decisions is not None and decisions.strip().lower() not in OPEN_DECISION_OK:
        errors.append("## Open Decisions must be empty (or 'None') before implementation")

    return errors


def _batch_errors(item: artifacts.Item, batches: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    if not batches:
        errors.append("## Batches must list every batch (B1...Bn), not only the first one")
        return errors

    ids: list[str] = []
    covered: set[str] = set()
    rows_by_id: dict[str, dict[str, str]] = {}
    for row in batches:
        batch_id = artifacts.row_value(row, "Batch", "批次").strip()
        if not BATCH_ID_RE.match(batch_id):
            errors.append(f"invalid batch id {batch_id!r}; expected B1, B2, ...")
            continue
        if batch_id in ids:
            errors.append(f"duplicate batch id {batch_id}")
            continue
        ids.append(batch_id)
        rows_by_id[batch_id] = row
        covered.update(AC_ID_RE.findall(artifacts.row_value(row, "AC", "覆盖 AC", "覆盖AC")))

    expected = [f"B{index}" for index in range(1, len(ids) + 1)]
    if ids and ids != expected:
        errors.append(
            "batches must be listed as B1..Bn in order; got "
            + ", ".join(ids)
            + f" (expected {', '.join(expected)})"
        )

    for ac_id in artifacts.ac_ids(item):
        if ac_id not in covered:
            errors.append(f"{ac_id} is not covered by any batch")

    positions = {batch_id: index for index, batch_id in enumerate(ids)}
    for batch_id in ids:
        depends = artifacts.row_value(rows_by_id[batch_id], "Depends", "依赖").strip()
        for dependency in re.split(r"[,，;；\s]+", depends):
            if not dependency or dependency in {"-", "—"}:
                continue
            if dependency == batch_id:
                errors.append(f"batch {batch_id} depends on itself")
                continue
            if dependency not in ids:
                errors.append(f"batch {batch_id} depends on unknown {dependency}")
                continue
            if positions[dependency] >= positions[batch_id]:
                errors.append(
                    f"batch {batch_id} depends on {dependency}, which is not an earlier batch; "
                    "dependencies must point backwards so the order is executable"
                )
    return errors


def item_errors(item: artifacts.Item, profile: Profile) -> list[str]:
    errors: list[str] = []
    label = item.directory.name

    for field in artifacts.ITEM_FIELDS:
        if not (item.meta.get(field) or "").strip():
            errors.append(f"{label}/item.md: missing frontmatter field '{field}'")

    if item.id and not (
        item.directory.name == item.id or item.directory.name.startswith(item.id + "-")
    ):
        errors.append(f"{label}: directory name must start with the item id {item.id}")

    if item.id and not profile.id_pattern.search(item.id):
        errors.append(
            f"{label}: id {item.id!r} does not match [id] format {profile.id_format!r}; "
            "rename the directory, then update 'id' and design.md 'item' to a current id"
        )

    if item.meta.get("type") and item.meta["type"] not in TYPES:
        errors.append(f"{label}: type {item.meta['type']!r} must be one of {', '.join(TYPES)}")
    if item.meta.get("size") and item.meta["size"] not in SIZES:
        errors.append(f"{label}: size {item.meta['size']!r} must be S, M or L")
    if item.meta.get("priority") and item.meta["priority"] not in PRIORITIES:
        errors.append(
            f"{label}: priority {item.meta['priority']!r} must be one of {', '.join(PRIORITIES)}"
        )
    if item.meta.get("mode") and item.meta["mode"] not in MODES:
        errors.append(f"{label}: mode {item.meta['mode']!r} must be one-shot or two-phase")
    created = (item.meta.get("created") or "").strip()
    if item.id and created and created.replace("-", "") not in item.id:
        errors.append(f"{label}: id {item.id} does not contain the created date {created}")
    month = artifacts.month_of(created)
    if artifacts.MONTH_RE.match(month) and item.directory.parent.name != month:
        errors.append(
            f"{label}: month directory must be {month} (from created), not "
            f"{item.directory.parent.name}; move it to <work_dir>/{month}/"
        )

    if item.ac_total == 0:
        errors.append(f"{label}: ## AC has no AC01-style entries")
    seen: set[str] = set()
    for entry in item.ac:
        if entry["id"] in seen:
            errors.append(f"{label}: duplicate {entry['id']}")
        seen.add(entry["id"])

    if not item.clarify:
        errors.append(f"{label}: ## Clarify needs '- Status: pending' or '- Status: clarified'")

    return errors


def item_warnings(item: artifacts.Item, profile: Profile) -> list[str]:
    warnings: list[str] = []
    label = item.directory.name

    slug = ""
    if item.id and item.directory.name.startswith(item.id + "-"):
        slug = item.directory.name[len(item.id) + 1:]
    if slug and artifacts.CJK_RE.search(slug) and len(slug) > artifacts.SLUG_COMFORT:
        warnings.append(
            f"{label}: slug is {len(slug)} characters; keep Chinese titles within "
            f"{artifacts.SLUG_COMFORT} (the directory name caps at {artifacts.SLUG_WIDE_MAX})"
        )

    for entry in item.ac:
        if not entry["text"]:
            warnings.append(f"{label}: {entry['id']} has no description")
        elif artifacts.PLACEHOLDER_RE.search(entry["text"]):
            warnings.append(f"{label}: {entry['id']} is still a placeholder")

    if item.size in profile.design_required_for and item.design_path is None:
        warnings.append(f"{label}: size {item.size} expects design.md before implementation")

    known_batches = {
        artifacts.row_value(row, "Batch", "批次").strip() for row in item.batches
    }
    progress_batches = {
        artifacts.row_value(row, "Batch", "批次").strip()
        for row in item.progress
        if artifacts.row_value(row, "Batch", "批次").strip()
    }
    started = any(
        artifacts.row_value(row, "Status", "状态").strip().lower()
        in {"doing", "done", "blocked", "进行中", "完成", "阻塞"}
        for row in item.progress
    )
    if item.design_path is not None and started:
        for batch_id in sorted(known_batches):
            if batch_id and batch_id not in progress_batches:
                warnings.append(
                    f"{label}: design defines {batch_id} but ## Implementation has no "
                    "row; add it so a resume can tell 'not started' from 'lost'"
                )
    for row in item.progress:
        batch_id = artifacts.row_value(row, "Batch", "批次").strip()
        state = artifacts.row_value(row, "Status", "状态").strip().lower()
        if (
            item.design_path is not None
            and batch_id
            and batch_id not in {"-", "—"}
            and batch_id not in known_batches
        ):
            warnings.append(f"{label}: progress mentions {batch_id} which design.md does not define")
        if state and state not in {"pending", "doing", "done", "blocked", "待开始", "进行中", "完成", "阻塞"}:
            warnings.append(f"{label}: progress state {state!r} is not a known state")

    if item.status == "done" and item.ac_done != item.ac_total:
        warnings.append(
            f"{label}: closed but AC is {item.ac_done}/{item.ac_total}"
        )
    return warnings


def _row_value_loose(row: dict[str, str], needles: tuple[str, ...]) -> str:
    for key, value in row.items():
        lowered = key.strip().lower()
        if any(needle.lower() in lowered for needle in needles):
            return value.strip()
    return ""


def _empty_evidence(value: str) -> bool:
    """A cell is empty when it has no content or only a TODO-style placeholder.

    Angle brackets are not placeholders by themselves: real commands contain
    `<skill>`, test output contains `<nil>`/`<br>`, and rejecting those turned
    valid evidence into a false negative. The template's command cell is empty,
    so it is still caught.
    """
    return not value or bool(PLACEHOLDER_WORDS.search(value))


def evidence_problems(
    item: artifacts.Item, strict: bool = False
) -> tuple[list[str], list[str]]:
    """Validate `test-report.md`: one evidence row per AC, with a command and output.

    `strict` is the difference between iterating and closing. While a batch is in
    flight a partial report is a warning; `done` refuses it. The verdict is the
    other half: a report that says FAIL is evidence that the item is not done.
    """
    path = item.directory / "test-report.md"
    if not path.is_file():
        return [], []
    label = f"{item.directory.name}/test-report.md"
    errors: list[str] = []
    warnings: list[str] = []

    def emit(message: str) -> None:
        (errors if strict else warnings).append(message)

    meta, body = artifacts.parse_frontmatter(artifacts.read_text(path))
    report_item = (meta.get("item") or "").strip()
    if report_item and report_item != item.id:
        errors.append(f"{label}: frontmatter 'item' must be {item.id}")

    result = artifacts.section(body, "Result", "结论")
    if result is None:
        emit(f"{label}: missing '## Result'")
    else:
        match = re.search(
            r"^\s*[-*]\s*(?:Verdict|结论)\s*[:：]\s*(.+?)\s*$", result, re.M | re.I
        )
        verdict = match.group(1).strip() if match else ""
        if not verdict:
            emit(f"{label}: '## Result' needs '- Verdict: PASS'")
        elif verdict.upper() != "PASS":
            emit(f"{label}: verdict is {verdict!r}; a passing report is required to close")

    evidence = artifacts.section(body, "Evidence", "证据")
    if evidence is None:
        emit(f"{label}: missing '## Evidence'")
        return errors, warnings

    known = set(artifacts.ac_ids(item))
    covered: set[str] = set()
    for row in artifacts.parse_tables(body, "Evidence", "证据"):
        ac_id = artifacts.row_value(row, "AC", "验收项").strip()
        if not ac_id or ac_id in {"AC", "-", "—"}:
            continue
        command = artifacts.row_value(row, "Command", "命令")
        output = _row_value_loose(
            row, ("output", "artefact", "artifact", "evidence", "输出", "证据")
        )
        if ac_id not in known:
            warnings.append(f"{label}: evidence for {ac_id}, which item.md does not define")
            continue
        covered.add(ac_id)
        for field, value in (("Command", command), ("Output", output)):
            if _empty_evidence(value):
                emit(f"{label}: {ac_id} has no {field} evidence")

    for ac_id in artifacts.ac_ids(item):
        if ac_id not in covered:
            emit(f"{label}: {ac_id} has no evidence row")
    return errors, warnings


def owner_warnings(profile: Profile, items: list[artifacts.Item]) -> list[str]:
    """One spelling per person, and every owner on the roster when one is set.

    A person on several machines resolves their own identity on each one; a
    spelling drift there is exactly how `status --mine` starts missing items.
    """
    warnings: list[str] = []
    spellings: dict[str, set[str]] = {}
    for item in items:
        owner = (item.meta.get("owner") or "").strip()
        if owner:
            spellings.setdefault(identity.normalize(owner), set()).add(owner)
    for variants in spellings.values():
        if len(variants) > 1:
            listed = " / ".join(sorted(variants))
            warnings.append(
                f"owners {listed} differ only by case or spacing; use one spelling "
                "on every machine so `status --mine` sees one person"
            )

    if profile.owners:
        allowed = {identity.normalize(owner) for owner in profile.owners}
        reported: set[str] = set()
        for item in items:
            owner = (item.meta.get("owner") or "").strip()
            if not owner or owner in reported or identity.normalize(owner) in allowed:
                continue
            reported.add(owner)
            warnings.append(
                f"{item.directory.name}: owner {owner!r} is not in [project] owners "
                f"({', '.join(profile.owners)}); add them there or fix the spelling"
            )
    return warnings


def _path_matches(path: str, prefixes: list[str]) -> bool:
    """True when `path` is one of `prefixes` or lives under one.

    The separator matters: a prefix is a directory, not a string. Without the
    boundary `lite-backend` silently covers `lite-backend-tools/`, which is a
    different repository and a different risk decision.
    """
    for prefix in prefixes:
        clean = prefix.rstrip("/")
        if path == clean or path.startswith(clean + "/"):
            return True
    return False


def paths_matching(paths: list[str], prefixes: list[str]) -> list[str]:
    """Paths under a configured prefix set, deduplicated and sorted."""
    if not prefixes:
        return []
    return sorted({path for path in paths if _path_matches(path, prefixes)})


def risk_paths_touched(profile: Profile, paths: list[str]) -> list[str]:
    """Structural paths in a set of changed files, minus the documented exemptions."""
    if not profile.design_risk_paths or not paths:
        return []
    return sorted(
        {
            path
            for path in paths
            if _path_matches(path, profile.design_risk_paths)
            and not _path_matches(path, profile.design_risk_exempt)
        }
    )


@dataclass
class ChangeSet:
    """The item's changed paths, split by where they were found.

    Uncommitted work is real work — the change being gated is often exactly
    what sits in the worktree — but a long-lived clone also carries dirty files
    that belong to nobody's item. Keeping the two sources apart lets a risk or
    fallback warning say which one it saw, so the reader can tell "this is my
    change" from "this was already dirty".

    In a workspace every path is prefixed with its repository, so one report and
    one risk list describe the whole change. A repository that is missing or
    unreadable is reported instead of being treated as an empty change: silence
    there would turn "no risk path touched" into a lie.
    """

    worktree: list[str] = field(default_factory=list)
    committed: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    incomplete: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.worktree = list(dict.fromkeys(self.worktree))
        self.committed = list(dict.fromkeys(self.committed))

    @property
    def paths(self) -> list[str]:
        return list(dict.fromkeys([*self.worktree, *self.committed]))

    @property
    def degraded(self) -> list[str]:
        """Warnings for what could not be inspected, phrased as what to fix."""
        messages: list[str] = []
        if self.unavailable:
            messages.append(
                "not a git work tree, so its changes are invisible here: "
                + ", ".join(self.unavailable)
                + " (fetch the checkout, or declare [[workspace.repo]] only for "
                "repositories every machine has)"
            )
        for entry in self.incomplete:
            messages.append(f"could not read git history for {entry}")
        return messages

    def label(self, path: str) -> str:
        in_worktree = path in self.worktree
        in_committed = path in self.committed
        if in_worktree and in_committed:
            return "worktree + committed"
        return "worktree" if in_worktree else "committed"

    def describe(self, paths: list[str]) -> str:
        """`db/schema.sql (worktree), deps.txt (committed)`, capped at three."""
        listed = ", ".join(f"{path} ({self.label(path)})" for path in paths[:3])
        if len(paths) > 3:
            listed += f" (+{len(paths) - 3} more)"
        return listed


def risk_gate(
    item: artifacts.Item, profile: Profile, changed: ChangeSet
) -> tuple[list[str], list[str]]:
    """Paths that demand a design, and the exemption that keeps docs from tripping it.

    `risk_paths` are structural: contracts, schema, permissions, deploy scripts.
    `risk_exempt` is the escape hatch that makes the rule usable — a work item
    whose only change is prose about a risk path must not require a design.
    Each hit names where it came from, so an unrelated dirty file is not
    mistaken for this item's change.
    """
    if not profile.design_risk_paths or not changed.paths:
        return [], []
    touched = risk_paths_touched(profile, changed.paths)
    if not touched or item.design_status == "ready":
        return [], []
    message = (
        f"{item.id} changes a risk path without a ready design: {changed.describe(touched)}; "
        "write design.md and run flow.py design-ready <ID>, or narrow the change"
    )
    if profile.design_risk_gate == "block":
        return [message], []
    return [], [message]


def _has_history(root) -> bool:
    """A repository with no commit yet has no history to search, not an error."""
    try:
        return bool(git.head(root))
    except git.GitError:
        return False


def changed_paths(profile: Profile, item: artifacts.Item) -> ChangeSet:
    """The item's work: uncommitted paths plus paths in its own commits.

    Commits are found by grepping the whole history for the item id, with no
    fixed window: a window silently drops the first commits of a long item and
    reports "no risk path" for a change that touched one. The worktree
    participates because the change under the gate is often not committed yet;
    the label keeps that provenance visible.

    Every declared repository is visited, and its paths are prefixed with the
    repository so a single risk list covers the whole workspace.
    """
    changed = ChangeSet()
    for repo in profile.workspace_repos:
        repo_root = profile.repo_root(repo.path)
        try:
            if not git.is_repo(repo_root):
                changed.unavailable.append(repo.name)
                continue
            changed.worktree.extend(
                profile.to_workspace(repo.path, path)
                for path in git.worktree_paths(repo_root)
            )
            if item is not None and item.id and _has_history(repo_root):
                owned = git.commits_matching(repo_root, item.id)
                changed.committed.extend(
                    profile.to_workspace(repo.path, path)
                    for path in git.files_many(repo_root, [c.sha for c in owned])
                )
        except git.GitError as exc:
            changed.incomplete.append(f"{repo.name}: {exc}")
    return changed


BATCH_REPO_COLUMNS = ("Repo", "仓库")
REPO_ONLY = {"-", "—", ""}


def design_repos(item: artifacts.Item) -> list[str]:
    """Repositories named by the design's batch table.

    The column has always been in the template and in the handoff prompt; the
    gate now reads it, which is how a change that has no commit yet still names
    where it lands. `.` means the control repository, the pre-workspace default.
    """
    found: list[str] = []
    for row in item.batches:
        value = artifacts.row_value(row, *BATCH_REPO_COLUMNS).strip()
        for entry in re.split(r"[,，;；\s]+", value):
            entry = entry.strip().strip("`")
            if entry in REPO_ONLY:
                continue
            entry = "" if entry == "." else entry.rstrip("/")
            if entry not in found:
                found.append(entry)
    return found


@dataclass
class Scope:
    """Which repositories a gate run covers, and why."""

    repos: list[str]
    reason: str
    warnings: list[str] = field(default_factory=list)


def scope(
    profile: Profile, item: artifacts.Item | None, explicit: list[str] | None = None
) -> Scope:
    """Decide which repositories a gate run inspects.

    Order: an explicit `--repo`, the repositories whose history mentions the
    item, the repositories with uncommitted work, the design's Repo column, and
    finally every repository with a warning. The last step is the important one:
    a workspace gate must never narrow silently.
    """
    declared = {repo.path for repo in profile.workspace_repos}
    labels = {repo.path: repo.name for repo in profile.workspace_repos}
    explicit = [entry for entry in (explicit or []) if entry is not None]
    if explicit:
        wanted: list[str] = []
        for entry in explicit:
            clean = entry.strip().rstrip("/")
            if clean in (".", "./", ""):
                clean = profile.control_path
            if clean not in declared:
                raise FlowError(
                    f"--repo {entry!r} is not a declared repository; known: "
                    + ", ".join(sorted(repo.name for repo in profile.workspace_repos))
                )
            if clean not in wanted:
                wanted.append(clean)
        return Scope(repos=wanted, reason="--repo")

    everything = [repo.path for repo in profile.workspace_repos]
    if item is None:
        return Scope(repos=everything, reason="project-wide")

    warnings: list[str] = []
    found: list[str] = []
    reason = ""
    for repo in profile.workspace_repos:
        repo_root = profile.repo_root(repo.path)
        try:
            if not git.is_repo(repo_root):
                continue
            if git.commits_matching(repo_root, item.id):
                found.append(repo.path)
        except git.GitError:
            continue
    if found:
        reason = "commits"
    if not found:
        for repo in profile.workspace_repos:
            repo_root = profile.repo_root(repo.path)
            try:
                if git.is_repo(repo_root) and git.worktree_paths(repo_root):
                    found.append(repo.path)
            except git.GitError:
                continue
        if found:
            reason = "worktree"
    if not found:
        named = design_repos(item)
        for entry in named:
            if entry in declared:
                if entry not in found:
                    found.append(entry)
            else:
                warnings.append(
                    f"design.md names repo {entry!r}, which is not a declared "
                    "repository; add [[workspace.repo]] for it or fix the batch table"
                )
        reason = "design Repo column" if found else ""
    if not found:
        if len(everything) > 1:
            warnings.append(
                f"cannot tell which repositories {item.id} touches; running every "
                "declared repository ("
                + ", ".join(labels[path] for path in everything)
                + "). Pass --repo or fill the design's Repo column"
            )
        return Scope(repos=everything, reason="all", warnings=warnings)
    return Scope(repos=found, reason=reason, warnings=warnings)


def fallback_warnings(profile: Profile, level: str, changed: ChangeSet) -> list[str]:
    """A cheap level does not cover a dependency-file change; say so.

    This is the contract behind l1: it is fast because it is scoped, and a
    change that invalidates the scope has to fall back to the full level. The
    hit names whether it is committed or still in the worktree.
    """
    if not profile.gate_fallback_paths or not changed.paths:
        return []
    full = profile.full_level
    if full is None or level == full:
        return []
    hits = sorted(
        {path for path in changed.paths if _path_matches(path, profile.gate_fallback_paths)}
    )
    if not hits:
        return []
    return [
        f"changed {changed.describe(hits)} invalidates {level}; "
        f"run gate --level {full} before committing"
    ]


def full_level_warning(profile: Profile) -> str | None:
    """Name the level `done` will close on when it is not l3.

    `full_level` is the strictest level the profile defines, which is what the
    gate records and what `done` requires — not necessarily what the project
    believes it requires. Saying it out loud separates a deliberate choice from
    a profile that quietly lost its strictest level, and it is a warning: the
    refusal conditions do not change.
    """
    full = profile.full_level
    if full is None or full == "l3":
        return None
    try:
        relative = profile.path.relative_to(profile.root)
    except ValueError:
        relative = profile.path
    return (
        f"the strictest gate is {full}; done will close on {full} — "
        f"add [gate] l3 to {relative} (with at least one command) if that is not intended"
    )


def quotepath_warnings(profile: Profile, items: list[artifacts.Item]) -> list[str]:
    """Non-ASCII slugs read as escapes until `core.quotepath` is off."""
    if not any(artifacts.CJK_RE.search(item.directory.name) for item in items):
        return []
    try:
        if not git.is_repo(profile.control_root):
            return []
        if git.config_get(profile.control_root, "core.quotepath").strip().lower() == "false":
            return []
    except git.GitError:
        return []
    return [
        "work item directories contain non-ASCII characters; run "
        "`git config core.quotepath false` so `git status` prints them readably"
    ]


def layout_problems(profile: Profile) -> tuple[list[str], list[str]]:
    """Validate the <work_dir>/<YYYY-MM>/<id>-<slug> layout.

    A misnamed bucket is an error, not a skip: a tool that only reads month
    buckets would otherwise lose every item filed under it.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not profile.work_path.is_dir():
        return errors, warnings
    for bucket in sorted(profile.work_path.iterdir()):
        if not bucket.is_dir():
            continue
        if bucket.name == artifacts.ARCHIVE_DIR:
            for month in sorted(bucket.iterdir()):
                if not month.is_dir() or month.name == "README.md":
                    continue
                if not artifacts.MONTH_RE.match(month.name):
                    warnings.append(
                        f"{artifacts.ARCHIVE_DIR}/{month.name}: archived items keep their "
                        "month bucket; move it into a YYYY-MM directory or restore it"
                    )
            continue
        if not artifacts.MONTH_RE.match(bucket.name):
            errors.append(
                f"{bucket.name}: items live in <work_dir>/<YYYY-MM>/<id>-<slug>; "
                "move it into a YYYY-MM directory named after the item's created month"
            )
            continue
        for entry in sorted(bucket.iterdir()):
            if entry.is_dir() and not (entry / "item.md").is_file():
                warnings.append(
                    f"{bucket.name}/{entry.name}: no item.md; remove it or restore the file"
                )
    return errors, warnings


def check_project(
    profile: Profile, work: str | None = None
) -> tuple[list[str], list[str]]:
    """Validate the project, or only one item when `work` is given.

    `gate --work` must not fail because a teammate's unrelated item is broken;
    the release path and a bare `check` still validate everything.
    """
    errors: list[str] = []
    warnings: list[str] = []

    for relative in profile.required_docs:
        if not (profile.root / relative).exists():
            errors.append(f"missing required document: {relative}")

    if work is None:
        layout_errors, layout_warnings = layout_problems(profile)
        errors.extend(layout_errors)
        warnings.extend(layout_warnings)
        doc_errors, doc_warnings = docs.problems(profile)
        errors.extend(doc_errors)
        warnings.extend(doc_warnings)

    items = artifacts.all_items(profile)
    if work is None:
        warnings.extend(owner_warnings(profile, items))
        warnings.extend(quotepath_warnings(profile, items))
    by_id: dict[str, list[str]] = {}
    for item in items:
        if item.id:
            by_id.setdefault(item.id, []).append(item.directory.name)
    duplicates = {
        item_id: names for item_id, names in by_id.items() if len(names) > 1
    }
    reported_duplicates: set[str] = set()

    scoped = [artifacts.find_item(profile, work)] if work else items
    for item in scoped:
        if item.id in duplicates and item.id not in reported_duplicates:
            reported_duplicates.add(item.id)
            errors.append(
                f"duplicate item id {item.id} in {', '.join(duplicates[item.id])}"
            )

        errors.extend(item_errors(item, profile))
        warnings.extend(item_warnings(item, profile))

        evidence_errors, evidence_warnings = evidence_problems(item)
        errors.extend(evidence_errors)
        warnings.extend(evidence_warnings)
        if item.status == "done" and not (item.directory / "test-report.md").is_file():
            warnings.append(
                f"{item.directory.name}: closed without a test-report; "
                "the AC tick is a claim, not evidence"
            )

        if item.design_path is not None:
            design_item = (item.design_meta.get("item") or "").strip()
            if design_item != item.id:
                errors.append(
                    f"{item.directory.name}/design.md: frontmatter 'item' must be {item.id}"
                )
            if item.clarify_state not in artifacts.CLARIFIED:
                errors.append(
                    f"{item.directory.name}: design.md exists but the requirement is not clarified"
                )
            if item.design_status == "ready":
                for error in design_errors(item, profile):
                    errors.append(f"{item.directory.name}/design.md: {error}")

        for path, text in ((item.path, artifacts.read_text(item.path)),):
            for target in artifacts.relative_links(path, text):
                if not (path.parent / target).exists():
                    errors.append(f"{path.relative_to(profile.root)}: broken link {target}")
        prd = (item.meta.get("prd") or "").strip()
        if prd and not (profile.root / prd).exists():
            errors.append(
                f"{item.directory.name}/item.md: prd {prd!r} does not exist; point at "
                "the requirement's real path or remove the field"
            )
        if item.design_path is not None:
            for target in artifacts.relative_links(
                item.design_path, artifacts.read_text(item.design_path)
            ):
                if not (item.design_path.parent / target).exists():
                    errors.append(
                        f"{item.design_path.relative_to(profile.root)}: broken link {target}"
                    )

    return errors, warnings


def today() -> str:
    return date.today().isoformat()
