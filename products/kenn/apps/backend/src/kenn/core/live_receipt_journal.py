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
        # False only on a failure that stopped before any write; session_context.undo_target walks past those.
        "write_attempted",
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
        # Chat "undo that" reads receipts back from here, so everything propose_undo needs has to survive: without
        # the device order, undoing an insert (Glue on the drum bus, 26 Sept 2026 on real Live) always refused.
        "after",
        "parameter_name",
        "unit",
        "frequency_requested_value",
        "gain_requested_value",
        "requested_devices",
        "readback_devices",
        # HTTP Undo now uses this server record. Clip names and identities must survive, rather than trusting card fields.
        "before_clip",
        "after_clip",
        "source_clip",
        "clip_identity",
    }
)


# Named like a secret but not one. An observation token only names the Live objects a read saw, and the Remote Script
# marks it used once a write spends it, so it authorises nothing. Chat "undo that" reads its receipt from here, and
# until 11 Oct the "token" filter dropped it: Undo then ran with no identity check and wrote to a same-name
# replacement device.
_NOT_SECRET = frozenset({"observation_token"})


def _safe_projection(value: Any, *, key: str = "", nested: bool = False) -> Any:
    """Project JSON values while excluding secrets and free-form evidence."""
    if isinstance(value, dict):
        allowed = _RECEIPT_FIELDS if not nested else None
        return {
            str(name): _safe_projection(item, key=str(name), nested=True)
            for name, item in value.items()
            if (allowed is None or str(name) in allowed)
            and (
                str(name) in _NOT_SECRET
                or not any(secret in str(name).lower() for secret in ("token", "secret", "nonce", "signature", "password"))
            )
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


def receipt_projection(receipt: dict[str, Any]) -> dict[str, Any]:
    """Return the receipt fields retained by the journal for browser comparison."""
    return _safe_projection(receipt)


def find_receipt(receipt_id: str) -> dict[str, Any] | None:
    """Find a recorded receipt and its server-owned session, including after restart."""
    if not receipt_id:
        # A missing ID supplies no authority to restore a value from a client receipt.
        return None
    try:
        with _JOURNAL_LOCK:
            if not JOURNAL_PATH.is_file():
                # Persistence is optional; the action service also retains receipts in memory.
                return None
            lines = JOURNAL_PATH.read_text(encoding="utf-8").splitlines()[-MAX_RECEIPTS:]
        for line in reversed(lines):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                # An interrupted or old malformed row cannot establish Undo ownership.
                continue
            receipt = row.get("receipt") if isinstance(row, dict) else None
            if isinstance(receipt, dict) and receipt.get("receipt_id") == receipt_id:
                return row
            if isinstance(receipt, dict) and isinstance(receipt.get("step_receipts"), list):
                for child in receipt["step_receipts"]:
                    if isinstance(child, dict) and child.get("receipt_id") == receipt_id:
                        # Recipes journal their children inside the parent. Each child inherits the recorded
                        # owner's authority after a companion restart, never a client-supplied session field.
                        return {**row, "receipt": child}
    except (OSError, TypeError, ValueError):
        # Without a readable server record, callers must refuse rather than trust the browser.
        return None
    return None


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


__all__ = ["JOURNAL_PATH", "MAX_RECEIPTS", "record_receipt", "list_receipts", "find_receipt", "receipt_projection"]
