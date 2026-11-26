"""Who is writing. Resolved explicitly, never guessed from a machine name."""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import git
from .errors import FlowError

ENV_VAR = "LITE_DEV_OWNER"
CONFIG_KEY = "lite-dev.owner"
CONFIG_LABEL = f"git config {CONFIG_KEY}"
OWNER_LINE = re.compile(r"^(?:owner|负责人)\s*[:：]\s*(.+)$", re.I)


def _from_file(path: Path) -> str:
    """First meaningful line of a per-machine identity file.

    A workspace whose root is not a repository cannot carry `git config`, and
    its top-level files are untracked on purpose. A small untracked file is the
    one place a person can name themselves without versioning the answer.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = OWNER_LINE.match(line)
        value = match.group(1).strip() if match else line
        if value:
            return value
    return ""


def resolve_with_source(
    root: Path,
    override: str | None = None,
    *,
    config_roots: list[Path] | None = None,
    owner_file: str = "",
) -> tuple[str, str]:
    """Identity and where it came from.

    Order: --owner/--by, $LITE_DEV_OWNER, `git config` in each given repository,
    then the project's owner file. There is no fallback to `user.name`: a wrong
    owner is worse than a clear error.
    """
    for value, label in ((override, "--owner"), (os.environ.get(ENV_VAR), ENV_VAR)):
        if value and value.strip():
            return value.strip(), label
    roots = config_roots if config_roots is not None else [root]
    for repo in roots:
        try:
            value = git.config_get(repo, CONFIG_KEY)
        except git.GitError:
            value = ""
        if value.strip():
            return value.strip(), CONFIG_LABEL
    if owner_file:
        value = _from_file(root / owner_file)
        if value:
            return value, owner_file
    raise FlowError(
        "no identity: pass --owner, set "
        f"{ENV_VAR}, run `git config --global {CONFIG_KEY} \"Your Name\"`, "
        'or set [project] owner_file = "<file>" and write your name into it '
        "(one value per person, on every machine)"
    )


def resolve_with_source_for(
    profile, override: str | None = None
) -> tuple[str, str]:
    """Resolve against a loaded profile: control repository, then root."""
    roots = [profile.control_root]
    if profile.root != profile.control_root:
        roots.append(profile.root)
    return resolve_with_source(
        profile.root,
        override,
        config_roots=roots,
        owner_file=profile.owner_file,
    )


def resolve(root: Path, override: str | None = None) -> str:
    return resolve_with_source(root, override)[0]


def resolve_for(profile, override: str | None = None) -> str:
    return resolve_with_source_for(profile, override)[0]


def try_resolve(root: Path, override: str | None = None) -> tuple[str, str] | None:
    """Like `resolve`, but None instead of an error. Commands that only warn use it."""
    try:
        return resolve_with_source(root, override)
    except FlowError:
        return None


def try_resolve_for(profile, override: str | None = None) -> tuple[str, str] | None:
    try:
        return resolve_with_source_for(profile, override)
    except FlowError:
        return None


def normalize(value: str) -> str:
    """Compare owners the way a human reads them: case and spacing do not matter."""
    return " ".join((value or "").split()).casefold()


def same(left: str, right: str) -> bool:
    return normalize(left) == normalize(right)
