from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterator, List, Optional, Tuple


def _truthy_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    raw = raw.strip().lower()
    return raw not in {"", "0", "false", "no", "off"}


@dataclass
class StartupProfiler:
    """
    Minimal stage timer for cold-start profiling.

    Enable by either:
      - passing enabled=True
      - or setting env var `AUDIOGEN_STARTUP_PROFILE=1`
    """

    emit: Callable[[str], None] = print
    enabled: bool = field(default_factory=lambda: _truthy_env("AUDIOGEN_STARTUP_PROFILE", False))
    _marks: List[Tuple[str, float]] = field(default_factory=list)
    _t0: float = field(default_factory=time.perf_counter)

    def mark(self, name: str) -> None:
        if not self.enabled:
            return
        self._marks.append((str(name), time.perf_counter()))

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dt_ms = (time.perf_counter() - t0) * 1000.0
            self.emit(f"[startup] {name}: {dt_ms:7.1f} ms")

    def report(self, *, title: str = "startup marks") -> None:
        if not self.enabled:
            return
        if not self._marks:
            self.emit("[startup] (no marks)")
            return
        self.emit(f"[startup] {title}")
        last = self._t0
        for name, t in self._marks:
            self.emit(f"[startup]  - {name}: {(t - last) * 1000.0:7.1f} ms")
            last = t
        self.emit(f"[startup]  = total: {(last - self._t0) * 1000.0:7.1f} ms")


def get_startup_profiler(emit: Optional[Callable[[str], None]] = None) -> StartupProfiler:
    return StartupProfiler(emit=emit or print)

