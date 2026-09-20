"""Thursday DAW Project File Watcher — Monitors active DAW session files.

Supports Ableton Live (.als), Logic Pro (.logicx, .logic), Pro Tools (.ptx, .ptf),
Reaper (.rpp), and FL Studio (.flp). Publishes DAW_PROJECT_UPDATED events to EventBus.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from thursday.events import Event, EventPriority, get_event_bus

logger = logging.getLogger(__name__)

DAW_EXTENSIONS = {
    ".als": "Ableton Live",
    ".logicx": "Logic Pro",
    ".logic": "Logic Pro",
    ".ptx": "Pro Tools",
    ".ptf": "Pro Tools",
    ".rpp": "Reaper",
    ".flp": "FL Studio",
}


@dataclass
class DAWSessionInfo:
    """Metadata representation of an active or recent DAW project session."""

    daw_type: str
    session_name: str
    file_path: str
    last_modified: float
    metadata: dict[str, Any] = field(default_factory=dict)


class DAWProjectWatcher:
    """Monitors directories for DAW session updates and notifies the EventBus."""

    def __init__(
        self,
        watch_dir: str | Path | None = None,
        poll_interval: float = 5.0,
        debounce_seconds: float = 30.0,
    ):
        if watch_dir is None:
            watch_dir = os.environ.get("THURSDAY_DAW_WATCH_DIR", str(Path.home() / "Documents" / "DAW_Sessions"))
        self.watch_dir = Path(watch_dir)
        self.poll_interval = poll_interval
        # DAWs like Ableton/Logic autosave every few seconds while a session
        # is actively being worked on -- without a debounce window, each
        # autosave bumps mtime and re-fires a fresh DAW_PROJECT_UPDATED event
        # every poll cycle. debounce_seconds is the minimum gap enforced
        # between two events for the *same* file; a still-newer mtime inside
        # that window updates the tracked mtime (so no writes are lost /
        # re-fired later) but does not itself emit an event.
        self.debounce_seconds = debounce_seconds
        self._seen_sessions: dict[str, float] = {}
        self._last_event_at: dict[str, float] = {}
        self._is_running = False

    def scan_once(self, *, now: float | None = None) -> list[DAWSessionInfo]:
        """Scan the watch directory once for new or modified DAW project files.

        ``now`` is injectable for deterministic debounce-window tests; real
        callers never pass it and get ``time.time()``.
        """
        if not self.watch_dir.exists():
            return []

        current_time = now if now is not None else time.time()
        updated_sessions: list[DAWSessionInfo] = []
        try:
            for root, _, files in os.walk(self.watch_dir):
                for fname in files:
                    ext = Path(fname).suffix.lower()
                    if ext in DAW_EXTENSIONS:
                        fpath = Path(root) / fname
                        mtime = fpath.stat().st_mtime
                        key = str(fpath)
                        prev_mtime = self._seen_sessions.get(key)

                        if prev_mtime is None or mtime > prev_mtime:
                            self._seen_sessions[key] = mtime

                            last_event_at = self._last_event_at.get(key)
                            if (
                                last_event_at is not None
                                and current_time - last_event_at < self.debounce_seconds
                            ):
                                # Newer write recorded, but inside the
                                # debounce window since the last emitted
                                # event for this file -- collapse it.
                                continue

                            self._last_event_at[key] = current_time
                            daw_name = DAW_EXTENSIONS[ext]
                            info = DAWSessionInfo(
                                daw_type=daw_name,
                                session_name=fpath.stem,
                                file_path=str(fpath),
                                last_modified=mtime,
                                metadata={"extension": ext, "size_bytes": fpath.stat().st_size},
                            )
                            updated_sessions.append(info)

                            # Publish event to EventBus
                            bus = get_event_bus()
                            bus.publish(Event(
                                topic="daw_session",
                                payload={
                                    "daw_type": daw_name,
                                    "session_name": fpath.stem,
                                    "file_path": str(fpath),
                                    "last_modified": mtime,
                                },
                                priority=EventPriority.NORMAL,
                                event_type="DAW_PROJECT_UPDATED",
                            ))
        except Exception as exc:
            logger.error("DAWProjectWatcher scan error: %s", exc, exc_info=True)

        return updated_sessions
