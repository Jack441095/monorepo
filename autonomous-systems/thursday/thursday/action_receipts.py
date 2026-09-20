"""Atomic idempotency receipts for confirmed Thursday mutations."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thursday.runtime_paths import DATA_DIR


class ReceiptConflict(ValueError):
    """An idempotency key was reused for a different action."""


@dataclass(frozen=True)
class ActionReceipt:
    receipt_id: str
    session_id: str
    service_id: str
    request_hash: str
    status: str
    response_text: str
    created_at: float
    completed_at: float | None


@dataclass(frozen=True)
class ClaimResult:
    claimed: bool
    receipt: ActionReceipt


def receipt_id_for_token(token: str) -> str:
    """Derive a non-secret stable receipt ID from a confirmation token."""
    return "act-" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


def request_hash(service_id: str, text: str) -> str:
    normalized = f"{service_id}\n{text.strip()}".encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def _db_path() -> Path:
    configured = os.environ.get("THURSDAY_ACTION_RECEIPTS_DB", "").strip()
    if configured:
        return Path(configured).expanduser()
    return DATA_DIR / "action_receipts.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS action_receipts (
               receipt_id TEXT PRIMARY KEY,
               session_id TEXT NOT NULL,
               service_id TEXT NOT NULL,
               request_hash TEXT NOT NULL,
               status TEXT NOT NULL CHECK (status IN ('processing', 'completed')),
               response_text TEXT NOT NULL DEFAULT '',
               created_at REAL NOT NULL,
               completed_at REAL
           )"""
    )
    return conn


def _from_row(row: sqlite3.Row) -> ActionReceipt:
    return ActionReceipt(
        receipt_id=str(row["receipt_id"]),
        session_id=str(row["session_id"]),
        service_id=str(row["service_id"]),
        request_hash=str(row["request_hash"]),
        status=str(row["status"]),
        response_text=str(row["response_text"] or ""),
        created_at=float(row["created_at"]),
        completed_at=(
            float(row["completed_at"]) if row["completed_at"] is not None else None
        ),
    )


def get_receipt(receipt_id: str, *, session_id: str) -> ActionReceipt | None:
    """Fetch a receipt only when it belongs to the requesting session."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM action_receipts WHERE receipt_id = ? AND session_id = ?",
            (receipt_id, session_id),
        ).fetchone()
    return _from_row(row) if row else None


def claim_action(
    receipt_id: str, *, session_id: str, service_id: str, text: str
) -> ClaimResult:
    """Atomically claim one action or return its existing receipt."""
    digest = request_hash(service_id, text)
    created_at = time.time()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM action_receipts WHERE receipt_id = ?", (receipt_id,)
        ).fetchone()
        if row:
            receipt = _from_row(row)
            if (
                receipt.session_id != session_id
                or receipt.service_id != service_id
                or receipt.request_hash != digest
            ):
                conn.rollback()
                raise ReceiptConflict(
                    "The action receipt was already used for a different request."
                )
            conn.commit()
            return ClaimResult(False, receipt)
        conn.execute(
            """INSERT INTO action_receipts
               (receipt_id, session_id, service_id, request_hash, status,
                response_text, created_at, completed_at)
               VALUES (?, ?, ?, ?, 'processing', '', ?, NULL)""",
            (receipt_id, session_id, service_id, digest, created_at),
        )
        conn.commit()
    return ClaimResult(
        True,
        ActionReceipt(
            receipt_id=receipt_id,
            session_id=session_id,
            service_id=service_id,
            request_hash=digest,
            status="processing",
            response_text="",
            created_at=created_at,
            completed_at=None,
        ),
    )


def complete_action(receipt_id: str, *, response_text: str) -> ActionReceipt:
    """Complete a claimed action exactly once and preserve its replay response."""
    completed_at = time.time()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM action_receipts WHERE receipt_id = ?", (receipt_id,)
        ).fetchone()
        if not row:
            conn.rollback()
            raise LookupError(f"Unknown action receipt: {receipt_id}")
        receipt = _from_row(row)
        if receipt.status == "completed":
            conn.commit()
            return receipt
        conn.execute(
            """UPDATE action_receipts
               SET status = 'completed', response_text = ?, completed_at = ?
               WHERE receipt_id = ? AND status = 'processing'""",
            (response_text, completed_at, receipt_id),
        )
        row = conn.execute(
            "SELECT * FROM action_receipts WHERE receipt_id = ?", (receipt_id,)
        ).fetchone()
        conn.commit()
    return _from_row(row)


def recent_receipts(
    *, since: float | None = None, limit: int = 20
) -> list[ActionReceipt]:
    """List the most recent receipts, optionally filtered by creation time.

    Read-only helper for reporting surfaces such as the daily brief.
    """
    query = "SELECT * FROM action_receipts"
    params: list[Any] = []
    if since is not None:
        query += " WHERE created_at >= ?"
        params.append(float(since))
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(int(limit))
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_from_row(row) for row in rows]
