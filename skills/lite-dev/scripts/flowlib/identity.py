"""Who is writing. Resolved explicitly, never guessed from a machine name."""
from __future__ import annotations

import os
from pathlib import Path

from . import git
from .errors import FlowError

ENV_VAR = "LITE_DEV_OWNER"
CONFIG_KEY = "lite-dev.owner"
CONFIG_LABEL = f"git config {CONFIG_KEY}"


def resolve_with_source(root: Path, override: str | None = None) -> tuple[str, str]:
    """Identity and where it came from: --owner/--by, $LITE_DEV_OWNER, then git config."""
    for value, label in ((override, "--owner"), (os.environ.get(ENV_VAR), ENV_VAR)):
        if value and value.strip():
            return value.strip(), label
    try:
        value = git.config_get(root, CONFIG_KEY)
    except git.GitError:
        value = ""
    if value.strip():
        return value.strip(), CONFIG_LABEL
    raise FlowError(
        "no identity: pass --owner, set "
        f"{ENV_VAR}, or run `git config --global {CONFIG_KEY} \"Your Name\"` "
        "(one value per person, on every machine)"
    )


def resolve(root: Path, override: str | None = None) -> str:
    return resolve_with_source(root, override)[0]


def try_resolve(root: Path, override: str | None = None) -> tuple[str, str] | None:
    """Like resolve, but None instead of an error. Commands that only warn use it."""
    try:
        return resolve_with_source(root, override)
    except FlowError:
        return None


def normalize(value: str) -> str:
    """Compare owners the way a human reads them: case and spacing do not matter."""
    return " ".join((value or "").split()).casefold()


def same(left: str, right: str) -> bool:
    return normalize(left) == normalize(right)
