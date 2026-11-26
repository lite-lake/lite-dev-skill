"""Scaffold a project for lite-dev: profile, entry documents, router.

Adoption is the first step of the flow and the one with the most manual steps:
the profile must carry this install's version and the project's mainline, the
entry documents must exist before `check` can pass, and the agent instructions
must route to the skill. Every writer here is additive: a file that exists is
never replaced, and a routing block is inserted rather than a file rewritten.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import fsio, git
from . import profile as profile_mod
from .errors import FlowError
from .profile import Profile, ProfileError

AGENTS_BEGIN = "<!-- lite-dev:begin -->"
AGENTS_END = "<!-- lite-dev:end -->"
PROFILE_REL = Path("docs") / "flow" / "profile.toml"
TEMPLATE = profile_mod.SKILL_ROOT / "profile.template.toml"
SKILL_PATH = "<path-to-lite-dev-skill>/skills/lite-dev"


@dataclass
class Scaffold:
    """What `init` did, in the order it happened, so the caller can print it."""

    root: Path
    profile_existed: bool = False
    wrote: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def compat_range(version: str) -> str:
    """The range a freshly scaffolded profile pins: this line, not the next one."""
    parts = version.split(".")
    try:
        major, minor = int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        raise ProfileError(f"cannot derive a compatibility range from version {version!r}")
    upper = f"{major + 1}.0" if major else f"{major}.{minor + 1}"
    return f">={version},<{upper}"


def _toml_string(value: str) -> str:
    """A TOML basic string. JSON escaping is a subset TOML accepts."""
    return json.dumps(value, ensure_ascii=False)


def render_profile(
    template: str, *, name: str, language: str, version: str, mainline: str
) -> str:
    """Fill the four project-specific lines of profile.template.toml.

    Substitution is guarded: a template that no longer has one of these lines is
    a shape change, and silently scaffolding a profile that pins nothing would
    leave every machine on a different gate.
    """
    substitutions = (
        (r'(?m)^name = "my-project"$', f"name = {_toml_string(name)}"),
        (r'(?m)^language = "en"', f'language = "{language}"'),
        (r"(?m)^requires = \">=.*\"$", f'requires = "{compat_range(version)}"'),
        (r'(?m)^mainline = ".*"$', f"mainline = {_toml_string(mainline)}"),
    )
    text = template
    for pattern, replacement in substitutions:
        text, count = re.subn(pattern, replacement, text)
        if count != 1:
            raise ProfileError(
                "cannot scaffold from profile.template.toml: the line matching "
                f"{pattern!r} appears {count} time(s). Copy the template by hand "
                "and set `name`, `requires`, and `mainline`."
            )
    return text


def with_baseline(text: str, sha: str) -> str:
    """Set [reconcile] baseline, creating the table when the profile lacks one."""
    line = f'baseline = "{sha}"'
    header = re.search(r"(?m)^\[reconcile\][^\n]*$", text)
    if header is None:
        return text.rstrip("\n") + f"\n\n[reconcile]\n{line}\n"
    following = re.search(r"(?m)^\[", text[header.end():])
    end = header.end() + following.start() if following else len(text)
    existing = re.search(r"(?m)^baseline\s*=.*$", text[header.end():end])
    if existing:
        start = header.end() + existing.start()
        stop = header.end() + existing.end()
        return text[:start] + line + text[stop:]
    return text[:header.end()] + "\n" + line + text[header.end():]


def agents_block(language: str = "en") -> str:
    if language == "zh":
        lines = [
            AGENTS_BEGIN,
            "## lite-dev",
            "",
            "本项目使用 lite-dev。实现、修复、设计或发布任何东西之前，先读",
            f"`{SKILL_PATH}/SKILL.md`。",
            "",
            f"- 每次会话先跑 `python3 {SKILL_PATH}/scripts/flow.py status`。",
            "- profile 是 `docs/flow/profile.toml`；命令与门禁层级都在那里。",
            "- 工作项在 `docs/work/`。不要手写状态，工具会推导。",
            "- 门禁跑项目自己的命令。不要另发明一套。",
            AGENTS_END,
            "",
        ]
        return "\n".join(lines)
    return "\n".join(
        [
            AGENTS_BEGIN,
            "## lite-dev",
            "",
            f"This project uses lite-dev. Read `{SKILL_PATH}/SKILL.md` before",
            "implementing, fixing, designing, or releasing anything.",
            "",
            f"- Start every session with `python3 {SKILL_PATH}/scripts/flow.py status`.",
            "- The profile is `docs/flow/profile.toml`; commands and gate levels live there.",
            "- Work items live in `docs/work/`. Never edit a status by hand; the tool derives it.",
            "- The gate runs this project's own commands. Do not invent a different one.",
            AGENTS_END,
            "",
        ]
    )


def with_agents_block(text: str, language: str = "en") -> tuple[str, str]:
    """(new text, action): inserted, or unchanged.

    An existing file keeps its title at the top: the block goes after the first
    H1 and the blank line that follows it, so the router reads first without
    rewriting the page.
    """
    if AGENTS_BEGIN in text:
        return text, "routing block present"
    if not text.strip():
        return agents_block(language), "routing block added"
    lines = text.splitlines(keepends=True)
    if lines and lines[0].startswith("# "):
        split = 1
        while split < len(lines) and not lines[split].strip():
            split += 1
        head = "".join(lines[:split])
        tail = "".join(lines[split:])
        return head + agents_block(language) + "\n" + tail, "routing block inserted"
    return agents_block(language) + "\n" + text, "routing block prepended"


def readme_text(name: str, language: str = "en") -> str:
    if language == "zh":
        return (
            f"# {name}\n"
            "\n"
            "用一段话说明这个项目是什么。替换这一行。\n"
            "\n"
            "- [文档](docs/README.md)\n"
            "- [Agent 指令](AGENTS.md)\n"
            "\n"
            "本项目使用 lite-dev：`docs/flow/profile.toml` 存放命令与门禁层级，\n"
            "`AGENTS.md` 说明一次会话如何开始。\n"
        )
    return (
        f"# {name}\n"
        "\n"
        "What this project is, in one paragraph. Replace this line.\n"
        "\n"
        "- [Documentation](docs/README.md)\n"
        "- [Agent instructions](AGENTS.md)\n"
        "\n"
        "This project uses lite-dev: `docs/flow/profile.toml` holds the commands\n"
        "and gate levels, and `AGENTS.md` says how a session starts.\n"
    )


def docs_readme_text(name: str, language: str = "en") -> str:
    if language == "zh":
        return (
            f"# {name} 文档\n"
            "\n"
            "这里是项目文档的入口。每个事实只有一处归口，其他文档链接它；每个目录\n"
            "索引都能从这里到达。\n"
            "\n"
            "- 开发流程：`flow/profile.toml` 是 profile；协议在 lite-dev skill 里。\n"
            "- 工作项：[work](work/README.md)。它们是记录仓，由 `flow.py status`\n"
            "  列出。\n"
        )
    return (
        f"# {name} documentation\n"
        "\n"
        "This is the entry point for the project's documents. Each fact has one\n"
        "home; every other document links it, and every directory index is reachable\n"
        "from here.\n"
        "\n"
        "- Development flow: `flow/profile.toml` is the profile; the protocol is in\n"
        "  the lite-dev skill.\n"
        "- Work items: [work](work/README.md). They are a record store; `flow.py\n"
        "  status` lists them.\n"
    )


def work_readme_text(language: str = "en") -> str:
    if language == "zh":
        return (
            "# 工作项\n"
            "\n"
            "每个目录是一个条目，按 `created` 日期归档到对应月份；由 `flow.py new`\n"
            "创建。不要重命名或移动条节目录，也不要手写状态：工具从 `## Clarify`、\n"
            "`design.md` 和 `closed:` 推导。\n"
            "\n"
            "- `item.md` —— 需求、AC 与批次记录。\n"
            "- `design.md` —— profile 要求设计时由 `flow.py design <ID>` 生成。\n"
            "- `test-report.md` —— 累计证据，每个 AC 一行；缺少它的条目 `done` 会拒绝。\n"
            "- `implementation.md` —— 可选；两阶段执行的批次记录。\n"
            "\n"
            "开启的条目有归属人。用 `flow.py claim <ID>` 重新指派；接管别人的条目需要\n"
            '`--takeover --reason "..."`。\n'
        )
    return (
        "# Work items\n"
        "\n"
        "One directory per item, filed by the month in its `created` date; `flow.py\n"
        "new` creates it. Do not rename or move an item directory, and never write a\n"
        "status by hand: the tool derives it from `## Clarify`, `design.md`, and\n"
        "`closed:`.\n"
        "\n"
        "- `item.md` — the request, its AC, and the batch log.\n"
        "- `design.md` — written by `flow.py design <ID>` when the profile requires one.\n"
        "- `test-report.md` — cumulative evidence, one row per AC; `done` refuses an\n"
        "  item without it.\n"
        "- `implementation.md` — optional; the batch log during a two-phase run.\n"
        "\n"
        "An open item has an owner. Reassign it with `flow.py claim <ID>`; taking over\n"
        "another person's item needs `--takeover --reason \"...\"`.\n"
    )


def stub_text(path: Path) -> str:
    return f"# {path.stem}\n\nReplace this line with what this document is.\n"


def _write(path: Path, text: str, result: Scaffold) -> None:
    """Write to the file a reader actually reads, and say where that was.

    A workspace keeps one authoritative document and symlinks it from every
    place that needs it. Replacing the link would detach the copy; writing
    through it updates the authority. The other two notes are the two ways a
    write can look successful and still be invisible to teammates: a target
    outside the project, and a target no repository tracks.
    """
    target = fsio.write_target(path)
    root = result.root.resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise FlowError(
            f"{relative(result.root, path)} is a symlink to {target}, which is outside "
            "the project root; write it where the file actually lives"
        )
    fsio.atomic_write_text(target, text)
    label = relative(result.root, path)
    result.wrote.append(label)
    if target != path:
        result.notes.append(
            f"{label}: written through the symlink to {relative(root, target)}"
        )
    try:
        inside = git.repo_of(target) is not None
    except git.GitError:
        inside = True
    if not inside:
        result.notes.append(
            f"untracked: {relative(root, target)} is not inside a git work tree; "
            "commit it from the repository that owns this directory, or a teammate "
            "will not see it"
        )


def _doc_text(root: Path, profile: Profile, name: str) -> str:
    path = Path(name)
    language = profile.language
    if path.name.lower() == "agents.md":
        return agents_block(language)
    if path.name.lower() == "readme.md":
        if path.parent == Path("."):
            return readme_text(root.name or "project", language)
        if path.parent == Path(profile.docs_dir):
            return docs_readme_text(root.name or "project", language)
    return stub_text(path)


def apply(
    root: Path,
    *,
    version: str,
    language: str = "en",
    baseline: bool = False,
) -> Scaffold:
    """Write what is missing. Never overwrite a file that exists."""
    result = Scaffold(root=root)
    profile_path = root / PROFILE_REL
    if profile_path.is_file():
        result.profile_existed = True
        result.kept.append(relative(root, profile_path))
    else:
        template = TEMPLATE.read_text(encoding="utf-8")
        text = render_profile(
            template,
            name=root.name or "project",
            language=language,
            version=version,
            mainline=git.default_branch(root),
        )
        fsio.atomic_write_text(profile_path, text)

    loaded: Profile = profile_mod.load(profile_path)
    for name in loaded.required_docs:
        path = root / name
        if path.is_file():
            if path.name.lower() == "agents.md":
                text, action = with_agents_block(
                    path.read_text(encoding="utf-8"), loaded.language
                )
                if action == "routing block present":
                    result.kept.append(relative(root, path))
                else:
                    _write(path, text, result)
                    result.notes.append(f"{relative(root, path)}: {action}")
            else:
                result.kept.append(relative(root, path))
            continue
        _write(path, _doc_text(root, loaded, path.relative_to(root).as_posix()), result)

    work_readme = loaded.work_path / "README.md"
    if work_readme.is_file():
        result.kept.append(relative(root, work_readme))
    else:
        _write(work_readme, work_readme_text(loaded.language), result)

    if baseline:
        result.notes.append(_baseline_note(root, profile_path, loaded.control_root))
    return result


def _baseline_note(
    root: Path, profile_path: Path, control_root: Path | None = None
) -> str:
    """Set the baseline only on a clean tree, so it names a commit people meant.

    The baseline is a commit in the control repository: that is the history
    `reconcile` reads when a project has no release record yet.
    """
    control = control_root or root
    if not git.is_repo(control):
        return (
            "baseline: not set — the control directory is not a git repository; "
            "`reconcile` needs history. Run `git init` there, commit the scaffold, "
            "then `flow.py init --baseline`"
        )
    dirty = git.dirty(control)
    if dirty:
        return (
            "baseline: not set — the control repository has uncommitted paths; commit "
            "them, then run `flow.py init --baseline` so the baseline names a "
            "commit you meant ("
            + ", ".join(dirty[:3])
            + (f" (+{len(dirty) - 3} more)" if len(dirty) > 3 else "")
            + ")"
        )
    try:
        sha = git.head(control)
    except git.GitError:
        return (
            "baseline: not set — the repository has no commit yet; commit the "
            "scaffold, then run `flow.py init --baseline`"
        )
    text = profile_path.read_text(encoding="utf-8")
    fsio.atomic_write_text(profile_path, with_baseline(text, sha))
    return (
        f"[reconcile] baseline = {sha[:7]} — history before adoption is recorded "
        "as a baseline, not as debt"
    )
