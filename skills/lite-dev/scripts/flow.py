#!/usr/bin/env python3
"""lite-dev flow tool.

Usage (from the project root):
    python3 <skill>/scripts/flow.py status
    python3 <skill>/scripts/flow.py new --title "Export CSV" --type REQ --size M
    python3 <skill>/scripts/flow.py check
    python3 <skill>/scripts/flow.py design-ready <ID>
    python3 <skill>/scripts/flow.py gate --level l1 [--work <ID>]
    python3 <skill>/scripts/flow.py done <ID>
    python3 <skill>/scripts/flow.py release --channel staging
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
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from flowlib import __version__, artifacts, checks, commands, git, reconcile, release  # noqa: E402
from flowlib import profile as profile_mod  # noqa: E402
from flowlib.profile import MODES, PRIORITIES, SIZES, TYPES, ProfileError  # noqa: E402

SKILL_DIR = SCRIPTS.parent
TEMPLATE = SKILL_DIR / "templates" / "item.md"

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
    "clarified": "write design.md, or start the change if no design is required",
    "designing": "finish design.md, then run design-ready {id}",
    "ready": "implement the batches, run the gate, then done {id}",
}


def _load_profile(args) -> profile_mod.Profile:
    return profile_mod.load(getattr(args, "profile", None))


def _slugify(title: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title.strip(), flags=re.UNICODE)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned[:32].rstrip("-")


def _next_id(profile: profile_mod.Profile, item_type: str, created: str) -> str:
    existing = {item.id for item in artifacts.all_items(profile)}
    existing.update(path.name for path in profile.work_path.glob("*") if path.is_dir())
    for sequence in range(1, 1000):
        candidate = profile.id_format.format(
            date=created.replace("-", ""),
            type=item_type,
            seq=sequence,
            owner=profile.owner,
        )
        if candidate not in existing and not any(
            name == candidate or name.startswith(candidate + "-") for name in existing
        ):
            return candidate
    raise ProfileError("cannot allocate an item id: sequence space exhausted")


def cmd_new(args) -> int:
    profile = _load_profile(args)
    item_type = args.type.upper()
    size = args.size.upper()
    priority = args.priority.upper()
    if item_type not in TYPES:
        raise SystemExit(f"error: --type must be one of {', '.join(TYPES)}")
    if size not in SIZES:
        raise SystemExit("error: --size must be one of S, M, L")
    if priority not in PRIORITIES:
        raise SystemExit(f"error: --priority must be one of {', '.join(PRIORITIES)}")
    mode = args.mode or ("two-phase" if size == "L" else "one-shot")
    if mode not in MODES:
        raise SystemExit("error: --mode must be one-shot or two-phase")

    created = checks.today()
    item_id = _next_id(profile, item_type, created)
    title = " ".join(args.title.split())
    slug = _slugify(title)
    directory = profile.work_path / (f"{item_id}-{slug}" if slug else item_id)
    directory.mkdir(parents=True, exist_ok=False)

    text = TEMPLATE.read_text(encoding="utf-8")
    for token, value in {
        "<ID>": item_id,
        "<TITLE>": title,
        "<TYPE>": item_type,
        "<PRIORITY>": priority,
        "<SIZE>": size,
        "<MODE>": mode,
        "<DATE>": created,
    }.items():
        text = text.replace(token, value)
    (directory / "item.md").write_text(text, encoding="utf-8")

    print(f"created {item_id}")
    print(f"  {(directory / 'item.md').relative_to(profile.root)}")
    print("next: clarify the requirement, then set '- Status: clarified'")
    return 0


def cmd_status(args) -> int:
    profile = _load_profile(args)
    items = artifacts.all_items(profile)
    if not items:
        print(f"{profile.name}: no work items")
        return 0

    items.sort(key=lambda item: (STATUS_ORDER.get(item.status, 9), item.id))
    rows = []
    for item in items:
        design = "ready" if item.design_status == "ready" else ("draft" if item.design_path else "-")
        rows.append(
            [
                item.id,
                item.meta.get("type", "-"),
                item.size or "-",
                item.mode or "-",
                item.status,
                f"{item.ac_done}/{item.ac_total}",
                design,
            ]
        )
    headers = ["ID", "TYPE", "SIZE", "MODE", "STATUS", "AC", "DESIGN"]
    widths = [max(len(str(row[i])) for row in rows + [headers]) for i in range(len(headers))]
    print(f"{profile.name} ({profile.path.relative_to(profile.root)})")
    print("  ".join(header.ljust(widths[i]) for i, header in enumerate(headers)))
    for row in rows:
        print("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))

    counts: dict[str, int] = {}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    summary = ", ".join(f"{key} {counts[key]}" for key in STATUS_ORDER if key in counts)
    print(f"\n{len(items)} item(s): {summary}")

    next_lines = []
    for item in items:
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


def cmd_check(args) -> int:
    profile = _load_profile(args)
    errors, warnings = checks.check_project(profile)
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
        print(f"PASS: no errors ({len(warnings)} warning(s))")
    else:
        print(f"FAIL: {len(errors)} error(s), {len(warnings)} warning(s)")
    _print_issues(errors, warnings)
    return 0 if ok else 1


def cmd_design_ready(args) -> int:
    profile = _load_profile(args)
    item = artifacts.find_item(profile, args.id)
    errors = checks.design_errors(item, profile)
    if errors:
        print("FAIL: the design is not ready")
        for error in errors:
            print(f"  - {error}")
        return 1
    artifacts.set_frontmatter_value(item.design_path, "status", "ready")
    print(f"PASS: design marked ready ({item.design_path.relative_to(profile.root)})")
    print(f"next: implement the batches, then flow.py gate --level l1 --work {item.id}")
    return 0


def cmd_gate(args) -> int:
    profile = _load_profile(args)
    errors, warnings = checks.check_project(profile)
    if errors:
        print("FAIL: static checks must pass before the gate runs")
        _print_issues(errors, warnings)
        return 1
    for warning in warnings:
        print(f"warn: {warning}")

    if args.work:
        item = artifacts.find_item(profile, args.work)
        if item.size in profile.design_required_for and item.design_status != "ready":
            print(
                f"FAIL: {item.id} is size {item.size} and needs a ready design "
                "(flow.py design-ready <ID>)"
            )
            return 1

    try:
        return commands.run_gate(profile, args.level, timeout=args.timeout)
    except ProfileError as exc:
        print(f"error: {exc}")
        return 2


def cmd_done(args) -> int:
    profile = _load_profile(args)
    item = artifacts.find_item(profile, args.id)

    closed = (item.meta.get("closed") or "").strip()
    if closed:
        print(f"{item.id} is already closed ({closed})")
        return 0

    errors = checks.item_errors(item, profile)
    if item.ac_done != item.ac_total:
        open_ids = ", ".join(entry["id"] for entry in item.ac if not entry["done"])
        errors.append(f"unchecked AC: {open_ids}")
    if item.size in profile.design_required_for and item.design_status != "ready":
        errors.append(f"size {item.size} needs a ready design before it can be done")
    if errors:
        print("FAIL: cannot close the work item")
        for error in errors:
            print(f"  - {error}")
        return 1

    artifacts.set_frontmatter_value(item.path, "closed", checks.today())
    print(f"done {item.id} ({checks.today()})")
    print(f"  AC {item.ac_done}/{item.ac_total}")
    print(f"  design: {item.design_status or '-'}")
    print(f"  {item.path.relative_to(profile.root)}")
    return 0


def _commit_text(commits: list[git.Commit], since: str | None, total: int) -> str:
    if not commits:
        return "None"
    origin = since[:7] if since else "the first commit"
    lines = [f"{total} commit(s) since {origin}"]
    lines.extend(f"- `{commit.short}` {commit.subject}" for commit in commits)
    return "\n".join(lines)


def _item_text(profile: profile_mod.Profile, commits: list[git.Commit]) -> str:
    ids: list[str] = []
    for commit in commits:
        for item_id in profile.id_pattern.findall(f"{commit.subject}\n{commit.body}"):
            if item_id not in ids:
                ids.append(item_id)
    return "\n".join(f"- {item_id}" for item_id in ids) if ids else "None"


def _record_path(profile: profile_mod.Profile, channel: str, day: str) -> Path:
    return release.next_path(profile, channel, day)


def cmd_release(args) -> int:
    profile = _load_profile(args)
    if not profile.release_channels:
        print("no release channels configured; add [release] channels in the profile")
        return 0
    if not args.channel:
        print(f"channels: {', '.join(profile.release_channels)}")
        for channel in profile.release_channels:
            record = release.latest(profile, channel)
            if record:
                print(
                    f"  {channel}: last {record.date} {record.source[:7]} "
                    f"({record.path.relative_to(profile.root)})"
                )
            else:
                print(f"  {channel}: no record")
        return 0
    if args.channel not in profile.release_channels:
        print(
            f"error: unknown channel '{args.channel}'; configured: "
            f"{', '.join(profile.release_channels)}"
        )
        return 2

    channel = args.channel
    try:
        git.ensure_repo(profile.root)
        branch = git.branch(profile.root)
        head = git.head(profile.root)
        previous = release.latest(profile, channel)
        since = args.since or (previous.source if previous else None)
        commits = git.commits(profile.root, since)
        debt = reconcile.collect(profile, channel, since)
    except git.GitError as exc:
        print(f"error: {exc}")
        return 2

    day = checks.today()
    target = _record_path(profile, channel, day)
    print(f"channel: {channel}")
    print(f"source: {head[:7]} ({branch or 'detached HEAD'})")
    print(
        f"previous: {previous.source[:7] + ' (' + previous.date + ')' if previous else 'none'}"
    )
    print(f"commits: {len(commits)}")
    print(f"gate: {profile.release_gate_level} (runs on --record)")
    print(f"record: {target.relative_to(profile.root)}")
    if debt.dirty:
        print(f"dirty tree: {len(debt.dirty)} path(s); recording will be refused")
    if debt.blocking:
        print(
            f"debt: {len(debt.no_item) + len(debt.missing_item)} commit(s) without a "
            "work item; --note is required to record"
        )

    if not args.record:
        print(f"\n{reconcile.render(debt, root=profile.root, verbose=args.verbose)}")
        print("\nnext: add --record --rollback \"<target and steps>\" [--note \"...\"]")
        return 0

    errors: list[str] = []
    if not args.rollback or not args.rollback.strip():
        errors.append("--rollback is required and must describe the rollback target and steps")
    if debt.dirty:
        errors.append("working tree is dirty; commit or stash before recording a release")
    if branch and branch in profile.release_channels:
        errors.append(
            f"current branch '{branch}' is a release channel; record from the main line"
        )
    if debt.blocking and not (args.note or "").strip():
        errors.append(
            "there are commits without work items; record the debt in --note "
            "(do not fabricate history)"
        )
    static_errors, static_warnings = checks.check_project(profile)
    if static_errors:
        errors.extend(f"check: {error}" for error in static_errors)
    if errors:
        print("\nFAIL: release not recorded")
        for error in errors:
            print(f"  - {error}")
        return 1
    for warning in static_warnings:
        print(f"warn: {warning}")

    try:
        results = commands.execute(
            profile, profile.release_gate_level, timeout=args.timeout
        )
    except ProfileError as exc:
        print(f"error: {exc}")
        return 2
    if commands.print_results(profile.release_gate_level, results) != 0:
        print("FAIL: release not recorded")
        return 1

    record = release.render(
        channel=channel,
        day=day,
        source=head,
        previous=previous.source if previous else "none",
        gate=commands.summary(profile.release_gate_level, results),
        commits=_commit_text(commits, since, debt.total),
        items=_item_text(profile, commits),
        rollback=args.rollback.strip(),
        notes=(args.note or "None").strip(),
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(record, encoding="utf-8")
    print(f"recorded {target.relative_to(profile.root)}")
    print(f"  source {head[:7]}  previous {previous.source[:7] if previous else 'none'}")
    print(f"  gate {profile.release_gate_level} PASS")
    return 0


def cmd_reconcile(args) -> int:
    profile = _load_profile(args)
    if not profile.release_channels:
        print("no release channels configured; add [release] channels in the profile")
        return 2
    channel = args.channel
    if not channel:
        if len(profile.release_channels) == 1:
            channel = profile.release_channels[0]
        else:
            print(
                f"error: --channel is required when several are configured: "
                f"{', '.join(profile.release_channels)}"
            )
            return 2
    if channel not in profile.release_channels:
        print(
            f"error: unknown channel '{channel}'; configured: "
            f"{', '.join(profile.release_channels)}"
        )
        return 2

    try:
        previous = release.latest(profile, channel)
        since = args.since or (previous.source if previous else None)
        debt = reconcile.collect(profile, channel, since)
    except git.GitError as exc:
        print(f"error: {exc}")
        return 2

    if args.json:
        print(json.dumps(reconcile.as_dict(debt), ensure_ascii=False, indent=2))
        return 0
    print(reconcile.render(debt, root=profile.root, verbose=args.verbose))
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
        if info["commands"]:
            print(f"  commands: {', '.join(info['commands'])}")
        for level, steps in info["gate"].items():
            print(f"  gate {level} += {', '.join(steps)}")
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

    new_parser = subparsers.add_parser("new", help="create a work item")
    add_common(new_parser)
    new_parser.add_argument("--title", required=True)
    new_parser.add_argument("--type", default="REQ")
    new_parser.add_argument("--size", default="M")
    new_parser.add_argument("--priority", default="P2")
    new_parser.add_argument("--mode", choices=MODES)
    new_parser.set_defaults(func=cmd_new)

    status_parser = subparsers.add_parser("status", help="show derived status for all items")
    add_common(status_parser)
    status_parser.set_defaults(func=cmd_status)

    check_parser = subparsers.add_parser("check", help="validate artifacts and links")
    add_common(check_parser)
    check_parser.add_argument("--json", action="store_true")
    check_parser.set_defaults(func=cmd_check)

    ready_parser = subparsers.add_parser("design-ready", help="validate a design and mark it ready")
    add_common(ready_parser)
    ready_parser.add_argument("id")
    ready_parser.set_defaults(func=cmd_design_ready)

    gate_parser = subparsers.add_parser("gate", help="run the project's commands as a gate")
    add_common(gate_parser)
    gate_parser.add_argument("--level", choices=profile_mod.LEVELS, default="l1")
    gate_parser.add_argument("--work", help="work item id; enforces the design rule")
    gate_parser.add_argument("--timeout", type=int, default=1800, help="seconds per command")
    gate_parser.set_defaults(func=cmd_gate)

    done_parser = subparsers.add_parser("done", help="close a work item after AC evidence")
    add_common(done_parser)
    done_parser.add_argument("id")
    done_parser.set_defaults(func=cmd_done)

    release_parser = subparsers.add_parser("release", help="plan or record a channel release")
    add_common(release_parser)
    release_parser.add_argument("--channel", help="release channel; omit to list channels")
    release_parser.add_argument("--record", action="store_true", help="run the gate and write a record")
    release_parser.add_argument("--rollback", help="rollback target and steps (required with --record)")
    release_parser.add_argument("--note", help="accepted debt and other release notes")
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ProfileError as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
