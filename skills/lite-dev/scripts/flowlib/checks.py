"""Deterministic checks shared by `check`, `design-ready`, and `gate`."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import artifacts
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
    if item.id and not item.id.startswith(item.meta.get("created", "").replace("-", "")):
        if item.meta.get("created"):
            errors.append(f"{label}: id {item.id} does not start with created date")

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


def check_project(profile: Profile) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for relative in profile.required_docs:
        if not (profile.root / relative).exists():
            errors.append(f"missing required document: {relative}")

    items = artifacts.all_items(profile)
    ids: dict[str, Path] = {}
    for item in items:
        if item.id:
            if item.id in ids:
                errors.append(f"duplicate item id {item.id} in {item.directory.name} and {ids[item.id].name}")
            ids[item.id] = item.directory

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
