"""Log and review weak Audio Tips LLM questions from the website."""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from db import connect, now

CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS tips_gaps (
        id TEXT PRIMARY KEY,
        question TEXT NOT NULL,
        confidence TEXT,
        topics TEXT,
        top_source TEXT,
        channel TEXT,
        status TEXT DEFAULT 'open',
        created_at TEXT,
        updated_at TEXT
    )
"""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, typedef: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if column not in {row[1] for row in rows}:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")


def init_gaps_table() -> None:
    with connect() as conn:
        conn.execute(CREATE_SQL)
        _ensure_column(conn, "tips_gaps", "note_file", "TEXT")
        conn.commit()


def should_record(payload: dict) -> bool:
    self_check = payload.get("answer_self_check") or {}
    warnings = self_check.get("warnings") if isinstance(self_check, dict) else []
    if warnings:
        return True
    confidence = str(payload.get("confidence", "")).lower()
    if confidence == "low":
        return True
    sources = payload.get("sources") or []
    has_note = any(str(item.get("kind", "")) == "note" for item in sources)
    if confidence == "medium" and not has_note:
        return True
    answer = str(payload.get("answer", "")).lower()
    if "do not have a strong local note" in answer:
        return True
    return False


def record_gap(question: str, payload: dict, *, channel: str = "unknown") -> dict | None:
    if not should_record(payload):
        return None
    init_gaps_table()
    sources = payload.get("sources") or []
    top = sources[0].get("label", "") if sources else ""
    row = {
        "id": str(uuid4())[:8],
        "question": question.strip()[:500],
        "confidence": str(payload.get("confidence", "")),
        "topics": json.dumps(payload.get("topics") or []),
        "top_source": str(top)[:240],
        "channel": channel[:40],
        "status": "open",
        "created_at": now(),
        "updated_at": now(),
    }
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tips_gaps (id, question, confidence, topics, top_source, channel, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row["id"],
                row["question"],
                row["confidence"],
                row["topics"],
                row["top_source"],
                row["channel"],
                row["status"],
                row["created_at"],
                row["updated_at"],
            ],
        )
        conn.commit()
    return row


def list_gaps(*, status: str = "open", limit: int = 50) -> list[dict]:
    init_gaps_table()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tips_gaps
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (status, max(1, min(200, limit))),
        ).fetchall()
    out: list[dict] = []
    for row in rows:
        item = dict(row)
        try:
            item["topics"] = json.loads(item.get("topics") or "[]")
        except json.JSONDecodeError:
            item["topics"] = []
        out.append(item)
    return out


def get_gap(gap_id: str) -> dict | None:
    init_gaps_table()
    with connect() as conn:
        row = conn.execute("SELECT * FROM tips_gaps WHERE id = ?", (gap_id.strip(),)).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item["topics"] = json.loads(item.get("topics") or "[]")
    except json.JSONDecodeError:
        item["topics"] = []
    return item


def link_gap_note(gap_id: str, note_file: str) -> bool:
    init_gaps_table()
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE tips_gaps
            SET status = 'drafted', note_file = ?, updated_at = ?
            WHERE id = ? AND status = 'open'
            """,
            (note_file, now(), gap_id.strip()),
        )
        conn.commit()
        return cur.rowcount > 0


def dismiss_gap(gap_id: str) -> bool:
    init_gaps_table()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE tips_gaps SET status = 'dismissed', updated_at = ? WHERE id = ? AND status = 'open'",
            (now(), gap_id.strip()),
        )
        conn.commit()
        return cur.rowcount > 0
