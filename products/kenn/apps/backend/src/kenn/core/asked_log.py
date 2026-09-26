"""What testers typed when KENN had to ask, kept on their Mac.

The rules and the planner have gone as far as made-up wording can take them (26 Sept 2026: a planner trained on
synthetic phrasings memorised them). Real wording is what's missing, so each time KENN asks back or refuses, this keeps
what was typed, what KENN said, and what the tester said next. It stays in KENN's data folder, capped, readable only by
the user, and leaves the Mac only inside a diagnostics file the tester chose to include it in.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from threading import Lock
from typing import Any

ASKED_LOG_PATH = Path(
    os.environ.get("KENN_ASKED_LOG", str(Path(__file__).resolve().parents[1] / "data" / "asked_log.jsonl"))
).expanduser()
MAX_ROWS = 300
# The next message only counts as the reply if it comes soon after; later it's a new thought.
REPLY_WINDOW_S = 300
ASKED_STATUSES = frozenset({"clarification_required", "refused", "unsupported", "invalid", "blocked"})
_LOCK = Lock()


def _path() -> Path:
    configured = os.environ.get("KENN_ASKED_LOG")
    return Path(configured).expanduser() if configured else ASKED_LOG_PATH


def _session_key(session_id: str) -> str:
    return hashlib.sha256(str(session_id).encode("utf-8")).hexdigest()[:12]


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".asked-", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write("".join(json.dumps(row, ensure_ascii=True) + "\n" for row in rows[-MAX_ROWS:]))
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def reply_status(reply: dict[str, Any]) -> str:
    """What a chat reply amounted to: a command status, or clarification_required when KENN asked back."""
    for candidate in (reply, (reply.get("orchestration") or {}).get("result") if isinstance(reply.get("orchestration"), dict) else None):
        if isinstance(candidate, dict) and str(candidate.get("status") or "") in ASKED_STATUSES:
            return str(candidate["status"])
    if reply.get("route") == "clarify":
        return "clarification_required"
    orchestrated = (reply.get("orchestration") or {}).get("result") if isinstance(reply.get("orchestration"), dict) else None
    return str((orchestrated or {}).get("status") or reply.get("route") or reply.get("status") or "")


def record(session_id: str, command: str, result: dict[str, Any], *, now: float | None = None) -> bool:
    """Fill in the reply to the last question in this session, and keep this one if KENN had to ask."""
    said = " ".join(str(command or "").split())[:500]
    if not said:
        return False
    now = time.time() if now is None else now
    session = _session_key(session_id)
    status = str(result.get("status") or "")
    try:
        with _LOCK:
            path = _path()
            rows = _read(path)
            pending = next((row for row in reversed(rows) if row.get("session") == session), None)
            if pending and pending.get("said") == said and now - float(pending.get("timestamp") or 0) <= 10:
                return False  # the chat route can try the same message twice; it's one request, not its own reply
            changed = False
            if pending and pending.get("next_said") is None and now - float(pending.get("timestamp") or 0) <= REPLY_WINDOW_S:
                pending["next_said"] = said
                pending["next_status"] = status[:64]
                changed = True
            if status in ASKED_STATUSES:
                rows.append({"timestamp": now, "session": session, "said": said,
                             "kenn_said": " ".join(str(result.get("answer") or "").split())[:500], "status": status[:64],
                             "next_said": None, "next_status": None})
                changed = True
            if changed:
                _write(path, rows)
            return changed
    except OSError:
        return False


def entries() -> list[dict[str, Any]]:
    """What's kept, without the session keys (they only link a question to its reply)."""
    with _LOCK:
        return [{key: value for key, value in row.items() if key != "session"} for row in _read(_path())]


def clear() -> int:
    with _LOCK:
        path = _path()
        count = len(_read(path))
        if path.exists():
            path.unlink()
        return count


__all__ = ["ASKED_STATUSES", "MAX_ROWS", "REPLY_WINDOW_S", "clear", "entries", "record", "reply_status"]
