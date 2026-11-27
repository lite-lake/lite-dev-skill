"""Assemble a cold-start prompt from the artifacts.

The prompt is data, not prose: id, paths, the batch table, the progress ledger,
the gate command. Prose that must be written is instruction, and it is written
in the project's language.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from . import artifacts, checks
from .errors import FlowError
from .profile import Profile

FLOW = Path(__file__).resolve().parents[1] / "flow.py"
DONE_STATES = {"done", "完成", "closed"}
DOING_STATES = {"doing", "进行中", "in-progress"}
BLOCKED_STATES = {"blocked", "阻塞"}

INSTRUCTIONS = {
    "en": {
        "continue": "Continue work item {id} in this repository.",
        "read": "Read these first, in this order:",
        "handoff": "Handoff (copied from the design, do not re-derive):",
        "batches": "Batches: {summary}",
        "next": "Next: {batch} — {goal}",
        "next_only": "Next: {batch}",
        "next_none": "Next: every batch is done; run the final gate, then close the item.",
        "blocked": "blocked",
        "resume": "Resume {batch} (in progress): {goal}",
        "blocked_next": "Next: {batch} — {goal} (BLOCKED; resolve it before dispatching)",
        "design_no_batches": "design.md has no ## Batches table",
        "rules": "Rules:",
        "rule_no_redesign": "- Do not redesign; the plan is confirmed{when}.",
        "rule_unconfirmed": "- design.md is not ready or not confirmed: return to Phase A and run design-ready.",
        "rule_batches": "- Dispatch every unfinished batch in order. A finished batch is not a stop condition.",
        "rule_accept": "- An AC is accepted black-box once, in the first batch that names it. A later batch runs regression only.",
        "rule_parallel": "- Batches in one parallel group with disjoint repositories may be dispatched together; one repository is always serial.",
        "rule_commit": "- Only the commit role commits. Update `## Implementation` after each batch.",
        "rule_stop": "- Stop on the conditions in SKILL.md section 9, then update progress first.",
        "gate": "Gate: {command}",
        "commit_gate": "Commit gate: {command}",
        "warnings": "Warnings:",
        "batch_intro": "You are the implement role for work item {id}, batch {batch}.",
        "batch_row": "Batch {batch}: {goal}; repo {repo}; covers {ac}; depends on {depends}.",
        "batch_parallel": "Parallel group {group}: this batch may be dispatched together with the other members; they change the other repositories.",
        "batch_accept": "Acceptance for this batch: {accept}.",
        "batch_regression": "Also covered here, already accepted in {batch}: {ac}. Run regression only; do not accept it twice.",
        "batch_rules": "Rules:",
        "batch_rule_scope": "- Do only this batch. Do not start the next one, do not refactor along the way.",
        "batch_rule_commit": "- Do not commit, do not push, do not edit design.md, do not relax tests.",
        "batch_rule_gap": "- A gap in scope, a contract, the data model, or a security semantic is a stop: report it instead of inventing one. An implementation detail takes `## Decision Defaults` and is recorded as a deviation.",
        "batch_return": "Return at most 30 lines: what changed, gate result, deviations, open questions.",
        "done": "done",
        "doing": "doing",
        "pending": "pending",
        "no_design": "no design.md yet",
        "rule_no_design": "- No design.md yet: for a two-phase item write the design and run design-ready; for one-shot, implement after clarifying.",
        "rule_unclarified": "- The requirement is not clarified: set '- Status: clarified' in item.md first.",
    },
    "zh": {
        "continue": "继续本仓库的工作项 {id}。",
        "read": "先读这些，按顺序：",
        "handoff": "交接摘要（从 design.md 原样复制，不要重新推导）：",
        "batches": "批次：{summary}",
        "next": "下一步：{batch} — {goal}",
        "next_only": "下一步：{batch}",
        "next_none": "下一步：全部批次已完成；跑最终门禁，然后收尾。",
        "blocked": "阻塞",
        "resume": "继续 {batch}（进行中）：{goal}",
        "blocked_next": "下一步：{batch} — {goal}（阻塞中；先解决再派发）",
        "design_no_batches": "design.md 没有 ## Batches 表",
        "rules": "规则：",
        "rule_no_redesign": "- 不要重新设计；方案已于{when}确认。",
        "rule_unconfirmed": "- design.md 尚未 ready 或未确认：回到 Phase A，跑 design-ready。",
        "rule_batches": "- 按顺序派发每一个未完成批次。完成一个批次不是停止条件。",
        "rule_accept": "- 每条 AC 只在第一个列出它的批次做一次黑盒验收；后续批次只跑回归。",
        "rule_parallel": "- 同一并行组且仓库互不相交的批次可一次派发；同一个仓库一律串行。",
        "rule_commit": "- 只有提交角色提交。每批完成后更新 `## Implementation`。",
        "rule_stop": "- 触发 SKILL.md 第 9 节的停止条件就停下，并先更新进度。",
        "gate": "门禁：{command}",
        "commit_gate": "提交门禁：{command}",
        "warnings": "警告：",
        "batch_intro": "你是工作项 {id} 批次 {batch} 的 implement 角色。",
        "batch_row": "批次 {batch}：{goal}；仓库 {repo}；覆盖 {ac}；依赖 {depends}。",
        "batch_parallel": "并行组 {group}：本批可与同组其他批次一起派发；它们改的是别的仓库。",
        "batch_accept": "本批验收：{accept}。",
        "batch_regression": "同批覆盖、但已在 {batch} 验收：{ac}。只跑回归，不重复验收。",
        "batch_rules": "规则：",
        "batch_rule_scope": "- 只做本批。不提前做下一批，不顺手重构。",
        "batch_rule_commit": "- 不 commit、不 push、不改 design.md、不降低测试标准。",
        "batch_rule_gap": "- 范围、契约、数据模型或安全语义的缺口就停：报告缺口，不自行发明。实现细节按 `## Decision Defaults` 取最小解并记为偏差。",
        "batch_return": "返回不超过 30 行：改了什么、门禁结果、偏差、待决问题。",
        "done": "完成",
        "doing": "进行中",
        "pending": "待开始",
        "no_design": "还没有 design.md",
        "rule_no_design": "- 还没有 design.md：两阶段工作项先写设计并跑 design-ready；单批工作项澄清后直接实现。",
        "rule_unclarified": "- 需求尚未澄清：先在 item.md 写 `- Status: clarified`。",
    },
}


def _text(profile: Profile) -> dict[str, str]:
    return INSTRUCTIONS.get(profile.language, INSTRUCTIONS["en"])


def _relative(profile: Profile, path: Path) -> str:
    try:
        return str(path.relative_to(profile.root))
    except ValueError:
        return str(path)


def batch_state(item: artifacts.Item, batch_id: str) -> str:
    for row in item.progress:
        if artifacts.row_value(row, "Batch", "批次").strip() != batch_id:
            continue
        state = artifacts.row_value(row, "Status", "状态").strip().lower()
        if state in DONE_STATES:
            return "done"
        if state in DOING_STATES:
            return "doing"
        if state in BLOCKED_STATES:
            return "blocked"
        return "pending"
    return "pending"


def batch_ids(item: artifacts.Item) -> list[str]:
    return [
        artifacts.row_value(row, "Batch", "批次").strip()
        for row in item.batches
        if artifacts.row_value(row, "Batch", "批次").strip()
    ]


def next_batch(item: artifacts.Item) -> str | None:
    for batch_id in batch_ids(item):
        if batch_state(item, batch_id) != "done":
            return batch_id
    return None


def _has_parallel_group(item: artifacts.Item) -> bool:
    return any(
        artifacts.row_value(row, "Parallel", "并行组").strip() not in {"", "-", "—"}
        for row in item.batches
    )


def _row(item: artifacts.Item, batch_id: str) -> dict[str, str]:
    for row in item.batches:
        if artifacts.row_value(row, "Batch", "批次").strip() == batch_id:
            return row
    raise FlowError(
        f"{item.id} has no batch {batch_id}; defined: {', '.join(batch_ids(item)) or 'none'}"
    )


def _field(row: dict[str, str], *names: str, default: str = "-") -> str:
    value = artifacts.row_value(row, *names).strip()
    return value if value and value not in {"—", "-"} else default


def render(profile: Profile, item: artifacts.Item, batch: str | None = None) -> str:
    words = _text(profile)
    command = shlex.quote(str(FLOW))
    gate = f"python3 {command} gate --level l1 --work {item.id}"
    lines: list[str] = []

    if batch:
        if item.design_path is None:
            raise FlowError(
                f"{item.id} has no design.md; drop --batch and hand off the item instead"
            )
        if item.design_status != "ready":
            raise FlowError(
                f"{item.id} design is not ready (status: {item.design_status or 'draft'}); "
                "finish the design and run design-ready before dispatching a batch"
            )
        problems = checks.design_errors(item, profile)
        if problems:
            raise FlowError(
                f"{item.id} design.md is marked ready but invalid: {problems[0]}; "
                "run check for the full list"
            )
        state = batch_state(item, batch)
        if state == "done":
            nxt = next_batch(item)
            raise FlowError(
                f"batch {batch} is already done; continue with {nxt or 'the final gate'}"
            )
        if state == "blocked":
            raise FlowError(
                f"batch {batch} is blocked; resolve the blocker before dispatching it"
            )
        row = _row(item, batch)
        depends = artifacts.row_value(row, "Depends", "依赖").strip()
        for dependency in re.split(r"[,，;；\s]+", depends):
            if not dependency or dependency in {"-", "—"}:
                continue
            if batch_state(item, dependency) != "done":
                raise FlowError(
                    f"batch {batch} depends on {dependency}, which is not done; "
                    "finish it before dispatching this batch"
                )
        lines.append(
            words["batch_intro"].format(id=item.id, batch=batch) + f"  ({item.meta.get('title', '')})"
        )
        lines.append("")
        lines.append(words["read"])
        if item.design_path is not None:
            lines.append(f"1. {_relative(profile, item.design_path)}")
        lines.append(f"2. {_relative(profile, item.path)}")
        lines.append("")
        lines.append(
            words["batch_row"].format(
                batch=batch,
                goal=_field(row, "Goal", "目标", "目标/动作"),
                repo=_field(row, "Repo", "仓库"),
                ac=_field(row, "AC", "覆盖 AC", "覆盖AC"),
                depends=_field(row, "Depends", "依赖"),
            )
        )
        group = _field(row, "Parallel", "并行组", default="")
        if group:
            lines.append(words["batch_parallel"].format(group=group))
        # Which ACs this batch accepts is derived from the batch table, so a
        # verifier is never asked to accept the same outcome twice.
        covers = checks.AC_ID_RE.findall(artifacts.row_value(row, "AC", "覆盖 AC", "覆盖AC"))
        accepting = checks.acceptance_batches(item)
        accept = sorted(ac_id for ac_id in covers if accepting.get(ac_id) == batch)
        if accept:
            lines.append(words["batch_accept"].format(accept=", ".join(accept)))
        for ac_id in sorted(covers):
            owner = accepting.get(ac_id)
            if owner and owner != batch:
                lines.append(words["batch_regression"].format(batch=owner, ac=ac_id))
        # A batch that names a repository gets a gate command for that repository:
        # the implement role should not have to rediscover the scope, and `l1`
        # stays cheap when the batch is one repository of several.
        batch_repo = _field(row, "Repo", "仓库", default="")
        if batch_repo not in {"", "-", "—", "."}:
            gate = f"{gate} --repo {shlex.quote(batch_repo)}"
        lines.append("")
        lines.append(words["batch_rules"])
        for key in ("batch_rule_scope", "batch_rule_commit", "batch_rule_gap"):
            lines.append(words[key])
        lines.append("")
        lines.append(words["gate"].format(command=gate))
        lines.append("")
        lines.append(words["batch_return"])
        return "\n".join(lines)

    lines.append(words["continue"].format(id=item.id) + f"  ({item.meta.get('title', '')})")
    mode = ", ".join(
        part for part in (item.meta.get("size", ""), item.meta.get("mode", "")) if part
    )
    if mode:
        lines.append(f"mode: {mode}  status: {item.status}")
    lines.append("")
    lines.append(words["read"])
    lines.append(f"1. {_relative(profile, item.path)}")
    if item.design_path is not None:
        lines.append(f"2. {_relative(profile, item.design_path)}")
    for label, key in (("PRD", "prd"), ("Board", "board")):
        value = (item.meta.get(key) or "").strip()
        if value:
            lines.append(f"- {label}: {value}")
    lines.append("")

    handoff = artifacts.section(item.design_body, "Handoff", "交接摘要")
    if handoff:
        # Drop the template's aside ("> Must be readable without..."), keep the data.
        handoff = "\n".join(
            line for line in handoff.splitlines() if not line.lstrip().startswith(">")
        ).strip()
    if handoff:
        lines.append(words["handoff"])
        lines.append(handoff)
        lines.append("")

    design_problems = (
        checks.design_errors(item, profile) if item.design_status == "ready" else []
    )

    ids = batch_ids(item)
    if ids:
        summary = ", ".join(
            f"{batch_id} {words.get(batch_state(item, batch_id), batch_state(item, batch_id))}"
            for batch_id in ids
        )
        lines.append(words["batches"].format(summary=summary))
        upcoming = next_batch(item)
        if upcoming:
            goal = _field(_row(item, upcoming), "Goal", "目标", default="")
            state = batch_state(item, upcoming)
            if state == "blocked":
                lines.append(
                    words["blocked_next"].format(batch=upcoming, goal=goal or "-")
                )
            elif state == "doing":
                lines.append(words["resume"].format(batch=upcoming, goal=goal or "-"))
            elif goal:
                lines.append(words["next"].format(batch=upcoming, goal=goal))
            else:
                lines.append(words["next_only"].format(batch=upcoming))
            depends = _field(_row(item, upcoming), "Depends", "依赖", default="")
            if depends:
                lines.append(f"Depends: {depends}")
        else:
            lines.append(words["next_none"])
        lines.append("")
    elif item.design_path is not None:
        lines.append(words["batches"].format(summary=words["design_no_batches"]))
        lines.append("")
    else:
        lines.append(words["batches"].format(summary=words["no_design"]))
        lines.append("")

    warnings = checks.item_warnings(item, profile)
    warnings.extend(f"design.md: {error}" for error in design_problems)
    if warnings:
        lines.append(words["warnings"])
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append(words["rules"])
    if item.design_path is None:
        if item.clarify_state not in artifacts.CLARIFIED:
            lines.append(words["rule_unclarified"])
        lines.append(words["rule_no_design"])
    else:
        confirmed = artifacts.section(item.design_body, "Confirmation", "方案确认") or ""
        when = ""
        for line in confirmed.splitlines():
            if "Date" in line or "日期" in line or "确认时间" in line:
                value = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                if value:
                    when = " " + value
        if item.clarify_state not in artifacts.CLARIFIED:
            lines.append(words["rule_unclarified"])
        if item.design_status != "ready" or design_problems:
            lines.append(words["rule_unconfirmed"])
        else:
            lines.append(words["rule_no_redesign"].format(when=when))
        for key in ("rule_batches", "rule_accept"):
            lines.append(words[key])
        if _has_parallel_group(item):
            lines.append(words["rule_parallel"])
        for key in ("rule_commit", "rule_stop"):
            lines.append(words[key])
    lines.append("")
    lines.append(words["gate"].format(command=gate))
    full = profile.full_level
    if full and full != "l1":
        lines.append(
            words["commit_gate"].format(
                command=f"python3 {command} gate --level {full} --work {item.id}"
            )
        )
    return "\n".join(lines)
