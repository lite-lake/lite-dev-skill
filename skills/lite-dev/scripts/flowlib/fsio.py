"""Atomic writes and a per-clone writer lock. Standard library only.

The working tree is shared by every agent session that runs in the same clone,
so read-modify-write commands take a lock and every write replaces the file in
one step. The lock lives in the system temp directory (keyed by the project
root), so it never shows up as a dirty path and the OS releases it when the
process exits.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from .errors import FlowError

LOCK_TIMEOUT = 10.0
POLL = 0.05


def atomic_write_text(path: Path, text: str) -> None:
    """Write UTF-8 with LF endings, then move it into place atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, path)
        except OSError as exc:
            raise FlowError(
                f"cannot replace {path}: {exc}; close the file if an editor holds it"
            ) from exc
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def write_target(path: Path) -> Path:
    """Where a write must land: the link target when `path` is a symlink.

    `os.replace` swaps the link itself, which silently detaches a workspace that
    keeps one authoritative file and symlinks it from elsewhere. Following the
    link writes the file the reader actually reads.
    """
    if path.is_symlink():
        return path.resolve()
    return path


def lock_path(root: Path) -> Path:
    digest = hashlib.sha1(str(root.resolve()).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"lite-dev-{digest}.lock"


@contextmanager
def project_lock(root: Path, timeout: float = LOCK_TIMEOUT):
    """Serialize writers inside one clone. Different clones get different locks."""
    path = lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = open(path, "a+b")
    except OSError as exc:
        raise FlowError(f"cannot open the writer lock {path}: {exc}") from exc
    try:
        _acquire(handle, root, timeout)
        try:
            yield
        finally:
            _release(handle)
    finally:
        handle.close()


def _acquire(handle, root: Path, timeout: float) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    deadline = time.monotonic() + timeout
    while True:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise FlowError(
                    f"another flow.py process is writing to {root}; "
                    f"waited {timeout:.0f}s. Retry when it finishes."
                )
            time.sleep(POLL)


def _release(handle) -> None:
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
