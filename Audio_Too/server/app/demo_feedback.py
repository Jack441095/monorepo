"""Feedback storage for external Audio Tips LLM demo testers."""

from __future__ import annotations

import json
from uuid import uuid4

from db import connect, now

CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS demo_feedback (
        id TEXT PRIMARY KEY,
        question TEXT,
        rating TEXT,
        comment TEXT,
        answer TEXT,
        sources_json TEXT,
        topics_json TEXT,
        confidence TEXT,
        source_quality TEXT,
        session_id TEXT,
        channel TEXT,
        issue_tags_json TEXT,
        repair_status TEXT,
        repair_note TEXT,
        repair_checked_at TEXT,
        repair_last_answer TEXT,
        repair_last_sources_json TEXT,
        created_at TEXT
    )
"""

ASK_SQL = """
    CREATE TABLE IF NOT EXISTS demo_questions (
        id TEXT PRIMARY KEY,
        session_id TEXT,
        question TEXT,
        confidence TEXT,
        source_quality TEXT,
        top_source TEXT,
        source_count INTEGER,
        answer_chars INTEGER,
        created_at TEXT
    )
"""


def _ensure_column(conn, table: str, column: str, typedef: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if column not in {row[1] for row in rows}:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")


def init_feedback_table() -> None:
    with connect() as conn:
        conn.execute(CREATE_SQL)
        conn.execute(ASK_SQL)
        _ensure_column(conn, "demo_feedback", "source_quality", "TEXT")
        _ensure_column(conn, "demo_feedback", "session_id", "TEXT")
        _ensure_column(conn, "demo_feedback", "answer", "TEXT")
        _ensure_column(conn, "demo_feedback", "sources_json", "TEXT")
        _ensure_column(conn, "demo_feedback", "topics_json", "TEXT")
        _ensure_column(conn, "demo_feedback", "channel", "TEXT")
        _ensure_column(conn, "demo_feedback", "issue_tags_json", "TEXT")
        _ensure_column(conn, "demo_feedback", "repair_status", "TEXT DEFAULT 'open'")
        _ensure_column(conn, "demo_feedback", "repair_note", "TEXT")
        _ensure_column(conn, "demo_feedback", "repair_checked_at", "TEXT")
        _ensure_column(conn, "demo_feedback", "repair_last_answer", "TEXT")
        _ensure_column(conn, "demo_feedback", "repair_last_sources_json", "TEXT")
        conn.commit()


def record_feedback(payload: dict) -> dict:
    init_feedback_table()
    row = {
        "id": str(uuid4())[:8],
        "question": str(payload.get("question", "")).strip()[:500],
        "rating": str(payload.get("rating", "")).strip()[:40],
        "comment": str(payload.get("comment", "")).strip()[:1200],
        "answer": str(payload.get("answer", "")).strip()[:8000],
        "sources_json": json_dumps(payload.get("sources") or []),
        "topics_json": json_dumps(payload.get("topics") or []),
        "confidence": str(payload.get("confidence", "")).strip()[:40],
        "source_quality": str(payload.get("source_quality", "")).strip()[:40],
        "session_id": str(payload.get("session_id", "")).strip()[:80],
        "channel": str(payload.get("channel", "demo")).strip()[:40] or "demo",
        "issue_tags_json": json_dumps(payload.get("issue_tags") or []),
        "repair_status": str(payload.get("repair_status", "open")).strip()[:40] or "open",
        "repair_note": str(payload.get("repair_note", "")).strip()[:240],
        "created_at": now(),
    }
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO demo_feedback (
                id, question, rating, comment, answer, sources_json, topics_json,
                confidence, source_quality, session_id, channel, issue_tags_json, repair_status, repair_note, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row["id"],
                row["question"],
                row["rating"],
                row["comment"],
                row["answer"],
                row["sources_json"],
                row["topics_json"],
                row["confidence"],
                row["source_quality"],
                row["session_id"],
                row["channel"],
                row["issue_tags_json"],
                row["repair_status"],
                row["repair_note"],
                row["created_at"],
            ],
        )
        conn.commit()
    return row


def json_dumps(value) -> str:
    try:
        return json.dumps(value, ensure_ascii=True)
    except (TypeError, ValueError):
        return "[]"


def json_loads_list(value) -> list:
    try:
        decoded = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return decoded if isinstance(decoded, list) else []


def hydrate_feedback(row: dict) -> dict:
    row["sources"] = json_loads_list(row.get("sources_json"))
    row["topics"] = json_loads_list(row.get("topics_json"))
    row["issue_tags"] = json_loads_list(row.get("issue_tags_json"))
    row["top_source"] = ""
    if row["sources"]:
        first = row["sources"][0]
        if isinstance(first, dict):
            row["top_source"] = str(first.get("label") or first.get("title") or first.get("source") or "")
    row["repair_last_sources"] = json_loads_list(row.get("repair_last_sources_json"))
    return row


def list_feedback(*, limit: int = 100) -> list[dict]:
    init_feedback_table()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM demo_feedback ORDER BY created_at DESC LIMIT ?",
            (max(1, min(500, limit)),),
        ).fetchall()
    return [hydrate_feedback(dict(row)) for row in rows]


def get_feedback(feedback_id: str) -> dict | None:
    init_feedback_table()
    with connect() as conn:
        row = conn.execute("SELECT * FROM demo_feedback WHERE id = ?", (feedback_id.strip(),)).fetchone()
    return hydrate_feedback(dict(row)) if row else None


def mark_repair_status(feedback_id: str, status: str, *, note_file: str = "") -> bool:
    init_feedback_table()
    clean_status = str(status or "").strip()[:40] or "open"
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE demo_feedback
            SET repair_status = ?, repair_note = COALESCE(NULLIF(?, ''), repair_note)
            WHERE id = ?
            """,
            (clean_status, str(note_file or "").strip()[:240], feedback_id.strip()),
        )
        conn.commit()
        return cur.rowcount > 0


def mark_repair_result(feedback_id: str, status: str, payload: dict, *, note_file: str = "") -> bool:
    init_feedback_table()
    sources = payload.get("sources") or []
    clean_status = str(status or "").strip()[:40] or "needs_review"
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE demo_feedback
            SET repair_status = ?,
                repair_note = COALESCE(NULLIF(?, ''), repair_note),
                repair_checked_at = ?,
                repair_last_answer = ?,
                repair_last_sources_json = ?
            WHERE id = ?
            """,
            (
                clean_status,
                str(note_file or "").strip()[:240],
                now(),
                str(payload.get("answer", "")).strip()[:8000],
                json_dumps(sources),
                feedback_id.strip(),
            ),
        )
        conn.commit()
        return cur.rowcount > 0


def record_question(session_id: str, question: str, payload: dict) -> dict:
    init_feedback_table()
    sources = payload.get("sources") or []
    top = sources[0].get("label", "") if sources else ""
    row = {
        "id": str(uuid4())[:8],
        "session_id": str(session_id or "").strip()[:80],
        "question": str(question).strip()[:500],
        "confidence": str(payload.get("confidence", "")).strip()[:40],
        "source_quality": str(payload.get("source_quality", "")).strip()[:40],
        "top_source": str(top)[:240],
        "source_count": len(sources),
        "answer_chars": len(str(payload.get("answer") or "")),
        "created_at": now(),
    }
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO demo_questions (id, session_id, question, confidence, source_quality, top_source, source_count, answer_chars, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row["id"],
                row["session_id"],
                row["question"],
                row["confidence"],
                row["source_quality"],
                row["top_source"],
                row["source_count"],
                row["answer_chars"],
                row["created_at"],
            ],
        )
        conn.commit()
    return row


def analytics(*, limit: int = 100) -> dict:
    init_feedback_table()
    with connect() as conn:
        questions = conn.execute(
            "SELECT * FROM demo_questions ORDER BY created_at DESC LIMIT ?",
            (max(1, min(500, limit)),),
        ).fetchall()
        feedback = conn.execute(
            "SELECT * FROM demo_feedback ORDER BY created_at DESC LIMIT ?",
            (max(1, min(500, limit)),),
        ).fetchall()
        sessions = conn.execute(
            """
            SELECT session_id, COUNT(*) AS question_count, MAX(created_at) AS last_seen
            FROM demo_questions
            WHERE COALESCE(session_id, '') != ''
            GROUP BY session_id
            ORDER BY last_seen DESC
            LIMIT 100
            """
        ).fetchall()
    qrows = [dict(row) for row in questions]
    frows = [hydrate_feedback(dict(row)) for row in feedback]
    total_questions = len(qrows)
    low_confidence = sum(1 for row in qrows if str(row.get("confidence", "")).lower() == "low")
    needs_work = sum(1 for row in frows if row.get("rating") == "not_useful")
    useful = sum(1 for row in frows if row.get("rating") == "useful")
    return {
        "total_recent_questions": total_questions,
        "low_confidence": low_confidence,
        "weak_rate": round(low_confidence / total_questions, 3) if total_questions else 0,
        "feedback_total": len(frows),
        "useful": useful,
        "needs_work": needs_work,
        "feedback_rate": round(len(frows) / total_questions, 3) if total_questions else 0,
        "sessions": [dict(row) for row in sessions],
        "questions": qrows,
        "feedback": frows,
    }
