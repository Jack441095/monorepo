"""Shared atomic file write for Thursday's small JSON/text data stores.

A crash or kill mid ``Path.write_text()`` leaves a truncated file; the next
``json.loads()`` on load then raises, and every one of these stores' loaders
silently resets to empty on that error -- quietly losing reminders, alerts,
analytics, or watcher state. Write to a tempfile in the same directory and
``os.replace()`` it into place instead, so a reader only ever sees the fully
old or fully new content, never a partial write.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(file_path: Path, content: str) -> None:
    """Write ``content`` to ``file_path`` atomically via tempfile + os.replace."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=str(file_path.parent), prefix=f".tmp_{file_path.name}")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(temp_path, file_path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
