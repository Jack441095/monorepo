"""Explicit producer preferences and evidence-linked production episodes."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from uuid import uuid4

from kenn.core.assistant_task_memory import AssistantTaskStore
from kenn.core.session_memory import DB_PATH


PREFERENCE_SCHEMA = "kenn.producer_preference.v1"
EPISODE_SCHEMA = "kenn.production_episode.v1"
MAX_PREFERENCES = 32
MAX_EPISODES = 64
PREFERENCE_KEYS = frozenset({
    "arrangement_preference",
    "communication_style",
    "creative_direction",
    "genre",
    "mix_priority",
    "monitoring",
    "preferred_device",
    "reference_track",
    "skill_level",
    "sound_palette",
    "workflow",
})
VERDICTS = frozenset({"keep", "revise", "reject"})
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS producer_preferences (
            preference_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            preference_key TEXT NOT NULL,
            value TEXT NOT NULL,
            source_turn_id TEXT NOT NULL,
            statement_sha256 TEXT NOT NULL,
            active INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS producer_preferences_current "
        "ON producer_preferences(session_id, preference_key, active, created_at DESC)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS production_episodes (
            episode_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            task_id TEXT NOT NULL UNIQUE,
            verdict TEXT NOT NULL,
            state_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS production_episodes_session_created "
        "ON production_episodes(session_id, created_at DESC)"
    )
    return conn


def _preference_projection(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": PREFERENCE_SCHEMA,
        "preference_id": row["preference_id"],
        "session_id": row["session_id"],
        "key": row["preference_key"],
        "value": row["value"],
        "source": "explicit_user_statement",
        "source_turn_id": row["source_turn_id"],
        "statement_sha256": row["statement_sha256"],
        "confidence": "explicit",
        "advisory_only": True,
        "created_at": row["created_at"],
    }


class AssistantProfileStore:
    """Store only explicit preferences and evidence-backed task outcomes."""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)

    def record_preference(
        self,
        *,
        session_id: str,
        key: str,
        value: str,
        source_turn_id: str,
        user_statement: str,
    ) -> dict[str, Any]:
        clean_session = _text(session_id, 128)
        clean_key = _text(key, 64).lower()
        clean_value = _text(value, 256)
        clean_turn = _text(source_turn_id, 128)
        statement = _text(user_statement, 2_048)
        errors: list[str] = []
        if not clean_session:
            errors.append("session_id is required")
        if not _KEY.fullmatch(clean_key) or clean_key not in PREFERENCE_KEYS:
            errors.append("preference key is outside KENN's production-profile allowlist")
        if not clean_value:
            errors.append("preference value is required")
        if not clean_turn:
            errors.append("source_turn_id is required")
        if not statement:
            errors.append("an explicit user statement is required")
        if clean_value and statement and clean_value.casefold() not in statement.casefold():
            errors.append("the preference value must appear in the explicit user statement")
        if errors:
            return {"ok": False, "errors": errors}

        created_at = _now()
        row = {
            "preference_id": f"preference-{uuid4().hex}",
            "session_id": clean_session,
            "preference_key": clean_key,
            "value": clean_value,
            "source_turn_id": clean_turn,
            "statement_sha256": "sha256:" + hashlib.sha256(statement.encode("utf-8")).hexdigest(),
            "created_at": created_at,
        }
        conn = _connect(self.db_path)
        try:
            conn.execute(
                "UPDATE producer_preferences SET active = 0 WHERE session_id = ? AND preference_key = ? AND active = 1",
                (clean_session, clean_key),
            )
            conn.execute(
                "INSERT INTO producer_preferences(preference_id, session_id, preference_key, value, "
                "source_turn_id, statement_sha256, active, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
                tuple(row[key] for key in (
                    "preference_id", "session_id", "preference_key", "value",
                    "source_turn_id", "statement_sha256", "created_at",
                )),
            )
            conn.execute(
                """
                DELETE FROM producer_preferences WHERE preference_id IN (
                    SELECT preference_id FROM producer_preferences WHERE session_id = ? AND active = 0
                    ORDER BY created_at DESC LIMIT -1 OFFSET ?
                )
                """,
                (clean_session, MAX_PREFERENCES),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "preference": _preference_projection(row)}

    def current_preferences(self, session_id: str) -> list[dict[str, Any]]:
        conn = _connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM producer_preferences WHERE session_id = ? AND active = 1 "
                "ORDER BY preference_key LIMIT ?",
                (_text(session_id, 128), MAX_PREFERENCES),
            ).fetchall()
        finally:
            conn.close()
        return [_preference_projection(row) for row in rows]

    def forget_preference(self, *, session_id: str, key: str) -> bool:
        conn = _connect(self.db_path)
        try:
            cursor = conn.execute(
                "UPDATE producer_preferences SET active = 0 WHERE session_id = ? AND preference_key = ? AND active = 1",
                (_text(session_id, 128), _text(key, 64).lower()),
            )
            conn.commit()
        finally:
            conn.close()
        return cursor.rowcount > 0

    def record_task_outcome(
        self,
        *,
        task_id: str,
        verdict: str,
        source_turn_id: str,
        user_statement: str,
        comment: str = "",
        requested_changes: list[str] | None = None,
    ) -> dict[str, Any]:
        task = AssistantTaskStore(self.db_path).load(_text(task_id, 128))
        if task is None:
            return {"ok": False, "errors": ["assistant task was not found"]}
        errors: list[str] = []
        clean_verdict = _text(verdict, 32).lower()
        clean_turn = _text(source_turn_id, 128)
        statement = _text(user_statement, 2_048)
        if task.get("status") != "completed":
            errors.append("only a completed assistant task can become a production episode")
        if clean_verdict not in VERDICTS:
            errors.append("verdict must be keep, revise, or reject")
        if not clean_turn or not statement:
            errors.append("an explicit user turn is required for an outcome")
        changes = requested_changes or []
        if not isinstance(changes, list) or len(changes) > 5 or any(not isinstance(item, str) or not item.strip() for item in changes):
            errors.append("requested_changes must contain at most five non-empty strings")
            changes = []
        completed_evidence = [
            item for item in (task.get("evidence") or [])
            if isinstance(item, dict)
            and item.get("progress_only") is not True
            and (item.get("receipt_id") or item.get("job_id") or item.get("project_id"))
        ]
        if not completed_evidence:
            errors.append("task has no persisted receipt or completed-job evidence")
        if errors:
            return {"ok": False, "errors": errors}

        episode = {
            "schema": EPISODE_SCHEMA,
            "episode_id": f"episode-{uuid4().hex}",
            "session_id": task["session_id"],
            "task_id": task["task_id"],
            "goal": _text(task.get("goal"), 1_024),
            "verdict": clean_verdict,
            "comment": _text(comment, 1_000),
            "requested_changes": [_text(item, 256) for item in changes],
            "source_turn_id": clean_turn,
            "statement_sha256": "sha256:" + hashlib.sha256(statement.encode("utf-8")).hexdigest(),
            "evidence_refs": completed_evidence[-8:],
            "advisory_only": True,
            "created_at": _now(),
        }
        conn = _connect(self.db_path)
        try:
            try:
                conn.execute(
                    "INSERT INTO production_episodes(episode_id, session_id, task_id, verdict, state_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        episode["episode_id"], episode["session_id"], episode["task_id"],
                        episode["verdict"], json.dumps(episode, sort_keys=True), episode["created_at"],
                    ),
                )
            except sqlite3.IntegrityError:
                return {"ok": False, "errors": ["task already has a recorded production episode"]}
            conn.execute(
                """
                DELETE FROM production_episodes WHERE episode_id IN (
                    SELECT episode_id FROM production_episodes WHERE session_id = ?
                    ORDER BY created_at DESC LIMIT -1 OFFSET ?
                )
                """,
                (episode["session_id"], MAX_EPISODES),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "episode": episode}

    def recent_episodes(self, session_id: str, *, limit: int = 8) -> list[dict[str, Any]]:
        bounded = max(1, min(MAX_EPISODES, int(limit)))
        conn = _connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT state_json FROM production_episodes WHERE session_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (_text(session_id, 128), bounded),
            ).fetchall()
        finally:
            conn.close()
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                item = json.loads(row["state_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(item, dict) and item.get("schema") == EPISODE_SCHEMA:
                result.append(item)
        return result

    def forget_episode(self, *, session_id: str, episode_id: str) -> bool:
        conn = _connect(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM production_episodes WHERE session_id = ? AND episode_id = ?",
                (_text(session_id, 128), _text(episode_id, 128)),
            )
            conn.commit()
        finally:
            conn.close()
        return cursor.rowcount > 0

    def clear_profile(self, session_id: str) -> dict[str, int]:
        """Forget all profile and outcome memory without deleting task receipts."""
        clean_session = _text(session_id, 128)
        conn = _connect(self.db_path)
        try:
            preferences = conn.execute(
                "DELETE FROM producer_preferences WHERE session_id = ?", (clean_session,),
            ).rowcount
            episodes = conn.execute(
                "DELETE FROM production_episodes WHERE session_id = ?", (clean_session,),
            ).rowcount
            conn.commit()
        finally:
            conn.close()
        return {"preferences": preferences, "episodes": episodes}

    def context_memory(self, session_id: str) -> dict[str, Any]:
        return {
            "producer_preferences": self.current_preferences(session_id),
            "episodic_outcomes": self.recent_episodes(session_id),
        }


__all__ = [
    "AssistantProfileStore", "EPISODE_SCHEMA", "MAX_EPISODES", "MAX_PREFERENCES",
    "PREFERENCE_KEYS", "PREFERENCE_SCHEMA", "VERDICTS",
]
