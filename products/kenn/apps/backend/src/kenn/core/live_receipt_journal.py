"""Bounded, non-secret persistence for verified Ableton Live receipts.

Receipts are useful after a companion restart, but confirmation tokens and
their signing metadata must remain process-bound.  This journal therefore
stores an allow-listed receipt projection only, caps the number of records,
and treats persistence failures as non-fatal to the Live safety boundary.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from threading import Lock
from typing import Any


JOURNAL_PATH = Path(
    os.environ.get(
        "KENN_LIVE_RECEIPT_JOURNAL",
        str(Path(__file__).resolve().parents[1] / "data" / "ableton_receipts.jsonl"),
    )
).expanduser()
MAX_RECEIPTS = 500
_JOURNAL_LOCK = Lock()

_RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "receipt_id",
        "action_id",
        "action",
        "idempotency_key",
        "status",
        "verified",
        "write_acknowledgement",
        "retry_safe",
        "timestamp",
        "target",
        "before",
        "requested",
        "readback",
        "error",
        "rolled_back",
        "rollback",
        "step_count",
        "step_receipts",
        "undo_steps",
        "undo_payload",
        "undo_available",
    }
)


def _safe_projection(value: Any, *, key: str = "", nested: bool = False) -> Any:
    """Project JSON values while excluding secrets and free-form evidence."""
    if isinstance(value, dict):
        allowed = _RECEIPT_FIELDS if not nested else None
        return {
            str(name): _safe_projection(item, key=str(name), nested=True)
            for name, item in value.items()
            if (allowed is None or str(name) in allowed)
            and not any(secret in str(name).lower() for secret in ("token", "secret", "nonce", "signature", "password"))
        }
    if isinstance(value, list):
        return [_safe_projection(item, key=key, nested=True) for item in value[:MAX_RECEIPTS]]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _journal_row(receipt: dict[str, Any], session_id: str) -> dict[str, Any]:
    return {
        "schema": "kenn.ableton_receipt_journal.v1",
        "recorded_at": time.time(),
        "session_id": str(session_id or "")[:128],
        "receipt": _safe_projection(receipt),
    }


def record_receipt(receipt: dict[str, Any], *, session_id: str = "") -> bool:
    """Persist one non-secret receipt projection, keeping the newest records."""
    if not isinstance(receipt, dict) or not receipt.get("receipt_id"):
        return False
    # Any receipt (even a failed one) means Live may have changed.
    from kenn.core.live_world_state import invalidate_world_state

    invalidate_world_state()
    row = _journal_row(receipt, session_id)
    try:
        with _JOURNAL_LOCK:
            JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
            existing: list[str] = []
            if JOURNAL_PATH.is_file():
                existing = JOURNAL_PATH.read_text(encoding="utf-8").splitlines()
            existing.append(json.dumps(row, ensure_ascii=True, separators=(",", ":")))
            retained = existing[-MAX_RECEIPTS:]
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=JOURNAL_PATH.parent, prefix=".ableton_receipts.", suffix=".tmp", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write("\n".join(retained) + "\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, JOURNAL_PATH)
            os.chmod(JOURNAL_PATH, 0o600)
        return True
    except (OSError, TypeError, ValueError):
        try:
            if "temporary" in locals() and temporary.exists():
                temporary.unlink()
        except OSError:
            pass
        return False


def list_receipts(*, session_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """Return newest journal entries, optionally scoped to one session."""
    bounded_limit = max(1, min(int(limit), 200))
    try:
        with _JOURNAL_LOCK:
            if not JOURNAL_PATH.is_file():
                return []
            lines = JOURNAL_PATH.read_text(encoding="utf-8").splitlines()
        entries: list[dict[str, Any]] = []
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict) or (session_id and item.get("session_id") != session_id):
                continue
            entries.append(item)
            if len(entries) >= bounded_limit:
                break
        return entries
    except (OSError, TypeError, ValueError):
        return []


__all__ = ["JOURNAL_PATH", "MAX_RECEIPTS", "record_receipt", "list_receipts"]
