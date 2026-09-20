"""KENN Reasoning Memory module.

Manages SQLite persistence for KENN's reasoning traces, allowing her to store
what she concluded, retrieve past conclusions, and query them with FTS5 search.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import uuid
import hashlib
from pathlib import Path
from typing import Any

logger = logging.getLogger("kenn.knowledge.reasoning")

ROOT = Path(__file__).resolve().parent.parent

# Found 2026-07-27 while testing Thursday's chat quality: query_reasoning_traces
# built its FTS query by OR-ing every word in the current message, then sorted
# the SQL-level matches by created_at DESC instead of relevance -- so any two
# messages sharing even one common word (nearly guaranteed given how many
# short function/stop words a real sentence has) surfaced the single MOST
# RECENT trace regardless of topic, not the most similar one. In production
# this meant e.g. "whats 17 times 24" pulled in the immediately-preceding
# unrelated exchange as "Past reasoning on this topic" and the answer quoted
# it verbatim. Filtering stop words out of the query terms, matching the same
# list already applied to short chit-chat elsewhere in this codebase's intent
# handling, removes the "matches on 'the'/'how'/'you'" false positives; see
# the ORDER BY rank fix in query_reasoning_traces below for the other half.
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did", "doing",
    "how", "what", "whats", "who", "whom", "which", "this", "that", "these",
    "those", "i", "you", "he", "she", "it", "we", "they", "me", "him", "her",
    "us", "them", "my", "your", "his", "its", "our", "their", "to", "of", "in",
    "on", "at", "by", "for", "with", "about", "as", "into", "like", "through",
    "after", "before", "between", "out", "against", "during", "without",
    "under", "around", "among", "and", "or", "but", "if", "then", "so",
    "because", "can", "could", "should", "would", "will", "shall", "may",
    "might", "must", "please", "thanks", "thank", "hey", "hi", "hello",
})


def _significant_words(text: str) -> list[str]:
    """Content words only -- stop words removed so a match requires actual
    topical overlap, not just sharing common function words."""
    return [w for w in re.findall(r"\w+", text.lower()) if w not in _STOPWORDS]

def _get_db_path() -> Path:
    """Dynamically resolve the DB path to support testing/isolation."""
    chats_dir = Path(os.environ.get("KENN_CHATS_DIR", str(ROOT / "chats"))).expanduser()
    return Path(os.environ.get("KENN_DB_PATH", str(chats_dir / "kenn.db"))).expanduser()


def _get_conn() -> sqlite3.Connection:
    """Get a connection to the SQLite database with WAL and timeout configuration."""
    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn



def init_db() -> None:
    """Initialize the knowledge reasoning tables and FTS5 search indexes."""
    try:
        with _get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_reasoning (
                    trace_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    query TEXT NOT NULL,
                    route TEXT NOT NULL,
                    evidence_ids TEXT NOT NULL,
                    conclusion TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    outcome TEXT,
                    correction TEXT,
                    lessons TEXT,
                    tags TEXT NOT NULL
                )
                """
            )
            # Create FTS5 virtual table
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_reasoning_fts USING fts5(
                        trace_id UNINDEXED,
                        query,
                        conclusion,
                        lessons,
                        tags
                    )
                    """
                )
            except sqlite3.OperationalError as e:
                logger.warning(f"FTS5 virtual table creation failed or not supported: {e}")

            # Create knowledge_lessons table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_lessons (
                    lesson_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    source_trace_id TEXT
                )
                """
            )

            # Create source_trust table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS source_trust (
                    source_name TEXT PRIMARY KEY,
                    trust_score REAL NOT NULL DEFAULT 1.0,
                    corrections_count INTEGER NOT NULL DEFAULT 0,
                    citations_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )

            # Create knowledge_contradictions table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_contradictions (
                    contradiction_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    resolution TEXT,
                    source_a TEXT NOT NULL,
                    source_b TEXT NOT NULL,
                    description TEXT NOT NULL,
                    conflicting_data TEXT NOT NULL
                )
                """
            )
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to initialize reasoning tables: {e}")


def get_chunk_id(chunk: dict) -> str:
    """Generate a deterministic, unique, and compact chunk identifier."""
    h = hashlib.md5()
    h.update(chunk.get("source", "").encode("utf-8", "ignore"))
    h.update(str(chunk.get("page", 0)).encode("utf-8", "ignore"))
    h.update(chunk.get("kind", "").encode("utf-8", "ignore"))
    h.update(chunk.get("text", "").encode("utf-8", "ignore"))
    return h.hexdigest()[:12]


def save_reasoning_trace(
    query: str,
    route: str,
    evidence_ids: list[str],
    conclusion: str,
    confidence: str,
    outcome: str | None = None,
    correction: str | None = None,
    lessons: list[str] | None = None,
    tags: list[str] | None = None,
    trace_id: str | None = None,
) -> str | None:
    """Save a reasoning trace to SQLite. Falls back gracefully on lock or failure."""
    try:
        import datetime
        init_db()
        tid = trace_id or str(uuid.uuid4())
        created = datetime.datetime.now(datetime.timezone.utc).isoformat()
        evidence_str = json.dumps(evidence_ids)
        lessons_str = json.dumps(lessons or [])
        tags_str = " ".join(tags or [])

        with _get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO knowledge_reasoning (
                    trace_id, created_at, query, route, evidence_ids,
                    conclusion, confidence, outcome, correction, lessons, tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (tid, created, query, route, evidence_str, conclusion,
                 confidence, outcome, correction, lessons_str, tags_str)
            )

            # Insert into FTS virtual table
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO knowledge_reasoning_fts (trace_id, query, conclusion, lessons, tags)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (tid, query, conclusion, lessons_str, tags_str)
                )
            except sqlite3.OperationalError:
                # FTS table may be missing or not compiled
                pass

            # Apply rolling retention limit
            _apply_retention(conn)

            return tid
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Fallback triggered: Failed to save reasoning trace: {e}")
        return None


def _apply_retention(conn: sqlite3.Connection, limit: int = 1000) -> None:
    """Delete oldest records keeping only the limit most recent traces."""
    try:
        row = conn.execute("SELECT COUNT(*) as count FROM knowledge_reasoning").fetchone()
        if row and row["count"] > limit:
            # Fetch the trace_ids that we want to keep
            rows = conn.execute(
                "SELECT trace_id FROM knowledge_reasoning ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,)
            ).fetchall()
            keep_ids = [r["trace_id"] for r in rows]
            if len(keep_ids) >= limit:
                placeholders = ",".join("?" for _ in keep_ids)
                try:
                    conn.execute(
                        f"DELETE FROM knowledge_reasoning_fts WHERE trace_id NOT IN ({placeholders})",
                        keep_ids
                    )
                except sqlite3.OperationalError:
                    pass
                conn.execute(
                    f"DELETE FROM knowledge_reasoning WHERE trace_id NOT IN ({placeholders})",
                    keep_ids
                )
    except sqlite3.Error as e:
        logger.warning(f"Failed to apply retention: {e}")



def get_reasoning_trace(trace_id: str) -> dict[str, Any] | None:
    """Load a reasoning trace by trace_id."""
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_reasoning WHERE trace_id = ?",
                (trace_id,)
            ).fetchone()
            if row:
                res = dict(row)
                try:
                    res["evidence_ids"] = json.loads(res["evidence_ids"])
                except Exception:
                    res["evidence_ids"] = []
                try:
                    res["lessons"] = json.loads(res["lessons"])
                except Exception:
                    res["lessons"] = []
                res["tags"] = res["tags"].split()
                return res
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to retrieve reasoning trace {trace_id}: {e}")
    return None


def query_reasoning_traces(query_text: str, limit: int = 3) -> list[dict[str, Any]]:
    """Query reasoning traces using FTS5 MATCH, falling back to LIKE if FTS fails.

    Ranked by FTS5 relevance (`ORDER BY rank`), not recency -- see the module
    docstring note above `_STOPWORDS` for why recency-ordering was a real
    contamination bug, not just a quality nicety. Only content words (stop
    words stripped) build the query, so "whats 17 times 24" or "how do I
    sidechain a kick" can no longer match an unrelated trace purely on
    sharing "whats"/"how"/"do" -- if nothing but stop words remain, there is
    no meaningful topic to match against, so this returns no hits rather
    than falling back to "whatever was said most recently".
    """
    try:
        init_db()
        words = re.findall(r'\w+', query_text)
        if not words:
            return list_reasoning_history(limit=limit)
        significant = _significant_words(query_text)
        if not significant:
            return []

        fts_query = " OR ".join(f'"{w}"*' for w in significant)
        results = []

        with _get_conn() as conn:
            try:
                match_rows = conn.execute(
                    """
                    SELECT trace_id FROM knowledge_reasoning_fts
                    WHERE knowledge_reasoning_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_query, limit)
                ).fetchall()
                ordered_ids = [r["trace_id"] for r in match_rows]
                if not ordered_ids:
                    return []
                placeholders = ",".join("?" for _ in ordered_ids)
                rows_by_id = {
                    r["trace_id"]: r
                    for r in conn.execute(
                        f"SELECT * FROM knowledge_reasoning WHERE trace_id IN ({placeholders})",
                        ordered_ids,
                    ).fetchall()
                }
                rows = [rows_by_id[tid] for tid in ordered_ids if tid in rows_by_id]
            except sqlite3.OperationalError:
                # FTS MATCH syntax error or missing table fallback
                like_pattern = f"%{query_text}%"
                rows = conn.execute(
                    """
                    SELECT * FROM knowledge_reasoning
                    WHERE query LIKE ? OR conclusion LIKE ? OR tags LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (like_pattern, like_pattern, like_pattern, limit)
                ).fetchall()

            for row in rows:
                res = dict(row)
                try:
                    res["evidence_ids"] = json.loads(res["evidence_ids"])
                except Exception:
                    res["evidence_ids"] = []
                try:
                    res["lessons"] = json.loads(res["lessons"])
                except Exception:
                    res["lessons"] = []
                res["tags"] = res["tags"].split()
                results.append(res)

            return results
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to query reasoning traces: {e}")
        return []


def list_reasoning_history(query_text: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """List reasoning history traces, optionally filtered."""
    try:
        init_db()
        results = []
        with _get_conn() as conn:
            if query_text:
                like_pattern = f"%{query_text}%"
                rows = conn.execute(
                    """
                    SELECT * FROM knowledge_reasoning
                    WHERE query LIKE ? OR conclusion LIKE ? OR tags LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (like_pattern, like_pattern, like_pattern, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM knowledge_reasoning ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()

            for row in rows:
                res = dict(row)
                try:
                    res["evidence_ids"] = json.loads(res["evidence_ids"])
                except Exception:
                    res["evidence_ids"] = []
                try:
                    res["lessons"] = json.loads(res["lessons"])
                except Exception:
                    res["lessons"] = []
                res["tags"] = res["tags"].split()
                results.append(res)

            return results
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to list reasoning history: {e}")
        return []
