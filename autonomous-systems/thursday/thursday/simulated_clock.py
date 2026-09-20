"""Injectable deterministic clock for Thursday V2-I.

Long-horizon behaviour must be testable without waiting real days. All
V2-I time-sensitive control-plane logic receives a Clock instead of
calling ``time.time()`` directly.

Clocks
------
SystemClock
    Thin wrapper over wall time (production default).
SimulatedClock
    Deterministic clock starting at an explicit epoch. Advances only
    forward — going backwards raises, preserving monotonic ordering.
    Day boundaries are computed against a FIXED UTC offset (default 0)
    so tests never depend on the host timezone or DST.

Persistence
-----------
``to_state`` / ``from_state`` allow a crashed long-horizon run to resume
at exactly the simulated instant it died. Restoring an older state than
the live clock would rewind time and is refused.

Authority note
--------------
The clock measures time only. It confers no authority: expiry decisions
made with it still fail closed (expired approval = rejected).
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from typing import Any

SECONDS_PER_DAY = 86400.0


class ClockProtocol:
    """Structural interface every clock satisfies."""

    def now(self) -> float:
        raise NotImplementedError

    def advance(self, seconds: float) -> None:
        raise NotImplementedError


class SystemClock(ClockProtocol):
    """Wall-clock production implementation."""

    def now(self) -> float:
        return _time.time()

    def advance(self, seconds: float) -> None:
        raise TypeError("SystemClock cannot be advanced; inject a SimulatedClock in tests")


@dataclass
class SimulatedClock(ClockProtocol):
    """Deterministic forward-only simulated clock.

    Parameters
    ----------
    start_epoch : float
        Initial simulated time (seconds since Unix epoch).
    tz_offset_hours : float
        Fixed timezone offset used for day-boundary arithmetic.
        Default 0 (UTC). Deliberately NOT the host timezone: day
        boundaries must be reproducible on any machine.
    """

    start_epoch: float
    tz_offset_hours: float = 0.0
    _current: float | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._current is None:
            self._current = float(self.start_epoch)

    # ------------------------------------------------------------------
    # Reading time
    # ------------------------------------------------------------------

    def now(self) -> float:
        return self._current

    def day(self) -> int:
        """Zero-based simulated day number since the clock's start."""
        delta = self._current - self.start_epoch
        return int(delta // SECONDS_PER_DAY)

    def day_start(self, epoch: float | None = None) -> float:
        """Start of the local (fixed-offset) day containing epoch."""
        e = self._current if epoch is None else epoch
        shifted = e + self.tz_offset_hours * 3600.0
        midnight = (shifted // SECONDS_PER_DAY) * SECONDS_PER_DAY
        return midnight - self.tz_offset_hours * 3600.0

    def day_end(self, epoch: float | None = None) -> float:
        return self.day_start(epoch) + SECONDS_PER_DAY

    # ------------------------------------------------------------------
    # Advancing time
    # ------------------------------------------------------------------

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("SimulatedClock cannot move backwards")
        self._current += float(seconds)

    def advance_days(self, days: float) -> None:
        self.advance(days * SECONDS_PER_DAY)

    def set_to_next_day_start(self) -> None:
        """Jump to the start of the next local day."""
        target = self.day_end()
        if target <= self._current:
            target += SECONDS_PER_DAY
        self._current = target

    # ------------------------------------------------------------------
    # Persistence / restart continuity
    # ------------------------------------------------------------------

    def to_state(self) -> dict[str, Any]:
        return {
            "start_epoch": self.start_epoch,
            "current_epoch": self._current,
            "tz_offset_hours": self.tz_offset_hours,
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "SimulatedClock":
        restored = cls(
            start_epoch=state["start_epoch"],
            tz_offset_hours=state.get("tz_offset_hours", 0.0),
        )
        restored._current = float(state["current_epoch"])
        return restored

    def restore_if_newer(self, state: dict[str, Any]) -> bool:
        """Restore persisted state only if it is not older than live time."""
        saved = float(state["current_epoch"])
        if saved < self._current:
            return False   # Refusing to rewind time
        self._current = saved
        return True


__all__ = [
    "SECONDS_PER_DAY",
    "ClockProtocol",
    "SystemClock",
    "SimulatedClock",
]
