"""Session Manager — persistent session memory for Thursday.

Stores conversation turns, active context, and inferred intents
in lightweight JSON files under Thursday/sessions/.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from thursday.runtime_paths import SESSION_DIR, SESSION_FILE
MAX_TURNS = 20


def _session_path(session_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
        raise ValueError("Invalid Thursday session ID.")
    return SESSION_DIR / f"{session_id}.json"


def _now() -> str:
    return datetime.now().isoformat()


def _empty_session(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "created_at": _now(),
        "updated_at": _now(),
        "turns": [],
        "feedback_state": {},
        "context": {
            "current_client": None,
            "current_project": None,
            "current_invoice": None,
            "pending_action": None,
            "pending_confirmation": None,
            "pending_confirmations": {},
            "pending_plans": {},
            "pending_suggestion": None,
            "last_action_receipt": None,
            "active_session_id": None,
            "last_search_query": None,
            "last_report": None,
            "current_mix_review": None,
            "current_audio_scan": None,
            "current_audiogen_job": None,
            "last_analyzed_track": None,
            "last_kenn_question": None,
            "active_voice": "thursday",
        },
    }


# ─── Public API ───────────────────────────────────────────────────────────


def get_or_create_session(session_id: str | None = None) -> dict:
    """Load existing session or create a new one."""
    if session_id is None or session_id.strip() == "":
        session_id = _read_session_file()

    # Handle empty or invalid session IDs
    if not session_id or session_id.strip() == "":
        session_id = str(uuid.uuid4())[:12]
        session = _empty_session(session_id)
        _save_session(session)
        _write_session_file(session_id)
        return session

    try:
        _session_path(session_id)
    except ValueError:
        session_id = str(uuid.uuid4())[:12]

    if load_session(session_id) is not None:
        return _load_session(session_id)

    # Create new session
    session = _empty_session(session_id)
    _save_session(session)
    _write_session_file(session_id)
    return session


def load_session(session_id: str) -> dict | None:
    """Load a specific session by ID. Returns None if not found."""
    try:
        _session_path(session_id)  # Validate ID format
    except ValueError:
        return None
    try:
        conn = _get_db()
        row = conn.execute("SELECT 1 FROM assistant_sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is not None:
            return _load_session(session_id)
        # Fallback to legacy JSON file
        legacy_path = SESSION_DIR / f"{session_id}.json"
        if legacy_path.exists():
            return _load_session(session_id)
    except Exception:
        logger.warning("load_session failed for session %s", session_id, exc_info=True)
    return None


def save_session(session: dict) -> None:
    """Persist session to disk."""
    session["updated_at"] = _now()
    _save_session(session)


def add_turn(
    session: dict,
    role: str,
    text: str,
    intent: str | None = None,
    service_used: str | None = None,
    entities: dict | None = None,
) -> dict:
    """Add a conversation turn to the session."""
    turn = {
        "role": role,
        "text": text,
        "timestamp": _now(),
        "intent": intent,
        "service_used": service_used,
        "entities": entities or {},
    }
    session.setdefault("turns", [])
    session["turns"].append(turn)

    if role == "thursday":
        session["feedback_state"] = {
            "turn_id": turn["timestamp"],
            "service_id": service_used or "",
            "intent_name": intent or "",
            "response_text": str(text or "")[:500],
            "created_epoch": time.time(),
            "recorded": False,
        }

    # Trim to max turns
    if len(session["turns"]) > MAX_TURNS:
        session["turns"] = session["turns"][-MAX_TURNS:]

    session["updated_at"] = _now()
    _save_session(session)
    return session


def update_context(session: dict, updates: dict) -> dict:
    """Merge updates into session context."""
    session["context"].update(updates)
    session["updated_at"] = _now()
    _save_session(session)
    return session


def get_context(session: dict) -> dict:
    """Get current session context."""
    return session.get("context", {})


def clear_context(session: dict) -> dict:
    """Reset context to defaults."""
    session["context"] = _empty_session(session["session_id"])["context"]
    session["updated_at"] = _now()
    _save_session(session)
    return session


def delete_session(session_id: str) -> bool:
    """Delete a session from the authoritative SQLite store.

    Sessions live in the ``assistant_sessions`` SQLite table (see
    ``_save_session``/``_load_session``) since the migration off per-session
    JSON files; deleting only the legacy ``SESSION_DIR / f"{id}.json"`` path
    (the previous behaviour of ``server.py``'s ``DELETE /session/<id>``) was a
    no-op against real, SQLite-backed sessions -- the file it targeted no
    longer exists for any session created after the migration, so the row
    (and the actual conversation/context data) was never removed.

    Uses a parameterized query scoped to exactly one ``session_id`` (never a
    prefix or pattern), so deleting one session cannot affect any other.

    Returns:
        True if a session (SQLite row and/or a leftover legacy JSON file) was
        actually found and deleted; False if no session with that id existed.

    Raises:
        ValueError: if ``session_id`` is not a valid session id.
    """
    _session_path(session_id)  # validates the id format; raises ValueError if malformed

    conn = _get_db()
    try:
        cursor = conn.execute(
            "DELETE FROM assistant_sessions WHERE session_id = ?", (session_id,)
        )
        conn.commit()
        deleted = cursor.rowcount > 0
    finally:
        conn.close()

    # A session created before the SQLite migration (or never re-saved since)
    # may still have a legacy per-session JSON file; remove it too so no
    # stale copy of the deleted session's data survives on disk.
    legacy_path = SESSION_DIR / f"{session_id}.json"
    if legacy_path.exists():
        try:
            legacy_path.unlink()
            deleted = True
        except OSError:
            logger.warning(
                "delete_session: found but could not remove legacy JSON file for %s",
                session_id,
                exc_info=True,
            )

    return deleted


def _get_db() -> sqlite3.Connection:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    db_path = SESSION_DIR / "thursday_sessions.sqlite3"
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assistant_sessions (
            session_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.row_factory = sqlite3.Row
    return conn


def list_sessions() -> list[dict]:
    """List all stored sessions with summary info."""
    sessions = []
    try:
        conn = _get_db()
        rows = conn.execute("SELECT session_id, state, created_at, updated_at FROM assistant_sessions ORDER BY updated_at DESC").fetchall()
        for row in rows:
            try:
                data = json.loads(row["state"])
                sessions.append({
                    "session_id": row["session_id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "num_turns": len(data.get("turns", [])),
                })
            except Exception:
                logger.warning("Skipping corrupt session row %s in list_sessions", row["session_id"], exc_info=True)
                continue
    except Exception:
        logger.warning("list_sessions query failed, returning partial/empty list", exc_info=True)
    return sessions


def new_session() -> dict:
    """Force-create a new session, updating the session file."""
    session_id = str(uuid.uuid4())[:12]
    session = _empty_session(session_id)
    _save_session(session)
    _write_session_file(session_id)
    return session


def _load_session(session_id: str) -> dict:
    """Load session data from SQLite database, with legacy JSON fallback & migration."""
    try:
        conn = _get_db()
        row = conn.execute("SELECT state FROM assistant_sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is not None:
            loaded = json.loads(row["state"])
        else:
            # Fallback to legacy JSON file
            legacy_path = SESSION_DIR / f"{session_id}.json"
            if legacy_path.exists():
                try:
                    loaded = json.loads(legacy_path.read_text(encoding="utf-8"))
                    # Save to DB to migrate it
                    state_str = json.dumps(loaded, indent=2)
                    conn.execute(
                        """INSERT OR REPLACE INTO assistant_sessions (session_id, state, created_at, updated_at)
                           VALUES (?, ?, ?, ?)""",
                        (session_id, state_str, loaded.get("created_at", _now()), _now())
                    )
                    conn.commit()
                    try:
                        legacy_path.unlink()
                    except OSError:
                        pass
                except Exception:
                    raise OSError(f"Failed to migrate legacy JSON for {session_id}")
            else:
                raise OSError(f"Session {session_id} not found")

        # Migrate older sessions whenever new context fields are introduced.
        defaults = _empty_session(session_id)
        loaded.setdefault("session_id", session_id)
        loaded.setdefault("created_at", defaults["created_at"])
        loaded.setdefault("updated_at", defaults["updated_at"])
        loaded.setdefault("turns", [])
        loaded.setdefault("feedback_state", {})
        loaded.setdefault("context", {})
        for key, value in defaults["context"].items():
            loaded["context"].setdefault(key, value)
        return loaded
    except Exception as e:
        raise RuntimeError(f"Failed to load session {session_id}: {e}")


def _save_session(session: dict) -> None:
    """Write session data to SQLite database."""
    try:
        conn = _get_db()
        session_id = session["session_id"]
        state_str = json.dumps(session, indent=2)
        now = _now()
        conn.execute(
            """INSERT OR REPLACE INTO assistant_sessions (session_id, state, created_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            (session_id, state_str, session.get("created_at", now), now)
        )
        conn.commit()

        # Clean up legacy JSON if it exists
        legacy_path = SESSION_DIR / f"{session_id}.json"
        if legacy_path.exists():
            try:
                legacy_path.unlink()
            except OSError:
                pass
    except Exception as e:
        raise RuntimeError(f"Failed to save session {session['session_id']}: {e}")


def _read_session_file() -> str | None:
    """Read the current session ID from Thursday's external state tree."""
    try:
        if SESSION_FILE.exists():
            return SESSION_FILE.read_text().strip()
    except OSError:
        pass
    return None


def _write_session_file(session_id: str) -> None:
    """Write the current session ID to Thursday's external state tree."""
    try:
        SESSION_FILE.write_text(session_id)
    except OSError:
        pass  # Non-fatal — session still works with explicit ID
