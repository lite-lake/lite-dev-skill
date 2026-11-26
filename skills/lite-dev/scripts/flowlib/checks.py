"""Deterministic checks shared by `check`, `design-ready`, and `gate`."""
from __future__ import annotations

import re
from datetime import date

from . import artifacts, git, identity
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
    if item.clarify_state not in artifacts.CLARIFIED:
        errors.append(
            "requirement is not clarified; set '- Status: clarified' in ## Clarify before designing"
        )

    found = artifacts.sections(item.design_body)
    for name in DESIGN_SECTIONS:
        if name not in found:
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
    for row in batches:
        batch_id = artifacts.row_value(row, "Batch", "批次").strip()
        if not BATCH_ID_RE.match(batch_id):
            errors.append(f"invalid batch id {batch_id!r}; expected B1, B2, ...")
            continue
        if batch_id in ids:
            errors.append(f"duplicate batch id {batch_id}")
        ids.append(batch_id)
        covered.update(AC_ID_RE.findall(artifacts.row_value(row, "AC", "覆盖 AC", "覆盖AC")))

    for ac_id in artifacts.ac_ids(item):
        if ac_id not in covered:
            errors.append(f"{ac_id} is not covered by any batch")

    for row in batches:
        depends = artifacts.row_value(row, "Depends", "依赖").strip()
        for dependency in re.split(r"[,，;；\s]+", depends):
            if not dependency or dependency in {"-", "—"}:
                continue
            if dependency not in ids:
                errors.append(
                    f"batch {artifacts.row_value(row, 'Batch', '批次')} depends on unknown {dependency}"
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
    for row in item.progress:
        batch_id = artifacts.row_value(row, "Batch", "批次").strip()
        state = artifacts.row_value(row, "Status", "状态").strip().lower()
        if batch_id and batch_id not in {"-", "—"} and batch_id not in known_batches:
            warnings.append(f"{label}: progress mentions {batch_id} which design.md does not define")
        if state and state not in {"pending", "doing", "done", "blocked", "待开始", "进行中", "完成", "阻塞"}:
            warnings.append(f"{label}: progress state {state!r} is not a known state")

    if (item.meta.get("closed") or "").strip() and item.ac_done != item.ac_total:
        warnings.append(
            f"{label}: closed but AC is {item.ac_done}/{item.ac_total}"
        )
    return warnings


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


def quotepath_warnings(profile: Profile, items: list[artifacts.Item]) -> list[str]:
    """Non-ASCII slugs read as escapes until `core.quotepath` is off."""
    if not any(artifacts.CJK_RE.search(item.directory.name) for item in items):
        return []
    try:
        if not git.is_repo(profile.root):
            return []
        if git.config_get(profile.root, "core.quotepath").strip().lower() == "false":
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

    items = artifacts.all_items(profile)
    if work is None:
        warnings.extend(owner_warnings(profile, items))
        warnings.extend(quotepath_warnings(profile, items))
    by_id: dict[str, list[str]] = {}
    for item in items:
        if item.id:
            by_id.setdefault(item.id, []).append(item.directory.name)

    scoped = [artifacts.find_item(profile, work)] if work else items
    for item in scoped:
        others = [name for name in by_id.get(item.id, []) if name != item.directory.name]
        if others:
            errors.append(
                f"duplicate item id {item.id} in {item.directory.name} and {', '.join(others)}"
            )

        errors.extend(item_errors(item, profile))
        warnings.extend(item_warnings(item, profile))

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
