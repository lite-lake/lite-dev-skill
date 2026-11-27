#!/usr/bin/env python3
"""lite-dev flow tool.

Usage (from the project root):
    python3 <skill>/scripts/flow.py init [--plan | --apply ID] [--baseline] [--upgrade]
    python3 <skill>/scripts/flow.py status [--mine] [--stale [--days N]]
    python3 <skill>/scripts/flow.py new --title "Export CSV" --type REQ --size M
    python3 <skill>/scripts/flow.py check [--work <ID>]
    python3 <skill>/scripts/flow.py design <ID>
    python3 <skill>/scripts/flow.py design-ready <ID>
    python3 <skill>/scripts/flow.py gate --level l1 [--work <ID>]
    python3 <skill>/scripts/flow.py claim <ID> [--takeover --reason "..."]
    python3 <skill>/scripts/flow.py done <ID> [--owner "Name"]
    python3 <skill>/scripts/flow.py drop <ID> [--reason "..."]
    python3 <skill>/scripts/flow.py handoff <ID> [--batch <Bx>]
    python3 <skill>/scripts/flow.py archive <ID> [--reason "..."]
    python3 <skill>/scripts/flow.py unarchive <ID>
    python3 <skill>/scripts/flow.py whoami
    python3 <skill>/scripts/flow.py release --channel staging [--confirm "..."]
    python3 <skill>/scripts/flow.py reconcile
    python3 <skill>/scripts/flow.py extensions

All project facts come from docs/flow/profile.toml. Nothing here knows a
project name, repository name, language, or build command.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if sys.version_info < (3, 11):
    print(
        "error: lite-dev requires Python 3.11+ (tomllib); "
        f"this is {sys.version.split()[0]}. Run it with python3.11+ or newer.",
        file=sys.stderr,
    )
    raise SystemExit(2)

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from flowlib import (  # noqa: E402
    __version__,
    adopt,
    archive,
    artifacts,
    changelog,
    checks,
    commands,
    fsio,
    gate_log,
    git,
    handoff,
    identity,
    reconcile,
    release,
    scaffold,
    stamp,
)
from flowlib import profile as profile_mod  # noqa: E402
from flowlib.errors import FlowError  # noqa: E402
from flowlib.profile import (  # noqa: E402
    MODES,
    PRIORITIES,
    SIZES,
    TYPES,
    ProfileError,
)

SKILL_DIR = SCRIPTS.parent
TEMPLATE = SKILL_DIR / "templates" / "item.md"
DESIGN_TEMPLATE = SKILL_DIR / "templates" / "design.md"


def _flow_invocation() -> str:
    """How this install tells a human to run the next step."""
    return f"python3 {SKILL_DIR / 'scripts' / 'flow.py'}"


# Printed by `init --upgrade` when the install crosses a major version. The
# long form lives in references/upgrade.md; this is the hard carrier's echo.
MAJOR_CHECKLIST = (
    "Read every section above, especially the [breaking] ones.",
    "Re-read references/invariants.md and SKILL.md; a heading or rule may have changed.",
    f"Run `flow.py extensions`; every enabled extension's requires must admit {__version__}.",
    "Run `flow.py init --plan`; a new profile key or required document may exist.",
    "Run `check` and the strictest gate level on this project.",
    "Record the outcome, then rerun with --accept-major.",
)


def _wiring_refusal(profile, *, level: str) -> int | None:
    """The one hard adoption gate: a command that is declared and not wired.

    Only the requested level is judged: a project may wire l1 and l2 before it
    wires l3, and cheap iteration should not wait. `done` passes the strictest
    defined level, which is the level it closes on.
    """
    wiring = profile_mod.level_wiring_problems(profile, level)
    what = f"gate {level}"
    if not wiring:
        return None
    print(f"FAIL: {what} is not wired")
    for problem in wiring:
        print(f"  - {problem}")
    print(f"next: {_flow_invocation()} init --plan")
    return 2


STATUS_ORDER = {
    "need-clarify": 0,
    "clarified": 1,
    "designing": 2,
    "ready": 3,
    "done": 4,
    "dropped": 5,
}
NEXT_ACTION = {
    "need-clarify": "answer the clarifying questions, then set '- Status: clarified'",
    "clarified": "start the change; add test-report, run gate, then done (write design.md first if required)",
    "designing": "finish design.md, then run design-ready {id}",
    "ready": "implement the batches, run the gate, then done {id}",
}


def _load_profile(args) -> profile_mod.Profile:
    return profile_mod.load(getattr(args, "profile", None))


def _slugify(title: str) -> str:
    """A directory slug that follows the title's script.

    Chinese titles keep their characters and cap at 30, which is 60 columns;
    everything else keeps the dash-joined form and the 32-character cap.
    """
    text = title.strip()
    wide = bool(artifacts.CJK_RE.search(text))
    limit = artifacts.SLUG_WIDE_MAX if wide else artifacts.SLUG_ASCII_MAX
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text, flags=re.UNICODE)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned[:limit].rstrip("-")


ID_ATTEMPTS = 50
_CLOCK = stamp.Clock()


def _new_id(
    profile: profile_mod.Profile, item_type: str, created: str, moment: datetime
) -> str:
    """Allocate the id for this moment, bumping the time code on collision.

    Only the item's month bucket is read: an id carries `created`'s date, so a
    candidate can only meet an item filed in the same month.
    """
    bucket = profile.work_path / artifacts.month_of(created)
    existing: set[str] = set()
    if bucket.is_dir():
        for path in bucket.iterdir():
            if not path.is_dir():
                continue
            existing.add(path.name)
            if (path / "item.md").is_file():
                existing.add(artifacts.load_item(path).id)
    ms = _CLOCK.allocate(created, moment)
    for _ in range(ID_ATTEMPTS):
        if ms >= stamp.MS_PER_DAY:
            raise FlowError(
                f"no id left in {created}: the clock is at the last millisecond of the day; "
                "rerun after midnight"
            )
        candidate = profile.id_format.format(
            date=created.replace("-", ""), type=item_type, time=stamp.encode(ms)
        )
        if candidate not in existing and not any(
            name == candidate or name.startswith(candidate + "-") for name in existing
        ):
            _CLOCK.commit(created, ms)
            return candidate
        ms += 1
    raise FlowError(
        f"cannot allocate an item id after {ID_ATTEMPTS} attempts; check [id] format"
    )


def cmd_new(args) -> int:
    profile = _load_profile(args)
    item_type = args.type.upper()
    size = args.size.upper()
    priority = args.priority.upper()
    if item_type not in TYPES:
        raise FlowError(f"--type must be one of {', '.join(TYPES)}")
    if size not in SIZES:
        raise FlowError("--size must be one of S, M, L")
    if priority not in PRIORITIES:
        raise FlowError(f"--priority must be one of {', '.join(PRIORITIES)}")
    mode = args.mode or ("two-phase" if size == "L" else "one-shot")
    if mode not in MODES:
        raise FlowError("--mode must be one-shot or two-phase")

    owner = identity.resolve_for(profile, args.owner)
    moment = stamp.now()
    created = moment.date().isoformat()
    bucket = profile.work_path / artifacts.month_of(created)
    title = " ".join(args.title.split())
    slug = _slugify(title)

    with fsio.project_lock(profile.root):
        bucket.mkdir(parents=True, exist_ok=True)
        directory = None
        item_id = ""
        for _ in range(5):
            item_id = _new_id(profile, item_type, created, moment)
            candidate = bucket / (f"{item_id}-{slug}" if slug else item_id)
            try:
                candidate.mkdir(parents=False, exist_ok=False)
            except FileExistsError:
                continue
            directory = candidate
            break
        if directory is None:
            raise FlowError("cannot create the item directory; another process keeps taking the id")

        text = TEMPLATE.read_text(encoding="utf-8")
        for token, value in {
            "<ID>": item_id,
            "<TITLE>": title,
            "<TYPE>": item_type,
            "<PRIORITY>": priority,
            "<SIZE>": size,
            "<MODE>": mode,
            "<OWNER>": owner,
            "<DATE>": created,
        }.items():
            text = text.replace(token, value)
        fsio.atomic_write_text(directory / "item.md", text)

    print(f"created {item_id}")
    print(f"  {(directory / 'item.md').relative_to(profile.root)}")
    if size in profile.design_required_for:
        print(
            "next: clarify the requirement, set '- Status: clarified', then "
            f"`flow.py design {item_id}` (size {size} requires a design)"
        )
    else:
        print("next: clarify the requirement, then set '- Status: clarified'")
    return 0


def _repo_state(profile: profile_mod.Profile, repo) -> dict:
    """One repository as a line of fact: branch, HEAD, distance from last fetch."""
    root = profile.repo_root(repo.path)
    state = {
        "path": repo.name,
        "present": False,
        "branch": "",
        "head": "",
        "ahead": 0,
        "behind": 0,
        "upstream": False,
        "dirty": 0,
    }
    try:
        if not git.is_repo(root):
            return state
        counts = git.upstream_counts(root)
        state.update(
            {
                "present": True,
                "branch": git.branch(root),
                "head": git.head(root)[:7],
                "ahead": counts[0] if counts else 0,
                "behind": counts[1] if counts else 0,
                "upstream": counts is not None,
                "dirty": len(git.dirty(root)),
            }
        )
    except git.GitError:
        return state
    return state


def _repos(profile: profile_mod.Profile) -> list[dict]:
    return [_repo_state(profile, repo) for repo in profile.workspace_repos]


def _repo_line(states: list[dict]) -> str:
    parts = []
    for state in states:
        if not state["present"]:
            parts.append(f"{state['path']} (not checked out)")
            continue
        tail = []
        if state["behind"]:
            tail.append(f"behind {state['behind']}")
        if state["dirty"]:
            tail.append(f"+{state['dirty']} dirty")
        suffix = f" ({', '.join(tail)})" if tail else ""
        parts.append(
            f"{state['path']} {state['branch'] or 'detached'} {state['head']}{suffix}"
        )
    return " | ".join(parts)


def _checkout(profile: profile_mod.Profile) -> dict | None:
    """The single repository's checkout state, for a project that has one."""
    state = _repo_state(profile, profile.workspace_repos[0])
    if not state["present"]:
        return None
    return {
        "branch": state["branch"],
        "head": state["head"],
        "ahead": state["ahead"],
        "behind": state["behind"],
        "upstream": state["upstream"],
    }


def _stale_rows(
    profile: profile_mod.Profile, items: list[artifacts.Item], days: int
) -> tuple[list[dict], str]:
    """Open items nobody has touched for a while, derived from git.

    The date is the latest commit that touched anything in the item directory;
    an uncommitted item falls back to its `created` date. This is a report, not
    a state: nothing is written and nothing is blocked. Items live in the
    control repository, so that is the history this reads.
    """
    today = date.today()
    dates: dict[str, str] = {}
    note = ""
    try:
        if git.is_repo(profile.control_root):
            dates = git.activity_dates(
                profile.control_root, profile.control_relative(profile.work_dir)
            )
        else:
            note = "the control directory is not a git repository; using created dates"
    except git.GitError:
        note = "git is unavailable; using created dates"

    rows: list[dict] = []
    for item in items:
        if (item.meta.get("closed") or "").strip():
            continue
        relative = item.directory.relative_to(profile.root).as_posix()
        last = dates.get(relative) or (item.meta.get("created") or "").strip()
        if not last:
            continue
        try:
            age = (today - date.fromisoformat(last)).days
        except ValueError:
            continue
        if age <= days:
            continue
        started = any(
            artifacts.row_value(row, "Status", "状态").strip().lower()
            in {"doing", "done", "进行中", "完成"}
            for row in item.progress
        )
        marker = (
            " (design ready, no batch started)"
            if item.design_status == "ready" and not started
            else ""
        )
        rows.append(
            {
                "id": item.id,
                "status": item.status,
                "owner": item.meta.get("owner", ""),
                "last": last,
                "days": age,
                "note": marker.strip(),
            }
        )
    rows.sort(key=lambda row: row["days"], reverse=True)
    return rows, note


def _print_stale(rows: list[dict], note: str, days: int) -> None:
    if rows:
        print(f"\nstale open items (>{days} days, last commit or created):")
        for row in rows:
            tail = f"  {row['note']}" if row["note"] else ""
            print(
                f"  {row['id']}  {row['status']}  {row['owner'] or '-'}  "
                f"{row['days']}d  {row['last']}{tail}"
            )
    else:
        print(f"\nstale: none older than {days} days")
    if note:
        print(f"  ({note})")


def _resolve_repo_arg(profile: profile_mod.Profile, value: str) -> str:
    """A `--repo` value as a declared repository path; `.` is the control repo."""
    clean = value.strip().rstrip("/")
    if clean in (".", "./", ""):
        clean = profile.control_path
    known = {repo.path for repo in profile.workspace_repos}
    if clean not in known:
        raise FlowError(
            f"--repo {value!r} is not a declared repository; known: "
            + ", ".join(sorted(repo.name for repo in profile.workspace_repos))
        )
    return clean


def _mentions(repo_root: Path, item_id: str) -> bool:
    """True when the repository's history mentions the item."""
    try:
        if not git.is_repo(repo_root) or not git.head(repo_root):
            return False
        return bool(git.commits_matching(repo_root, item_id))
    except git.GitError:
        return False


def cmd_status(args) -> int:
    profile = _load_profile(args)
    items = artifacts.all_items(profile)
    # The ladder is project-level: filters below narrow the item table, not the
    # question "has this project adopted the flow yet".
    ladder_items = items + artifacts.archived_items(profile)
    mine = ""
    if args.mine:
        mine = identity.resolve_for(profile, None)
        items = [
            item for item in items if identity.same(item.meta.get("owner") or "", mine)
        ]

    repo_filter = ""
    if getattr(args, "repo", None):
        repo_filter = _resolve_repo_arg(profile, args.repo)
        items = [
            item
            for item in items
            if item.id and _mentions(profile.repo_root(repo_filter), item.id)
        ]

    counts: dict[str, int] = {}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    checkout = _checkout(profile)
    repo_states = _repos(profile) if profile.workspace else []
    items.sort(key=lambda item: (STATUS_ORDER.get(item.status, 9), item.id))
    full = profile.full_level
    # A fresh clone has no PASS yet; that is expected until an item is ready to
    # close. Do not open every session with a warning it cannot act on.
    gate_relevant = any(item.status in {"ready", "done"} for item in items)
    stale = gate_log.stale_line(profile, full) if full and gate_relevant else None
    advisories = [
        line
        for line in (
            checks.full_level_warning(profile),
            stale,
            profile_mod.drift_note(__version__, profile.reviewed),
        )
        if line
    ]
    stale_rows: list[dict] = []
    stale_note = ""
    if args.stale:
        stale_rows, stale_note = _stale_rows(profile, items, args.days)
    ladder = adopt.ladder(profile, items=ladder_items)

    if args.json:
        payload = {
            "project": profile.name,
            "version": __version__,
            "reviewed": profile.reviewed,
            "drift": profile_mod.classify_drift(__version__, profile.reviewed),
            "profile": str(profile.path.relative_to(profile.root)),
            "checkout": checkout,
            "adoption": {
                "done": ladder.done,
                "total": len(ladder.rungs),
                "current": ladder.current.id if ladder.current else None,
                "next": ladder.current.command if ladder.current else None,
                "rungs": [
                    {"id": rung.id, "name": rung.name, "done": rung.done}
                    for rung in ladder.rungs
                ],
            },
            "repos": [
                {**state, "control": repo.control}
                for state, repo in zip(repo_states, profile.workspace_repos)
            ]
            if profile.workspace
            else None,
            "mine": mine or None,
            "gate": {"full": full, "stale": stale},
            "items": [
                {
                    "id": item.id,
                    "title": item.meta.get("title", ""),
                    "type": item.meta.get("type", ""),
                    "size": item.size,
                    "mode": item.mode,
                    "status": item.status,
                    "owner": item.meta.get("owner", ""),
                    "closed_by": item.meta.get("closed_by", ""),
                    "prd": item.meta.get("prd", ""),
                    "board": item.meta.get("board", ""),
                    "ac_done": item.ac_done,
                    "ac_total": item.ac_total,
                    "design": (
                        (
                            "ready!"
                            if checks.design_errors(item, profile)
                            else "ready"
                        )
                        if item.design_status == "ready"
                        else (
                            "draft"
                            if item.design_path
                            else ("required" if item.size in profile.design_required_for else "")
                        )
                    ),
                    "path": str(item.directory.relative_to(profile.root)),
                }
                for item in items
            ],
            "counts": {key: counts[key] for key in STATUS_ORDER if key in counts},
        }
        if args.stale:
            payload["stale"] = {
                "days": args.days,
                "items": stale_rows,
                "note": stale_note or None,
            }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"{profile.name} ({profile.path.relative_to(profile.root)})")
    print(f"  lite-dev {__version__}")
    if repo_filter or getattr(args, "repo", None):
        print(f"  filter  repo {repo_filter or '.'}")
    if profile.workspace:
        control = profile.control_path or "."
        print(f"  control {control}")
        print(f"  repos   {_repo_line(repo_states)}")
        missing = [
            state["path"]
            for state, repo in zip(repo_states, profile.workspace_repos)
            if not state["present"] and repo.required
        ]
        if missing:
            print(
                "  warn:    not checked out here: "
                + ", ".join(missing)
                + " (its changes are invisible to the gate on this machine)"
            )
    elif checkout:
        label = checkout["branch"] or "detached HEAD"
        if checkout["upstream"]:
            print(
                f"  checkout {label} {checkout['head']} "
                f"(upstream: behind {checkout['behind']}, ahead {checkout['ahead']})"
            )
        else:
            print(f"  checkout {label} {checkout['head']} (no upstream; this clone only)")

    for line in adopt.render_ladder(ladder, indent="  "):
        print(line)

    if not items:
        print("  no work items" if not mine else f"  no items for {mine}")
        archived = len(artifacts.archived_items(profile))
        if archived:
            print(f"{archived} archived ({profile.work_dir}/_archive/README.md)")
        _print_advisories(advisories)
        if args.stale:
            _print_stale(stale_rows, stale_note, args.days)
        return 0

    rows = []
    design_problems: dict[str, list[str]] = {}
    for item in items:
        if item.design_status == "ready":
            problems = checks.design_errors(item, profile)
            if problems:
                design_problems[item.id] = problems
            design = "ready!" if problems else "ready"
        elif item.design_path:
            design = "draft"
        elif item.size in profile.design_required_for:
            design = "required"
        else:
            design = "-"
        rows.append(
            [
                item.id,
                item.meta.get("type", "-"),
                item.size or "-",
                item.mode or "-",
                item.status,
                item.meta.get("owner", "-"),
                f"{item.ac_done}/{item.ac_total}",
                design,
            ]
        )
    headers = ["ID", "TYPE", "SIZE", "MODE", "STATUS", "OWNER", "AC", "DESIGN"]
    widths = [max(len(str(row[i])) for row in rows + [headers]) for i in range(len(headers))]
    print("  ".join(header.ljust(widths[i]) for i, header in enumerate(headers)))
    for row in rows:
        print("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))

    counts: dict[str, int] = {}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    summary = ", ".join(f"{key} {counts[key]}" for key in STATUS_ORDER if key in counts)
    print(f"\n{len(items)} item(s): {summary}")
    archived = len(artifacts.archived_items(profile))
    if archived:
        print(f"{archived} archived ({profile.work_dir}/_archive/README.md)")
    _print_advisories(advisories)
    if args.stale:
        _print_stale(stale_rows, stale_note, args.days)

    for item_id, problems in design_problems.items():
        extra = f" (+{len(problems) - 1} more; run check)" if len(problems) > 1 else ""
        print(f"warn: {item_id} design.md is marked ready but invalid: {problems[0]}{extra}")

    next_lines = []
    for item in items:
        if item.status == "clarified" and item.size in profile.design_required_for:
            template = "write design.md (flow.py design {id}), then run design-ready {id}"
        else:
            template = NEXT_ACTION.get(item.status)
        if template:
            next_lines.append(f"  {item.id}  {template.format(id=item.id)}")
    if next_lines:
        print("\nnext:")
        print("\n".join(next_lines))
    return 0


def _print_issues(errors: list[str], warnings: list[str]) -> None:
    for error in errors:
        print(f"  error: {error}")
    for warning in warnings:
        print(f"  warn:  {warning}")


def _print_advisories(advisories: list[str]) -> None:
    """Profile-level advice that never blocks: `status` prints, the gate decides."""
    if not advisories:
        return
    print()
    for line in advisories:
        print(f"warn: {line}")


def cmd_version(args) -> int:
    """What this install is, and how it relates to the project's contract.

    Answers even when the profile cannot load: a pin from another major is
    exactly when a human runs it.
    """
    skill = str(SKILL_DIR)
    commit = ""
    dirty = False
    repo = git.repo_of(SKILL_DIR)
    if repo is not None and git.tracks(repo, SKILL_DIR):
        try:
            commit = git.head(repo)
        except git.GitError:
            commit = ""
        try:
            prefix = SKILL_DIR.resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            prefix = ""
        if prefix and prefix != ".":
            dirty = any(
                line[3:].strip().strip('"').startswith(prefix)
                for line in git.dirty(repo)
            )

    profile_path: Path | None = None
    if getattr(args, "profile", None):
        profile_path = Path(args.profile).resolve()
    else:
        try:
            profile_path = profile_mod.find_profile()
        except ProfileError:
            profile_path = None

    requires = reviewed = language = ""
    error = ""
    if profile_path is not None:
        try:
            requires, reviewed, language = profile_mod.raw_flow_pins(profile_path)
        except ProfileError as exc:
            error = str(exc)
        if not error:
            try:
                profile_mod.load(profile_path)
            except ProfileError as exc:
                error = str(exc)
    effective = reviewed or profile_mod.range_floor(requires)
    try:
        drift = profile_mod.classify_drift(__version__, effective)
    except ProfileError:
        drift = "unknown"
    changelog_path = str(changelog.skill_path(language or "en"))

    if args.json:
        payload = {
            "version": __version__,
            "skill": skill,
            "commit": commit or None,
            "dirty": dirty,
            "project": str(profile_path) if profile_path else None,
            "requires": requires or None,
            "reviewed": effective or None,
            "drift": drift,
            "error": error or None,
            "changelog": changelog_path,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"lite-dev {__version__}")
    print(f"  skill:    {skill}")
    if commit:
        state = "dirty" if dirty else "clean"
        print(f"  commit:   {commit[:12]} ({state})")
    else:
        print("  commit:   none (not a tracked checkout)")
    if profile_path is None:
        print("  project:  none (run init in a project root)")
        return 0
    print(f"  project:  {profile_path}")
    print(f"  requires: {requires or '(missing)'}")
    print(f"  reviewed: {effective or '(none)'}")
    print(f"  drift:    {drift}{_drift_next(drift, effective)}")
    print(f"  changelog: {changelog_path}")
    if error:
        print(f"  error:    {error}")
    return 0


def _drift_next(drift: str, reviewed: str) -> str:
    if drift == "patch":
        return " (seamless)"
    if drift == "minor":
        return (
            f"; read CHANGELOG {reviewed}..{__version__}, then "
            "init --upgrade --apply flow.reviewed"
        )
    if drift == "major":
        return "; run init --upgrade, read the breaking sections, then pass --accept-major"
    if drift in ("older-minor", "older-major"):
        return f"; install lite-dev >= {reviewed}"
    if drift == "unknown":
        return "; run init --upgrade to record a reviewed version"
    return ""


def cmd_check(args) -> int:
    profile = _load_profile(args)
    errors, warnings = checks.check_project(profile, work=args.work)
    ok = not errors
    if args.json:
        print(
            json.dumps(
                {
                    "ok": ok,
                    "profile": str(profile.path),
                    "version": __version__,
                    "extensions": profile.extension_info,
                    "errors": errors,
                    "warnings": warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if ok else 1

    print(f"profile: {profile.path.relative_to(profile.root)}")
    if ok:
        print(f"PASS: no errors ({len(warnings)} warning(s); warnings do not block)")
    else:
        print(f"FAIL: {len(errors)} error(s), {len(warnings)} warning(s); errors block")
    _print_issues(errors, warnings)
    return 0 if ok else 1


def cmd_design_ready(args) -> int:
    profile = _load_profile(args)
    item = artifacts.find_item(profile, args.id)
    if artifacts.is_archived(item):
        raise FlowError(
            f"{item.id} is archived; run flow.py unarchive {item.id} before changing its design"
        )
    errors = checks.design_errors(item, profile)
    if errors:
        print("FAIL: the design is not ready")
        for error in errors:
            print(f"  - {error}")
        return 1
    with fsio.project_lock(profile.root):
        artifacts.set_frontmatter_value(item.design_path, "status", "ready")
    print(f"PASS: design marked ready ({item.design_path.relative_to(profile.root)})")
    print(f"next: implement the batches, then flow.py gate --level l1 --work {item.id}")
    return 0


def cmd_design(args) -> int:
    """Create design.md from the template, so the scaffold is not guesswork."""
    profile = _load_profile(args)
    item = artifacts.find_item(profile, args.id)
    if artifacts.is_archived(item):
        raise FlowError(
            f"{item.id} is archived; run flow.py unarchive {item.id} before designing it"
        )
    if item.design_path is not None:
        raise FlowError(
            f"{item.id} already has design.md; edit it and run design-ready"
        )
    if item.clarify_state not in artifacts.CLARIFIED:
        raise FlowError(
            "requirement is not clarified; set '- Status: clarified' in ## Clarify first"
        )
    text = DESIGN_TEMPLATE.read_text(encoding="utf-8").replace("<ID>", item.id)
    with fsio.project_lock(profile.root):
        fsio.atomic_write_text(item.directory / "design.md", text)
    print(f"created {item.id} design.md")
    print(f"  {(item.directory / 'design.md').relative_to(profile.root)}")
    print(f"next: fill the plan, get the human's confirmation, then flow.py design-ready {item.id}")
    return 0


def cmd_gate(args) -> int:
    profile = _load_profile(args)
    # A level whose commands are not wired is not a gate. Refuse before the
    # static checks so the message is the wiring problem, not a shell error from
    # an unconfigured placeholder.
    refusal = _wiring_refusal(profile, level=args.level)
    if refusal is not None:
        return refusal
    errors, warnings = checks.check_project(profile, work=args.work)
    item = None
    if args.work:
        item = artifacts.find_item(profile, args.work)

    changed = checks.changed_paths(profile, item)
    warnings.extend(changed.degraded)
    if item is not None:
        risk_errors, risk_warnings = checks.risk_gate(item, profile, changed)
        errors.extend(risk_errors)
        warnings.extend(risk_warnings)
    warnings.extend(checks.fallback_warnings(profile, args.level, changed))

    chosen = checks.scope(profile, item, args.repo)
    warnings.extend(chosen.warnings)
    if profile.workspace:
        print(
            f"gate {args.level}: scope {chosen.reason} — "
            + ", ".join(path or "." for path in chosen.repos)
        )

    if errors:
        print("FAIL: static checks must pass before the gate runs")
        _print_issues(errors, warnings)
        return 1
    for warning in warnings:
        print(f"warn: {warning}")

    if item is not None:
        if item.size in profile.design_required_for and item.design_status != "ready":
            print(
                f"FAIL: {item.id} is size {item.size} and needs a ready design "
                "(flow.py design-ready <ID>)"
            )
            return 1

    full = profile.full_level
    if full and full != args.level:
        stale = gate_log.stale_line(profile, full)
        if stale:
            print(f"warn: {stale}")

    try:
        return commands.run_gate(
            profile,
            args.level,
            timeout=args.timeout,
            item=item.id if item is not None else "",
            repos=chosen.repos,
        )
    except ProfileError as exc:
        print(f"error: {exc}")
        return 2


def _mention_evidence(path: Path) -> None:
    """Link the test report from item.md so the next session finds the evidence.

    `done` has just validated the report. Recording the pointer is the same kind
    of bookkeeping as `closed` and `closed_by`; without it every closed designed
    item would carry an "artifact never mentioned" warning forever.
    """
    if not (path.parent / "test-report.md").is_file():
        return
    text = artifacts.read_text(path)
    if "test-report.md" in text:
        return
    line = "- Evidence: test-report.md"
    match = re.search(r"^##[ \t]+Notes[ \t]*$", text, re.M)
    if match:
        text = text[: match.end()] + f"\n\n{line}" + text[match.end():]
    else:
        text = text.rstrip() + f"\n\n## Notes\n\n{line}\n"
    fsio.atomic_write_text(path, text)


def cmd_done(args) -> int:
    profile = _load_profile(args)
    # Closing rides on the strictest level, so that is the level that must be
    # wired; a lower unwired level is caught when it is next run.
    refusal = _wiring_refusal(profile, level=profile.full_level)
    if refusal is not None:
        return refusal
    item = artifacts.find_item(profile, args.id)
    closer = identity.try_resolve_for(profile, args.owner)

    closed = (item.meta.get("closed") or "").strip()
    if closed:
        print(f"{item.id} is already closed ({closed})")
        return 0

    # Say which level this close will actually ride on before refusing anything:
    # a profile that defines only a cheap level is legal, not silent.
    advisory = checks.full_level_warning(profile)
    if advisory:
        print(f"warn: {advisory}")

    if artifacts.is_archived(item):
        raise FlowError(
            f"{item.id} is archived; run flow.py unarchive {item.id} before changing it"
        )
    if closer is None:
        raise FlowError(
            "no identity: set git config lite-dev.owner \"Your Name\", "
            "$LITE_DEV_OWNER, or pass --owner; `done` must record who closed the item"
        )

    errors = checks.item_errors(item, profile)
    if item.ac_done != item.ac_total:
        open_ids = ", ".join(entry["id"] for entry in item.ac if not entry["done"])
        errors.append(f"unchecked AC: {open_ids}")
    if item.size in profile.design_required_for and item.design_status != "ready":
        errors.append(f"size {item.size} needs a ready design before it can be done")
    if item.design_path is not None:
        if item.design_status != "ready":
            errors.append(
                f"design.md is {item.design_status or 'draft'}, not ready; "
                "run design-ready (and fix it) before closing"
            )
        else:
            errors.extend(checks.design_errors(item, profile))
    report = item.directory / "test-report.md"
    if not report.is_file():
        errors.append(
            f"{item.directory.name}: done requires test-report.md; "
            "the AC tick is a claim, not evidence"
        )
    evidence_errors, evidence_warnings = checks.evidence_problems(item, strict=True)
    errors.extend(evidence_errors)
    if errors:
        print("FAIL: cannot close the work item")
        for error in errors:
            print(f"  - {error}")
        return 1
    for warning in evidence_warnings:
        print(f"warn: {warning}")

    full = profile.full_level
    if full is None:
        errors.append("the profile defines no gate level; cannot close an item without one")
    elif gate_log.path_for(profile) is None:
        errors.append(
            "the gate ledger is unavailable (not a git repository); "
            "lite-dev records a full-level PASS per clone, so run the flow inside git"
        )
    elif gate_log.last_pass_for(profile, full, item.id) is None:
        errors.append(
            f"no {full} PASS recorded for {item.id} in this clone; "
            f"run `flow.py gate --level {full} --work {item.id}` before closing"
        )
    if errors:
        print("FAIL: cannot close the work item")
        for error in errors:
            print(f"  - {error}")
        return 1

    owner = (item.meta.get("owner") or "").strip()
    if owner and not identity.same(owner, closer[0]):
        print(
            f"warn: {item.id} is owned by {owner}; closing as {closer[0]} "
            "(the verifier may close; `closed_by` records it)"
        )

    with fsio.project_lock(profile.root):
        current = artifacts.find_item(profile, item.id)
        if (current.meta.get("closed") or "").strip():
            print(f"{item.id} is already closed ({current.meta['closed'].strip()})")
            return 0
        updates = {"closed": checks.today(), "closed_by": closer[0]}
        artifacts.set_frontmatter_values(current.path, updates)
        _mention_evidence(current.path)
    print(f"done {item.id} ({checks.today()})")
    print(f"  AC {item.ac_done}/{item.ac_total}")
    print(f"  design: {item.design_status or '-'}")
    print(f"  closed by: {closer[0]}")
    print(f"  {item.path.relative_to(profile.root)}")
    return 0


def cmd_drop(args) -> int:
    """Retire an item that will not be delivered, without pretending it passed."""
    profile = _load_profile(args)
    item = artifacts.find_item(profile, args.id)
    if artifacts.is_archived(item):
        raise FlowError(
            f"{item.id} is archived; run flow.py unarchive {item.id} before dropping it"
        )
    closed = (item.meta.get("closed") or "").strip()
    if closed:
        raise FlowError(
            f"{item.id} is already closed ({closed}); use archive if it should leave the working set"
        )
    closer = identity.resolve_for(profile, args.owner)
    reason = " ".join((args.reason or "").split())
    with fsio.project_lock(profile.root):
        current = artifacts.find_item(profile, args.id)
        if (current.meta.get("closed") or "").strip():
            print(f"{item.id} is already closed ({current.meta['closed'].strip()})")
            return 0
        updates = {"closed": "dropped", "closed_by": closer}
        if reason:
            updates["drop_reason"] = reason
        artifacts.set_frontmatter_values(current.path, updates)
    print(f"dropped {item.id}")
    if reason:
        print(f"  reason: {reason}")
    print(f"  {item.path.relative_to(profile.root)}")
    return 0


def cmd_claim(args) -> int:
    profile = _load_profile(args)
    item = artifacts.find_item(profile, args.id)
    owner = identity.resolve_for(profile, args.owner)
    if artifacts.is_archived(item):
        raise FlowError(
            f"{item.id} is archived; run flow.py unarchive {item.id} before changing its owner"
        )
    previous = (item.meta.get("owner") or "").strip()
    if identity.same(previous, owner):
        print(f"{item.id} is already owned by {previous or owner}")
        return 0
    closed = (item.meta.get("closed") or "").strip()
    if closed:
        raise FlowError(
            f"{item.id} is already closed ({closed}); ownership of a closed item is history. "
            "Create a new item instead of rewriting it."
        )
    if previous and not args.takeover:
        raise FlowError(
            f"{item.id} is owned by {previous} and is not closed ({item.status}); "
            "pass --takeover to reassign it, or ask the owner first. "
            "Ownership is a signal, not a lock: read the item before taking it."
        )
    reason = " ".join((getattr(args, "reason", "") or "").split())
    if previous and args.takeover and not reason:
        raise FlowError(
            f"taking over {item.id} from {previous} needs --reason \"...\"; "
            "record why the handover happened"
        )
    with fsio.project_lock(profile.root):
        current = artifacts.find_item(profile, args.id)
        updates = {"owner": owner}
        if previous and args.takeover:
            actor = identity.try_resolve_for(profile, None)
            updates["takeover_by"] = actor[0] if actor else owner
            updates["takeover_reason"] = reason
        artifacts.set_frontmatter_values(current.path, updates)
    print(f"claimed {item.id}: {previous or 'unowned'} -> {owner}")
    if reason:
        print(f"  reason: {reason}")
    print("commit the change so teammates see the claim")
    return 0


def cmd_whoami(args) -> int:
    profile = _load_profile(args)
    found = identity.try_resolve_for(profile, args.owner)
    if found is None:
        print("identity: (none)")
        print(
            f"set one with --owner, ${identity.ENV_VAR}, or "
            f"`git config --global {identity.CONFIG_KEY} \"Your Name\"`"
        )
        return 1
    owner, source = found
    print(f"identity: {owner}")
    print(f"source:   {source}")
    print(f"project:  {profile.name} ({profile.path.relative_to(profile.root)})")
    return 0


def _commit_text(commits: list[git.Commit], since: str | None, total: int) -> str:
    if not commits:
        return "None"
    origin = since[:7] if since else "the first commit"
    lines = [f"{total} commit(s) since {origin}"]
    lines.extend(f"- `{commit.short}` {commit.subject}" for commit in commits)
    return "\n".join(lines)


def _item_text(profile: profile_mod.Profile, commits: list[git.Commit]) -> str:
    known = {
        item.id
        for item in artifacts.all_items(profile) + artifacts.archived_items(profile)
        if item.id
    }
    ids: list[str] = []
    for commit in commits:
        for item_id in profile.id_pattern.findall(f"{commit.subject}\n{commit.body}"):
            if item_id not in ids:
                ids.append(item_id)
    if not ids:
        return "None"
    lines = [f"- {item_id}" for item_id in ids if item_id in known]
    lines.extend(
        f"- (missing) {item_id} — referenced by a commit but no such item exists"
        for item_id in ids
        if item_id not in known
    )
    return "\n".join(lines)


def _record_path(profile: profile_mod.Profile, channel: str, day: str, source: str) -> Path:
    return release.next_path(profile, channel, day, source)


@dataclass
class ChannelPlan:
    """Everything one channel's record needs, computed once and printed once."""

    channel: str
    repo: str
    repo_root: Path
    mainline: str
    branch: str
    head: str
    previous: object | None
    since: str | None
    commits: list
    debt: object
    design_risk: list[str]
    risk: list[str]
    reconcile_risk: list[str]
    counts: tuple | None
    behind: int
    control_dirty: list[str]

    @property
    def repo_label(self) -> str:
        return self.repo or "."


def _plan_channel(
    profile: profile_mod.Profile, channel: str, since_arg: str | None
) -> ChannelPlan:
    bound = profile.channel(channel)
    repo = bound.repo if bound else profile.control_path
    repo_root = profile.repo_root(repo)
    git.ensure_repo(repo_root)
    branch = git.branch(repo_root)
    head = git.head(repo_root)
    previous = release.tip(profile, channel)
    if since_arg:
        if not git.is_ancestor(repo_root, since_arg, head):
            raise FlowError(
                f"--since {since_arg[:7]} is not an ancestor of HEAD; "
                "fetch/pull or pass a commit from this clone's history"
            )
        if (
            previous
            and since_arg != previous.source
            and git.is_ancestor(repo_root, previous.source, since_arg)
        ):
            raise FlowError(
                f"--since {since_arg[:7]} starts after the recorded tip "
                f"{previous.short}; record the range that follows the tip, "
                "or fix the bookkeeping commit first"
            )
    since = since_arg or (previous.source if previous else None)
    debt = reconcile.collect(profile, channel, since)
    range_paths = [
        profile.to_workspace(repo, path)
        for path in git.files_in_range(repo_root, since)
    ]
    design_risk = checks.risk_paths_touched(profile, range_paths)
    counts = git.upstream_counts(repo_root)
    control_dirty = (
        git.dirty(profile.control_root)
        if profile.control_root != repo_root
        else debt.dirty
    )
    return ChannelPlan(
        channel=channel,
        repo=repo,
        repo_root=repo_root,
        mainline=bound.mainline if bound else profile.release_mainline,
        branch=branch,
        head=head,
        previous=previous,
        since=since,
        commits=git.commits(repo_root, since),
        debt=debt,
        design_risk=design_risk,
        risk=design_risk if profile.release_confirm_risk_paths else [],
        reconcile_risk=checks.paths_matching(range_paths, profile.risk_paths),
        counts=counts,
        behind=counts[1] if counts else 0,
        control_dirty=control_dirty,
    )


def _print_plan(plan: ChannelPlan, profile: profile_mod.Profile) -> None:
    day = checks.today()
    target = _record_path(profile, plan.channel, day, plan.head)
    suffix = f" (repo {plan.repo_label})" if profile.workspace else ""
    print(f"channel: {plan.channel}{suffix}")
    print(f"source: {plan.head[:7]} ({plan.branch or 'detached HEAD'})")
    print(
        f"previous: {plan.previous.short + ' (' + plan.previous.date + ')' if plan.previous else 'none'}"
    )
    print(f"commits: {len(plan.commits)}")
    print(f"record: {target.relative_to(profile.root)}")
    counts = plan.counts
    if counts is None:
        print("upstream: none configured; cannot prove this clone is current")
    elif plan.behind:
        print(f"upstream: behind {plan.behind} commit(s); pull before recording")
    if plan.debt.dirty:
        print(f"dirty tree: {len(plan.debt.dirty)} path(s); recording will be refused")
    if plan.debt.blocking:
        print(
            f"debt: {len(plan.debt.no_item) + len(plan.debt.missing_item)} commit(s) "
            "without a work item; --note is required to record"
        )
    if plan.debt.bookkeeping:
        print(
            f"bookkeeping: {len(plan.debt.bookkeeping)} commit(s) ignored "
            "(records/archive only)"
        )
    if plan.reconcile_risk:
        only = [path for path in plan.reconcile_risk if path not in plan.design_risk]
        if only:
            listed = ", ".join(only[:3]) + (
                f" (+{len(only) - 3} more)" if len(only) > 3 else ""
            )
            print(
                f"warn: [reconcile] risk paths touched but not in [design] risk_paths: "
                f"{listed}; review whether --confirm should cover them"
            )
    if profile.release_confirm_risk_paths:
        if plan.risk:
            print(
                f"risk paths: {len(plan.risk)} touched; --confirm is required to record "
                "(the profile sets [release] confirm_risk_paths = true)"
            )
        else:
            print("risk paths: none touched; no confirmation required")


def _plan_errors(
    plan: ChannelPlan,
    profile: profile_mod.Profile,
    confirm_text: str,
    note: str,
) -> list[str]:
    errors: list[str] = []
    if plan.behind:
        errors.append(
            f"this clone is behind its upstream by {plan.behind} commit(s); "
            "pull before recording a release"
        )
    if plan.debt.dirty:
        errors.append(
            f"the {plan.repo_label} repository is dirty; commit or stash before "
            "recording a release"
        )
    if plan.control_dirty and profile.control_root != plan.repo_root:
        errors.append(
            f"the control repository ({profile.control_path or '.'}) is dirty; the "
            "record is written there, so commit or stash before recording"
        )
    if not plan.branch:
        errors.append("detached HEAD; check out the mainline branch before recording a release")
    elif plan.branch != plan.mainline:
        errors.append(
            f"current branch '{plan.branch}' is not the mainline '{plan.mainline}' for "
            f"channel '{plan.channel}'; record from the mainline"
        )
    if (
        plan.previous
        and plan.head != plan.previous.source
        and not git.is_ancestor(plan.repo_root, plan.previous.source, plan.head)
    ):
        errors.append(
            f"this clone is behind the channel: {plan.previous.short} is not an "
            "ancestor of HEAD. Pull or rebase before recording; the release must "
            "follow the recorded tip."
        )
    if plan.debt.blocking and not note.strip():
        errors.append(
            "there are commits without work items; record the debt in --note "
            "(do not fabricate history)"
        )
    if plan.risk and not confirm_text:
        listed = ", ".join(plan.risk[:3]) + (
            f" (+{len(plan.risk) - 3} more)" if len(plan.risk) > 3 else ""
        )
        errors.append(
            f"this release touches a risk path ({listed}); "
            'pass --confirm "<the human\'s words>" to record who authorized it'
        )
    return errors


def _authorization(
    risk: list[str], confirm_text: str, confirmed_by: str, by: str
) -> str:
    if not risk and not confirm_text:
        return "None"
    return (
        f"- Required: {'yes' if risk else 'no'}\n"
        f"- Confirmed by: {confirmed_by if confirm_text else '-'}\n"
        f"- Recorded by: {by}\n"
        f"- Note: {confirm_text or 'None'}"
    )


def _write_channel_record(
    profile: profile_mod.Profile,
    plan: ChannelPlan,
    *,
    day: str,
    by: str,
    gate_text: str,
    artifact_list: list[str],
    rollback: str,
    note: str,
    confirm_text: str,
    confirmed_by: str,
) -> Path:
    record = release.render(
        channel=plan.channel,
        repo=plan.repo,
        day=day,
        source=plan.head,
        previous=plan.previous.source if plan.previous else "none",
        by=by,
        tool=__version__,
        gate=gate_text,
        commits=_commit_text(plan.commits, plan.since, plan.debt.total),
        items=_item_text(profile, plan.commits),
        artifacts_text="\n".join(f"- {item}" for item in artifact_list) or "None",
        rollback=rollback,
        authorization=_authorization(plan.risk, confirm_text, confirmed_by, by),
        notes=note,
    )
    with fsio.project_lock(profile.root):
        current = release.tip(profile, plan.channel)
        current_source = current.source if current else "none"
        expected = plan.previous.source if plan.previous else "none"
        if current_source != expected:
            raise FlowError(
                "another process recorded a release in this clone while the gate ran; "
                "re-run release to plan against the new tip"
            )
        target = _record_path(profile, plan.channel, day, plan.head)
        fsio.atomic_write_text(target, record)
    return target


def cmd_release(args) -> int:
    profile = _load_profile(args)
    if not profile.release_channels:
        print("no release channels configured; add [release] channels in the profile")
        return 0
    if args.group and args.channel:
        print("error: --channel and --group describe different releases; pick one")
        return 2

    group = None
    if args.group:
        group = profile.group(args.group)
        if group is None:
            print(
                f"error: unknown release group '{args.group}'; configured: "
                f"{', '.join(entry.name for entry in profile.release_groups) or 'none'}"
            )
            return 2
        channels = list(group.channels)
    elif args.channel:
        if args.channel not in profile.release_channels:
            print(
                f"error: unknown channel '{args.channel}'; configured: "
                f"{', '.join(profile.release_channels)}"
            )
            return 2
        channels = [args.channel]
    else:
        print(f"channels: {', '.join(profile.release_channels)}")
        status = 0
        for channel in profile.release_channels:
            try:
                record = release.tip(profile, channel)
            except (FlowError, git.GitError) as exc:
                print(f"  {channel}: error: {exc}")
                status = 2
                continue
            if record:
                print(
                    f"  {channel}: last {record.date} {record.short} by {record.by or '-'} "
                    f"({record.path.relative_to(profile.root)})"
                )
            else:
                print(f"  {channel}: no record")
        for entry in profile.release_groups:
            print(f"  group {entry.name}: {', '.join(entry.channels)}")
        return status

    plans: list[ChannelPlan] = []
    for channel in channels:
        try:
            plans.append(_plan_channel(profile, channel, args.since))
        except (git.GitError, FlowError) as exc:
            prefix = f"{channel}: " if len(channels) > 1 else ""
            print(f"error: {prefix}{exc}")
            return 2

    if group is not None:
        print(f"group: {group.name}")
        print(f"channels: {', '.join(plan.channel for plan in plans)}")
        print(f"gate: {profile.release_gate_level} (one run covers every channel)")
        umbrella = release.next_group_path(profile, group.name, checks.today())
        print(f"index: {umbrella.relative_to(profile.root)}")
        print("")
    else:
        print(f"gate: {profile.release_gate_level} (runs on --record)")
    for plan in plans:
        _print_plan(plan, profile)
        print("")

    if not args.record:
        for plan in plans:
            print(
                f"{plan.channel}:\n"
                + reconcile.render(plan.debt, root=profile.root, verbose=args.verbose)
            )
        print('next: add --record --rollback "<target and steps>" [--note "..."]')
        return 0

    by = identity.resolve_for(profile, args.by)
    artifact_list = [item.strip() for item in (args.artifact or []) if item.strip()]
    confirm_text = (args.confirm or "").strip()
    confirmed_by = (getattr(args, "confirmed_by", "") or "").strip() or by
    note_text = (args.note or "").strip()

    errors: list[str] = []
    if not args.rollback or not args.rollback.strip():
        errors.append("--rollback is required and must describe the rollback target and steps")
    if profile.release_require_artifacts and not artifact_list:
        errors.append(
            "--artifact is required: the profile sets [release] require_artifacts = true"
        )
    for plan in plans:
        for error in _plan_errors(plan, profile, confirm_text, note_text):
            errors.append(f"{plan.channel}: {error}" if len(plans) > 1 else error)
    if confirm_text and not any(plan.risk for plan in plans):
        print(
            "warn: --confirm was given but the range touches no [design] risk path; "
            "the record will say Required: no"
        )
    static_errors, static_warnings = checks.check_project(profile)
    errors.extend(f"check: {error}" for error in static_errors)
    if errors:
        print("FAIL: release not recorded")
        for error in errors:
            print(f"  - {error}")
        return 1
    for warning in static_warnings:
        print(f"warn: {warning}")

    try:
        results, chosen_steps = commands.execute(
            profile, profile.release_gate_level, timeout=args.timeout
        )
    except ProfileError as exc:
        print(f"error: {exc}")
        return 2
    if commands.print_results(profile.release_gate_level, results, chosen_steps) != 0:
        print("FAIL: release not recorded")
        return 1
    gate_log.record(
        profile,
        profile.release_gate_level,
        True,
        item="release",
        repos=sorted({result.repo for result in results if result.repo}),
    )
    gate_text = commands.summary(profile.release_gate_level, results)

    day = checks.today()
    written: list[tuple[ChannelPlan, Path]] = []
    for plan in plans:
        target = _write_channel_record(
            profile,
            plan,
            day=day,
            by=by,
            gate_text=gate_text,
            artifact_list=artifact_list,
            rollback=args.rollback.strip(),
            note=(args.note or "None").strip(),
            confirm_text=confirm_text,
            confirmed_by=confirmed_by,
        )
        written.append((plan, target))
        print(f"recorded {target.relative_to(profile.root)}")
        print(
            f"  source {plan.head[:7]}  previous "
            f"{plan.previous.short if plan.previous else 'none'}"
        )

    if group is not None:
        risk_any = [plan.channel for plan in plans if plan.risk]
        umbrella_text = release.render_group(
            group=group.name,
            day=day,
            by=by,
            tool=__version__,
            gate=gate_text
            + "\n\nOne run of the level above covered every channel; each channel's "
            "record repeats it.",
            members=release.group_rows(
                [(plan.channel, plan.repo, plan.head, path) for plan, path in written]
            ),
            rollback=args.rollback.strip(),
            notes=(args.note or "None").strip(),
            authorization=_authorization(risk_any, confirm_text, confirmed_by, by)
            if risk_any or confirm_text
            else "None",
        )
        index = release.next_group_path(profile, group.name, day)
        with fsio.project_lock(profile.root):
            fsio.atomic_write_text(index, umbrella_text)
        print(f"index {index.relative_to(profile.root)} ({len(written)} channels)")
    print(f"  gate {profile.release_gate_level} PASS")
    print("next: commit the record so the next release reads the new watermark")
    return 0


def cmd_init(args) -> int:
    """Scaffold the project, then report where adoption stands.

    Scaffolding is additive and never overwrites. The adoption ladder is derived
    from files, not stored, so re-running this command is always safe and always
    shows the truth. `--plan` reads the repository and proposes profile values;
    `--apply <id>` is the only path that writes one. Without `--root`, an
    existing profile wins over the working directory: a workspace is entered
    from any of its repositories, and scaffolding a second flow inside a
    subdirectory would split the item store in two.
    """
    if args.root:
        root = Path(args.root).resolve()
        if not root.is_dir():
            print(f"error: {root} is not a directory", file=sys.stderr)
            return 2
    else:
        root = Path.cwd()
        try:
            existing = profile_mod.find_profile()
        except ProfileError:
            existing = None
        if existing is not None:
            try:
                root = profile_mod.load(existing).root
            except ProfileError as exc:
                if not args.upgrade:
                    print(f"error: {exc}", file=sys.stderr)
                    return 2
                # An old version pin fails to load; --upgrade still needs a root.
                root = profile_mod.conventional_root(existing)
            print(f"note:    using the existing profile at {existing} (root {root})")

    profile_path = root / scaffold.PROFILE_REL

    if args.upgrade:
        if args.baseline:
            print(
                "error: --baseline runs after the upgrade; commit, then run "
                "init --baseline",
                file=sys.stderr,
            )
            return 2
        return _cmd_upgrade(profile_path, args)

    if args.plan:
        if not profile_path.is_file():
            print(
                f"error: no profile at {profile_path}; run `flow.py init` first "
                "(it scaffolds without overwriting anything)",
                file=sys.stderr,
            )
            return 2
        try:
            profile = profile_mod.load(profile_path)
        except ProfileError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return _report_adoption(profile, plan=True, apply_ids=[])

    result = scaffold.apply(
        root, version=__version__, language=args.language, baseline=args.baseline
    )
    print(f"project: {root}")
    if result.profile_existed:
        print(f"profile: {scaffold.relative(root, root / scaffold.PROFILE_REL)} (kept)")
    else:
        print(f"profile: {scaffold.relative(root, root / scaffold.PROFILE_REL)} (created)")
    if result.wrote:
        print(f"wrote:   {', '.join(result.wrote)}")
    if result.kept:
        print(f"kept:    {', '.join(result.kept)}")
    for note in result.notes:
        print(f"note:    {note}")

    profile = profile_mod.load(profile_path)
    return _report_adoption(
        profile,
        plan=bool(args.adopt or args.apply),
        apply_ids=list(args.apply or []),
    )


def _print_check_line(errors: list[str], warnings: list[str]) -> None:
    if errors:
        print(f"check: FAIL — {len(errors)} error(s), {len(warnings)} warning(s); errors block")
    else:
        print(f"check: PASS — no errors ({len(warnings)} warning(s); warnings do not block)")
    _print_issues(errors, warnings)


def _rewrite_agents_language(profile) -> None:
    """A profile that says `zh` and an English router state one fact twice."""
    for name in profile.required_docs:
        if Path(name).name.lower() != "agents.md":
            continue
        path = profile.root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        updated, changed = scaffold.replace_agents_block(text, profile.language)
        if not changed or updated == text:
            continue
        fsio.atomic_write_text(path, updated)
        print(
            f"note:    rewrote the lite-dev routing block in {name} "
            f"({profile.language})"
        )


def _report_adoption(profile, *, plan: bool, apply_ids: list[str]) -> int:
    """Check, ladder, then proposals. The only writer is an explicit --apply."""
    errors, warnings = checks.check_project(profile)
    _print_check_line(errors, warnings)

    advisory = checks.full_level_warning(profile)
    if advisory:
        print(f"warn:    {advisory}")

    if profile.workspace:
        print(
            "workspace: control "
            + (profile.control_path or ".")
            + "; repos "
            + ", ".join(repo.name for repo in profile.workspace_repos)
        )
        for state in _repos(profile):
            if not state["present"]:
                print(
                    f"note:    {state['path']} is not checked out here; its changes "
                    "will be invisible to the gate on this machine"
                )

    resolved = identity.try_resolve_for(profile)
    if resolved is None:
        print('identity: none — run `git config --global lite-dev.owner "Your Name"`')
    else:
        print(f"identity: {resolved[0]} (from {resolved[1]})")

    ladder = adopt.ladder(profile, check_errors=errors)
    for line in adopt.render_ladder(ladder, invocation=_flow_invocation()):
        print(line)

    # `init` reports; it does not judge. A pre-existing broken link is S2 debt,
    # and failing here would make the scaffold look broken while the command did
    # exactly what it promised. `check` and `gate` are the commands that fail.
    if plan:
        proposal_plan = adopt.plan(profile, check_errors=errors)
        if apply_ids:
            try:
                applied = adopt.apply(
                    profile.path, proposal_plan.proposals, apply_ids, root=profile.root
                )
            except (FlowError, OSError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            for proposal_id in applied:
                print(f"applied: {proposal_id}")
            profile = profile_mod.load(profile.path)
            if "project.language" in applied:
                _rewrite_agents_language(profile)
            errors, warnings = checks.check_project(profile)
            _print_check_line(errors, warnings)
            ladder = adopt.ladder(profile, check_errors=errors)
            for line in adopt.render_ladder(ladder, invocation=_flow_invocation()):
                print(line)
            proposal_plan = adopt.plan(profile, check_errors=errors)
            if proposal_plan.proposals:
                print("\nremaining:")
                for line in adopt.render_plan(proposal_plan):
                    print(line)
        else:
            print()
            for line in adopt.render_plan(proposal_plan):
                print(line)

    if not profile_mod.wiring_problems(profile):
        print(
            "\nnext:\n"
            f'  {_flow_invocation()} new --title "..." --type REQ --size S'
        )
    return 0


def _print_version_review(plan: adopt.Plan) -> None:
    """Show what the agent must read before accepting a Y or an X change."""
    if not plan.drift:
        return
    to = plan.review_to or __version__
    low = plan.review_from
    if plan.drift == "patch":
        print(f"review:  patch {low or '?'} -> {to} (no review needed)")
        return
    if plan.drift in ("older-minor", "older-major"):
        print(
            f"review:  this install {to} is older than reviewed {low}; "
            "install the reviewed version"
        )
        return

    print(f"review:  {plan.drift} {low or '?'} -> {to}")
    path = changelog.skill_path(plan.language)
    try:
        items = changelog.between(path, low, to)
    except FlowError as exc:
        print(f"  read:  {exc}")
        print(f"         {changelog.URL}/{path.name}")
        return
    if not items:
        print(f"  read:  {path.name} has no section for {low or '?'}..{to}")
        return
    span = f"{low}..{to}" if low else to
    print(f"  read:  {path.name} {span}")
    for line in changelog.render(items, mark_breaking=(plan.drift == "major")):
        print(f"    {line}" if line else "")
    if plan.drift == "major":
        print("  checklist (references/upgrade.md):")
        for index, item in enumerate(MAJOR_CHECKLIST, 1):
            print(f"    {index}. {item}")


def _cmd_upgrade(profile_path: Path, args) -> int:
    """Propose (and optionally apply) the version-contract migration.

    This path reads the raw profile on purpose: a pin from an older install
    fails to load, and "install a different skill" is not a migration. Z is
    seamless; Y shows the changelog range; X also needs `--accept-major` after
    the checklist.
    """
    if not profile_path.is_file():
        print(f"error: no profile at {profile_path}; run `flow.py init` first", file=sys.stderr)
        return 2
    proposal_plan = adopt.upgrade_plan(profile_path)
    _print_version_review(proposal_plan)
    major = proposal_plan.drift == "major"

    print("upgrade:")
    for line in adopt.render_plan(proposal_plan):
        print(line)

    applicable = [proposal.id for proposal in proposal_plan.proposals if proposal.applicable]
    pending_requires = (
        proposal_plan.find("flow.requires") is not None
        and "flow.requires" not in (args.apply or [])
    )
    if applicable and not args.apply:
        command = f"{_flow_invocation()} init --upgrade"
        if major:
            command += " --accept-major"
        command += " " + " ".join(f"--apply {proposal_id}" for proposal_id in applicable)
        print("next:")
        print(f"  {command}")

    if major and args.apply and not getattr(args, "accept_major", False):
        print(
            "error: crossing a major version requires --accept-major after the "
            "checklist in references/upgrade.md",
            file=sys.stderr,
        )
        return 2

    if args.apply:
        try:
            applied = adopt.apply(
                profile_path,
                proposal_plan.proposals,
                args.apply,
                root=profile_mod.conventional_root(profile_path),
            )
        except (FlowError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        for proposal_id in applied:
            print(f"applied: {proposal_id}")
        if pending_requires:
            print(
                "note:    flow.requires is still pending; the profile will not "
                "load until it is applied"
            )
        proposal_plan = adopt.upgrade_plan(profile_path)
        if proposal_plan.proposals:
            print("\nremaining:")
            for line in adopt.render_plan(proposal_plan):
                print(line)

    try:
        profile = profile_mod.load(profile_path)
    except ProfileError as exc:
        print(f"note:    profile still does not load: {exc}")
        return 1 if args.apply else 0
    return _report_adoption(profile, plan=False, apply_ids=[])


def cmd_reconcile(args) -> int:
    profile = _load_profile(args)
    channel = args.channel
    baseline = (args.since or profile.reconcile_baseline or "").strip()
    if not profile.release_channels:
        if args.channel:
            print(
                f"error: unknown channel '{args.channel}'; no channels are configured",
                file=sys.stderr,
            )
            return 2
        if not baseline:
            print(
                "error: no release channels and no baseline; set "
                '[reconcile] baseline = "<commit>" in the profile (or pass --since) '
                "so the debt of a project without release records can be computed",
                file=sys.stderr,
            )
            return 2
        channel = "baseline"
    if channel is None:
        if len(profile.release_channels) == 1:
            channel = profile.release_channels[0]
        else:
            print(
                f"error: --channel is required when several are configured: "
                f"{', '.join(profile.release_channels)}"
            )
            return 2
    if channel != "baseline" and channel not in profile.release_channels:
        print(
            f"error: unknown channel '{channel}'; configured: "
            f"{', '.join(profile.release_channels)}"
        )
        return 2

    try:
        previous = None if channel == "baseline" else release.tip(profile, channel)
        since = args.since or (previous.source if previous else None)
        if not since and profile.reconcile_baseline:
            since = profile.reconcile_baseline
        bound = profile.channel(channel)
        repo_root = profile.repo_root(
            bound.repo if bound else profile.control_path
        )
        source = (
            "--since"
            if args.since
            else f"the {channel} watermark"
            if previous
            else "[reconcile] baseline"
        )
        if since and not git.has_commit(repo_root, since):
            raise FlowError(
                f"unknown commit {since[:7]} from {source}; it is not in this clone. "
                "Fetch first, or pass a commit from this history."
            )
        if since and not git.is_ancestor(repo_root, since, git.head(repo_root)):
            raise FlowError(
                f"{source} {since[:7]} is not an ancestor of HEAD; this clone is "
                "behind or on a different history. Fetch and pull."
            )
        debt = reconcile.collect(profile, channel, since)
    except (git.GitError, FlowError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                reconcile.as_dict(debt, root=profile.root, verbose=args.verbose),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(reconcile.render(debt, root=profile.root, verbose=args.verbose))
    if debt.blocking:
        print(
            "\nnext: release --record needs --note naming the debt above; "
            "commits that only touch records/archive are now ignored."
        )
    return 0


def cmd_handoff(args) -> int:
    profile = _load_profile(args)
    item = artifacts.find_item(profile, args.id)
    if args.batch and not item.design_path:
        raise FlowError(
            f"{item.id} has no design.md; drop --batch and hand off the item instead"
        )
    print(handoff.render(profile, item, batch=args.batch))
    return 0


def cmd_archive(args) -> int:
    profile = _load_profile(args)
    target = archive.archive(profile, args.id, reason=args.reason or "", force=args.force)
    print(f"archived {args.id}")
    print(f"  {target.relative_to(profile.root)}")
    print(f"  index: {archive.index_path(profile).relative_to(profile.root)}")
    print("next: commit the move so the next session sees the same working set")
    return 0


def cmd_unarchive(args) -> int:
    profile = _load_profile(args)
    target = archive.restore(profile, args.id)
    print(f"restored {args.id}")
    print(f"  {target.relative_to(profile.root)}")
    return 0


def cmd_extensions(args) -> int:
    profile = _load_profile(args)
    print(f"lite-dev {__version__}")
    if not profile.extension_info:
        print("no extensions enabled")
        return 0
    for info in profile.extension_info:
        label = info["name"] + (f" {info['version']}" if info["version"] else "")
        print(f"{label}  [{info['source']}]  requires {info['requires']}")
        if info["description"]:
            print(f"  {info['description']}")
        if info.get("commands"):
            print(f"  commands: {', '.join(info['commands'])}")
        for level, steps in info.get("gate", {}).items():
            print(f"  gate {level} += {', '.join(steps)}")
        if info.get("docs"):
            print(f"  docs required += {', '.join(info['docs'])}")
        if info.get("risk_paths"):
            print(f"  reconcile risk paths += {', '.join(info['risk_paths'])}")
        for detector in info.get("detect", []):
            print(f"  detect {detector['file']} -> {detector['command']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flow.py",
        description="lite-dev flow tool (profile-driven; no project facts inside).",
    )
    parser.add_argument("--version", action="version", version=f"lite-dev {__version__}")
    parser.add_argument("--profile", help="path to docs/flow/profile.toml")

    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser):
        subparser.add_argument(
            "--profile", default=argparse.SUPPRESS, help="path to docs/flow/profile.toml"
        )

    init_parser = subparsers.add_parser(
        "init", help="scaffold the project, then report the adoption ladder"
    )
    init_parser.add_argument(
        "--root", help="project root (defaults to the working directory)"
    )
    init_parser.add_argument(
        "--language", choices=("en", "zh"), default="en", help="prose language"
    )
    init_parser.add_argument(
        "--adopt",
        action="store_true",
        help="scaffold, then print the adoption plan (the old ramp, now derived)",
    )
    init_parser.add_argument(
        "--plan",
        action="store_true",
        help="read-only: propose profile values from the repository",
    )
    init_parser.add_argument(
        "--apply",
        action="append",
        metavar="ID",
        help="write one proposal (repeatable; run --plan to see the ids)",
    )
    init_parser.add_argument(
        "--upgrade",
        action="store_true",
        help="propose a version-pin migration for this install",
    )
    init_parser.add_argument(
        "--accept-major",
        action="store_true",
        help="required to apply an upgrade that crosses a major version",
    )
    init_parser.add_argument(
        "--baseline",
        action="store_true",
        help="record HEAD as [reconcile] baseline; needs a clean tree",
    )
    init_parser.set_defaults(func=cmd_init)

    new_parser = subparsers.add_parser("new", help="create a work item")
    add_common(new_parser)
    new_parser.add_argument("--title", required=True)
    new_parser.add_argument("--type", default="REQ")
    new_parser.add_argument("--size", default="M")
    new_parser.add_argument("--priority", default="P2")
    new_parser.add_argument("--mode", choices=MODES)
    new_parser.add_argument(
        "--owner", help="who owns the item (defaults to $LITE_DEV_OWNER or git config lite-dev.owner)"
    )
    new_parser.set_defaults(func=cmd_new)

    status_parser = subparsers.add_parser("status", help="show derived status for all items")
    add_common(status_parser)
    status_parser.add_argument("--mine", action="store_true", help="only items owned by you")
    status_parser.add_argument(
        "--stale",
        action="store_true",
        help="list open items untouched for more than --days (derived from git)",
    )
    status_parser.add_argument(
        "--days", type=int, default=30, help="staleness threshold in days (default 30)"
    )
    status_parser.add_argument(
        "--repo",
        help="only items whose history mentions them in this repository (. is the "
        "control repo)",
    )
    status_parser.add_argument("--json", action="store_true", help="machine-readable output")
    status_parser.set_defaults(func=cmd_status)

    version_parser = subparsers.add_parser(
        "version", help="show the running skill version and the project's version contract"
    )
    add_common(version_parser)
    version_parser.add_argument("--json", action="store_true", help="machine-readable output")
    version_parser.set_defaults(func=cmd_version)

    check_parser = subparsers.add_parser("check", help="validate artifacts and links")
    add_common(check_parser)
    check_parser.add_argument("--work", help="validate one item instead of the whole project")
    check_parser.add_argument("--json", action="store_true")
    check_parser.set_defaults(func=cmd_check)

    design_parser = subparsers.add_parser(
        "design", help="create design.md from the skill template"
    )
    add_common(design_parser)
    design_parser.add_argument("id")
    design_parser.set_defaults(func=cmd_design)

    ready_parser = subparsers.add_parser("design-ready", help="validate a design and mark it ready")
    add_common(ready_parser)
    ready_parser.add_argument("id")
    ready_parser.set_defaults(func=cmd_design_ready)

    gate_parser = subparsers.add_parser("gate", help="run the project's commands as a gate")
    add_common(gate_parser)
    gate_parser.add_argument("--level", choices=profile_mod.LEVELS, default="l1")
    gate_parser.add_argument("--work", help="work item id; enforces the design rule")
    gate_parser.add_argument(
        "--repo",
        action="append",
        help="limit the gate to this repository (repeatable; . is the control repo)",
    )
    gate_parser.add_argument("--timeout", type=int, default=1800, help="seconds per command")
    gate_parser.set_defaults(func=cmd_gate)

    done_parser = subparsers.add_parser("done", help="close a work item after AC evidence")
    add_common(done_parser)
    done_parser.add_argument("id")
    done_parser.add_argument("--owner", help="who closes it (defaults to your identity)")
    done_parser.set_defaults(func=cmd_done)

    drop_parser = subparsers.add_parser("drop", help="retire an item that will not be delivered")
    add_common(drop_parser)
    drop_parser.add_argument("id")
    drop_parser.add_argument("--reason", help="why it was dropped")
    drop_parser.add_argument("--owner", help="who dropped it (defaults to your identity)")
    drop_parser.set_defaults(func=cmd_drop)

    claim_parser = subparsers.add_parser("claim", help="take ownership of a work item")
    add_common(claim_parser)
    claim_parser.add_argument("id")
    claim_parser.add_argument("--owner", help="new owner (defaults to your identity)")
    claim_parser.add_argument(
        "--takeover",
        action="store_true",
        help="reassign an active item that another person owns (needs --reason)",
    )
    claim_parser.add_argument(
        "--reason", help="why the takeover happened; recorded in the item"
    )
    claim_parser.set_defaults(func=cmd_claim)

    whoami_parser = subparsers.add_parser(
        "whoami", help="show the identity flow.py resolves and where it comes from"
    )
    add_common(whoami_parser)
    whoami_parser.add_argument("--owner", help="identity to report instead of yours")
    whoami_parser.set_defaults(func=cmd_whoami)

    release_parser = subparsers.add_parser("release", help="plan or record a channel release")
    add_common(release_parser)
    release_parser.add_argument("--channel", help="release channel; omit to list channels")
    release_parser.add_argument(
        "--group",
        help="release group: every channel it names, then one index record",
    )
    release_parser.add_argument("--record", action="store_true", help="run the gate and write a record")
    release_parser.add_argument("--rollback", help="rollback target and steps (required with --record)")
    release_parser.add_argument(
        "--confirm",
        help="the human's authorization, recorded when the range touches a risk path",
    )
    release_parser.add_argument("--note", help="accepted debt and other release notes")
    release_parser.add_argument(
        "--confirmed-by", help="who authorized the risk (defaults to the recorder)"
    )
    release_parser.add_argument("--artifact", action="append", help="artefact reference; repeatable")
    release_parser.add_argument("--by", help="who records the release (defaults to your identity)")
    release_parser.add_argument("--since", help="override the watermark commit")
    release_parser.add_argument("--timeout", type=int, default=1800, help="seconds per gate command")
    release_parser.add_argument("--verbose", action="store_true", help="show files in the debt report")
    release_parser.set_defaults(func=cmd_release)

    reconcile_parser = subparsers.add_parser(
        "reconcile", help="show release debt since the channel watermark (advisory)"
    )
    add_common(reconcile_parser)
    reconcile_parser.add_argument("--channel", help="release channel; defaults when only one exists")
    reconcile_parser.add_argument("--since", help="override the watermark commit")
    reconcile_parser.add_argument("--json", action="store_true")
    reconcile_parser.add_argument("--verbose", action="store_true", help="show files per commit")
    reconcile_parser.set_defaults(func=cmd_reconcile)

    extensions_parser = subparsers.add_parser(
        "extensions", help="show enabled extensions and what they add"
    )
    add_common(extensions_parser)
    extensions_parser.set_defaults(func=cmd_extensions)

    handoff_parser = subparsers.add_parser(
        "handoff", help="print a cold-start prompt for a fresh session"
    )
    add_common(handoff_parser)
    handoff_parser.add_argument("id")
    handoff_parser.add_argument(
        "--batch", help="print the implement dispatch for one batch instead"
    )
    handoff_parser.set_defaults(func=cmd_handoff)

    archive_parser = subparsers.add_parser(
        "archive", help="move a closed item out of the working set"
    )
    add_common(archive_parser)
    archive_parser.add_argument("id")
    archive_parser.add_argument("--reason", help="why it was archived (recorded in the index)")
    archive_parser.add_argument(
        "--force", action="store_true", help="archive an item that is not closed"
    )
    archive_parser.set_defaults(func=cmd_archive)

    unarchive_parser = subparsers.add_parser(
        "unarchive", help="move an archived item back into the working set"
    )
    add_common(unarchive_parser)
    unarchive_parser.add_argument("id")
    unarchive_parser.set_defaults(func=cmd_unarchive)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ProfileError, FlowError, git.GitError) as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
