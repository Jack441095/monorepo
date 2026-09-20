"""Authoritative persistence for multi-turn diagnostic loops.

Clients receive loop state for display, but continuation always resolves the
server-stored copy by ID. Optimistic updates prevent two observations from
advancing the same hypothesis concurrently.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from kenn.core.diagnostic_loop import LOOP_SCHEMA, validate_diagnostic_loop
from kenn.core.session_memory import DB_PATH


MAX_LOOPS_PER_SESSION = 64


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS diagnostic_loops (
            loop_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            status TEXT NOT NULL,
            state_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS diagnostic_loops_session_updated "
        "ON diagnostic_loops(session_id, updated_at DESC)"
    )
    return conn


class DiagnosticLoopStore:
    """Store and atomically advance only valid KENN diagnostic state."""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)

    def start(self, loop: dict[str, Any]) -> dict[str, Any]:
        checked = validate_diagnostic_loop(loop)
        if not checked.get("ok"):
            return {"ok": False, "errors": checked.get("errors", [])}
        loop_id = str(loop.get("loop_id") or "")[:128]
        session_id = str(loop.get("session_id") or "")[:128]
        if not loop_id or not session_id:
            return {"ok": False, "errors": ["Diagnostic loop and session identities are required."]}
        state_json = json.dumps(loop, sort_keys=True)
        conn = _connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO diagnostic_loops(loop_id, session_id, status, state_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    loop_id, session_id, str(loop.get("status") or ""), state_json,
                    str(loop.get("created_at") or ""), str(loop.get("updated_at") or ""),
                ),
            )
            conn.execute(
                """
                DELETE FROM diagnostic_loops
                WHERE loop_id IN (
                    SELECT loop_id FROM diagnostic_loops
                    WHERE session_id = ?
                    ORDER BY updated_at DESC LIMIT -1 OFFSET ?
                )
                """,
                (session_id, MAX_LOOPS_PER_SESSION),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return {"ok": False, "errors": ["Diagnostic loop identity already exists."]}
        finally:
            conn.close()
        return {"ok": True, "loop": loop}

    def load(self, loop_id: str) -> dict[str, Any] | None:
        conn = _connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT state_json FROM diagnostic_loops WHERE loop_id = ?",
                (str(loop_id)[:128],),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        try:
            state = json.loads(row["state_json"])
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(state, dict) or state.get("schema") != LOOP_SCHEMA:
            return None
        return state

    def update(self, *, expected: dict[str, Any], updated: dict[str, Any]) -> dict[str, Any]:
        checked = validate_diagnostic_loop(updated)
        if not checked.get("ok"):
            return {"ok": False, "errors": checked.get("errors", [])}
        if expected.get("loop_id") != updated.get("loop_id"):
            return {"ok": False, "errors": ["Diagnostic loop identity cannot change."]}
        if expected.get("session_id") != updated.get("session_id"):
            return {"ok": False, "errors": ["Diagnostic loop session cannot change."]}
        previous_json = json.dumps(expected, sort_keys=True)
        updated_json = json.dumps(updated, sort_keys=True)
        conn = _connect(self.db_path)
        try:
            cursor = conn.execute(
                "UPDATE diagnostic_loops SET status = ?, state_json = ?, updated_at = ? "
                "WHERE loop_id = ? AND state_json = ?",
                (
                    str(updated.get("status") or ""), updated_json,
                    str(updated.get("updated_at") or ""), str(updated.get("loop_id") or ""),
                    previous_json,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        if cursor.rowcount != 1:
            return {
                "ok": False,
                "errors": ["Diagnostic loop changed concurrently; reload it before recording another result."],
            }
        return {"ok": True, "loop": updated}


__all__ = ["DiagnosticLoopStore", "MAX_LOOPS_PER_SESSION"]
