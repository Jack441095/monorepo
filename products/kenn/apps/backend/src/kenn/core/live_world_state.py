"""Shared, versioned world model for the companion process.

The version is monotonic and only advances when the model's fingerprint
changes, so two answers with the same version describe the same Live state.
Every verified KENN write invalidates the cache (see live_receipt_journal), so
KENN never answers from a picture older than its own last change.

AbletonOSC listener pushes are deliberately not used yet: they arrive on the
same reply port and address as ordinary reads, so the shared request/response
socket could mistake a push for a pending read's reply. That needs a
dedicated push port in the Remote Script first (tracker B2).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from kenn.core.live_world_model import read_world_model

DEFAULT_MAX_AGE_SECONDS = 2.0


class WorldModelState:
    def __init__(self, reader: Callable[[Any], dict[str, Any]] = read_world_model) -> None:
        self._reader = reader
        self._lock = threading.Lock()
        self._model: dict[str, Any] | None = None
        self._read_at = 0.0
        self._version = 0
        self._fingerprint: str | None = None
        self._dirty = True
        self._client: Any = None

    @property
    def version(self) -> int:
        return self._version

    def invalidate(self) -> None:
        with self._lock:
            self._dirty = True

    def current(self, client: Any, *, max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
                force: bool = False) -> dict[str, Any]:
        with self._lock:
            fresh = (self._model is not None and not self._dirty and not force
                     and self._client is client
                     and (time.monotonic() - self._read_at) < max_age_seconds)
            if not fresh:
                model = self._reader(client)
                self._client = client
                self._read_at = time.monotonic()
                self._dirty = False
                if model.get("status") == "connected":
                    if model.get("fingerprint") != self._fingerprint:
                        self._version += 1
                        self._fingerprint = model.get("fingerprint")
                    self._model = model
                else:
                    self._model = None
                    return dict(model)
            result = dict(self._model or {})
            result["version"] = self._version
            result["age_seconds"] = round(time.monotonic() - self._read_at, 3)
            return result


world_state = WorldModelState()


def invalidate_world_state() -> None:
    world_state.invalidate()


__all__ = ["DEFAULT_MAX_AGE_SECONDS", "WorldModelState", "invalidate_world_state", "world_state"]
