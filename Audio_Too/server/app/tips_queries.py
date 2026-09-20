"""Log Audio Tips LLM questions for content planning."""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from db import connect, now

CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS tips_queries (
        id TEXT PRIMARY KEY,
        question TEXT NOT NULL,
        confidence TEXT,
        topics TEXT,
        top_source TEXT,
        channel TEXT,
        created_at TEXT
    )
"""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, typedef: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if column not in {row[1] for row in rows}:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")


def init_queries_table() -> None:
    with connect() as conn:
        conn.execute(CREATE_SQL)
        _ensure_column(conn, "tips_queries", "route", "TEXT")
        _ensure_column(conn, "tips_queries", "intent", "TEXT")
        _ensure_column(conn, "tips_queries", "source_quality", "TEXT")
        _ensure_column(conn, "tips_queries", "answer_self_check", "TEXT")
        _ensure_column(conn, "tips_queries", "grounding_score", "INTEGER")
        _ensure_column(conn, "tips_queries", "grounding", "TEXT")
        _ensure_column(conn, "tips_queries", "grounding_mode", "TEXT")
        conn.commit()


def record_query(question: str, payload: dict, *, channel: str = "unknown") -> dict:
    init_queries_table()
    sources = payload.get("sources") or []
    top = sources[0].get("label", "") if sources else ""
    row = {
        "id": str(uuid4())[:8],
        "question": question.strip()[:500],
        "confidence": str(payload.get("confidence", "")),
        "topics": json.dumps(payload.get("topics") or []),
        "top_source": str(top)[:240],
        "channel": channel[:40],
        "route": str(payload.get("route", ""))[:60],
        "intent": str(payload.get("intent", ""))[:60],
        "source_quality": str(payload.get("source_quality", ""))[:60],
        "answer_self_check": json.dumps(payload.get("answer_self_check") or {}),
        "grounding_score": int((payload.get("grounding") or {}).get("score", 0) or 0),
        "grounding": json.dumps(payload.get("grounding") or {}),
        "grounding_mode": str(payload.get("grounding_mode", ""))[:40],
        "created_at": now(),
    }
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tips_queries
                (id, question, confidence, topics, top_source, channel, route, intent, source_quality,
                 answer_self_check, grounding_score, grounding, grounding_mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row["id"],
                row["question"],
                row["confidence"],
                row["topics"],
                row["top_source"],
                row["channel"],
                row["route"],
                row["intent"],
                row["source_quality"],
                row["answer_self_check"],
                row["grounding_score"],
                row["grounding"],
                row["grounding_mode"],
                row["created_at"],
            ],
        )
        conn.commit()
    return row


def list_queries(*, limit: int = 40) -> list[dict]:
    init_queries_table()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tips_queries ORDER BY created_at DESC LIMIT ?",
            (max(1, min(200, limit)),),
        ).fetchall()
    out: list[dict] = []
    for row in rows:
        item = dict(row)
        try:
            item["topics"] = json.loads(item.get("topics") or "[]")
        except json.JSONDecodeError:
            item["topics"] = []
        try:
            item["answer_self_check"] = json.loads(item.get("answer_self_check") or "{}")
        except json.JSONDecodeError:
            item["answer_self_check"] = {}
        try:
            item["grounding"] = json.loads(item.get("grounding") or "{}")
        except json.JSONDecodeError:
            item["grounding"] = {}
        out.append(item)
    return out


def self_check_warnings(item: dict) -> list[str]:
    check = item.get("answer_self_check") or {}
    warnings = check.get("warnings") if isinstance(check, dict) else []
    if isinstance(warnings, list):
        return [str(warning) for warning in warnings if str(warning).strip()]
    return []


def list_quality_issues(*, limit: int = 40) -> list[dict]:
    rows = list_queries(limit=max(limit * 3, limit))
    issues: list[dict] = []
    for item in rows:
        warnings = self_check_warnings(item)
        has_grounding = item.get("grounding_score") is not None or bool(item.get("grounding"))
        weak_grounding = has_grounding and int(item.get("grounding_score") or 0) < 65
        weak = (
            warnings
            or weak_grounding
            or str(item.get("confidence", "")).lower() == "low"
            or str(item.get("source_quality", "")).lower() in {"low", "weak"}
            or str(item.get("route", "")).lower() in {"unknown", "clarify"}
        )
        if not weak:
            continue
        item["self_check_warnings"] = warnings
        issues.append(item)
        if len(issues) >= max(1, min(200, limit)):
            break
    return issues
