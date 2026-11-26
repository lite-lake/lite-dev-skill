"""The time code in an item id: milliseconds since local midnight.

One clock read per item, so the date and the code cannot disagree across
midnight. The code is a label and a sort key, not a coordination fact: two
clones that stamp the same millisecond get the same code, and `check` reports
the duplicate id instead of merging them.
"""
from __future__ import annotations

from datetime import datetime

from .profile import TIME_ALPHABET, TIME_LEN

MS_PER_DAY = 86_400_000


def now() -> datetime:
    """The single clock read for one allocation."""
    return datetime.now()


def ms_since_midnight(moment: datetime) -> int:
    return (
        (moment.hour * 3600 + moment.minute * 60 + moment.second) * 1000
        + moment.microsecond // 1000
    )


def encode(ms: int) -> str:
    """Fixed-width code, so ids sort lexicographically in creation order."""
    if not 0 <= ms < MS_PER_DAY:
        raise ValueError(f"milliseconds since midnight out of range: {ms}")
    chars: list[str] = []
    value = ms
    for _ in range(TIME_LEN):
        value, rest = divmod(value, len(TIME_ALPHABET))
        chars.append(TIME_ALPHABET[rest])
    return "".join(reversed(chars))


class Clock:
    """Hands out increasing codes for one process.

    A coarse clock, or two allocations in the same millisecond, cannot produce
    the same code twice: the next request starts at the previous code plus one.
    """

    def __init__(self) -> None:
        self._last: tuple[str, int] | None = None

    def allocate(self, created: str, moment: datetime) -> int:
        ms = ms_since_midnight(moment)
        if self._last is not None:
            last_date, last_ms = self._last
            if last_date == created and ms <= last_ms:
                ms = last_ms + 1
        return ms

    def commit(self, created: str, ms: int) -> None:
        self._last = (created, ms)
