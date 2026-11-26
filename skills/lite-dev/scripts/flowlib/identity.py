"""Who is writing. Resolved explicitly, never guessed from a machine name."""
from __future__ import annotations

import os
from pathlib import Path

from . import git
from .errors import FlowError

ENV_VAR = "LITE_DEV_OWNER"
CONFIG_KEY = "lite-dev.owner"


def resolve(root: Path, override: str | None = None) -> str:
    """--owner / --by, then $LITE_DEV_OWNER, then `git config lite-dev.owner`."""
    for value, label in ((override, "--owner"), (os.environ.get(ENV_VAR), ENV_VAR)):
        if value and value.strip():
            return value.strip()
    try:
        value = git.config_get(root, CONFIG_KEY)
    except git.GitError:
        value = ""
    if value.strip():
        return value.strip()
    raise FlowError(
        "no identity: pass --owner, set "
        f"{ENV_VAR}, or run `git config --global {CONFIG_KEY} \"Your Name\"` "
        "(one value per person, on every machine)"
    )
