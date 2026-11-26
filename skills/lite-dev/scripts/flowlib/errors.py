"""User-facing failures that must become `error: ...` instead of a traceback."""
from __future__ import annotations


class FlowError(Exception):
    """A failure the tool can explain: print it and exit 2."""
