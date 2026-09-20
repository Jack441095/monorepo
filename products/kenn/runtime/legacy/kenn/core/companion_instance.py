"""Single-instance ownership for the local KENN companion.

The companion and AbletonOSC share a fixed local reply port.  Starting a
second process must therefore fail before it advertises a partially healthy
HTTP service.  An OS-held advisory lock is preferable to a PID file: kernel
ownership disappears automatically after crashes and common termination
signals, while the allow-listed metadata remains useful to an operator.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOCK_SCHEMA = "kenn.companion_instance.v1"
LOCK_PATH_ENV = "KENN_INSTANCE_LOCK_PATH"


class CompanionAlreadyRunning(RuntimeError):
    """Raised when another process owns the companion lock."""

    def __init__(self, path: Path, owner: dict[str, Any] | None = None) -> None:
        self.path = path
        self.owner = owner or {}
        pid = self.owner.get("pid")
        started_at = self.owner.get("started_at")
        details = []
        if isinstance(pid, int) and pid > 0:
            details.append(f"PID {pid}")
        if isinstance(started_at, str) and started_at:
            details.append(f"started {started_at}")
        suffix = f" ({', '.join(details)})" if details else ""
        super().__init__(
            "Another KENN companion already owns the local instance lock"
            f"{suffix}. Stop that exact instance before retrying."
        )


def default_lock_path() -> Path:
    override = os.environ.get(LOCK_PATH_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    uid = os.getuid() if hasattr(os, "getuid") else 0
    return Path(tempfile.gettempdir()) / f"kenn-companion-{uid}.lock"


def _read_metadata(handle: Any) -> dict[str, Any] | None:
    try:
        handle.seek(0)
        value = json.loads(handle.read() or "{}")
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


class CompanionInstanceLock:
    """Own the per-user KENN companion lock for this process lifetime."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or default_lock_path()).expanduser().resolve()
        self._handle: Any | None = None
        self.metadata: dict[str, Any] | None = None

    def acquire(self, *, host: str, port: int) -> dict[str, Any]:
        if self._handle is not None:
            raise RuntimeError("KENN companion instance lock is already acquired")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(self.path, flags, 0o600)
        os.fchmod(fd, 0o600)
        handle = os.fdopen(fd, "r+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            owner = _read_metadata(handle)
            handle.close()
            raise CompanionAlreadyRunning(self.path, owner) from exc
        metadata = {
            "schema": LOCK_SCHEMA,
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "host": host,
            "port": int(port),
        }
        handle.seek(0)
        handle.truncate()
        json.dump(metadata, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        self._handle = handle
        self.metadata = metadata
        return dict(metadata)

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        self.metadata = None
        if handle is None:
            return
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self) -> "CompanionInstanceLock":
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


__all__ = [
    "CompanionAlreadyRunning",
    "CompanionInstanceLock",
    "LOCK_PATH_ENV",
    "LOCK_SCHEMA",
    "default_lock_path",
]
