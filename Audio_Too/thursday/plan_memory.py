"""Thursday Planning Memory.

Mirrors the crash-safety and retrieval architecture of KENN's reasoning
memory (studio/kenn/kenn/knowledge/reasoning.py): a SQLite table + FTS5
index that lets Thursday remember what she planned, what she executed, and
whether it succeeded — then retrieve the most similar past plans before
planning the current request (see thursday/brain.py's build_brain_prompt).

Unlike KENN's reasoning memory (which prunes old rows outright), plan
memory is capped at 500 *active* rows but never silently loses history:
rows evicted by the retention cap are archived to an append-only JSONL log
(thursday/user_data/plan_memory_archive.jsonl) before being removed from
the active table, using the same atomic-write pattern as feedback.py.

Every write here is best-effort and fails soft: a locked or corrupt DB
never blocks a Thursday request. This module is a read/retrieval and
after-the-fact logging feature only — it does not gate or skip any
confirmation/receipt safety check.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("thursday.plan_memory")

ACTIVE_LIMIT = 500

from thursday.redaction import redact
from thursday.runtime_paths import DATA_DIR

# Same bug, same fix as studio/kenn/kenn/knowledge/reasoning.py's identical
# query_reasoning_traces (this module mirrors that one, per the docstring
# above): recency-ordering + no stop-word filtering meant any two messages
# sharing one common word surfaced the most recent plan regardless of topic,
# not the most similar one. See that module for the full incident writeup.
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
    configured = os.environ.get("THURSDAY_PLAN_MEMORY_DB", "").strip()
    if configured:
        return Path(configured).expanduser()
    return DATA_DIR / "plan_memory.sqlite3"


def _get_archive_path() -> Path:
    configured = os.environ.get("THURSDAY_PLAN_MEMORY_ARCHIVE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return DATA_DIR / "plan_memory_archive.jsonl"


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
    """Initialize the plan_memory table and FTS5 search index."""
    try:
        with _get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS plan_memory (
                    plan_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    query TEXT NOT NULL,
                    abstract TEXT NOT NULL,
                    steps TEXT NOT NULL,
                    executed_steps TEXT NOT NULL,
                    status TEXT NOT NULL,
                    service_id TEXT,
                    result_summary TEXT,
                    lesson TEXT,
                    tags TEXT NOT NULL
                )
                """
            )
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS plan_memory_fts USING fts5(
                        plan_id UNINDEXED,
                        query,
                        abstract,
                        lesson,
                        tags
                    )
                    """
                )
            except sqlite3.OperationalError as e:
                logger.warning(f"FTS5 virtual table creation failed or not supported: {redact(str(e))}")
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to initialize plan_memory tables: {redact(str(e))}")


def _atomic_append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Append records to a JSONL archive, best-effort, with a file lock.

    Not a full atomic-replace (that isn't compatible with append-only logs),
    but uses an exclusive advisory lock — same pattern as
    thursday/feedback.py's record_feedback — so concurrent writers don't
    interleave partial lines.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                for record in records:
                    f.write(json.dumps(record) + "\n")
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError as e:
        logger.warning(f"Failed to archive plan_memory rows: {redact(str(e))}")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    res = dict(row)
    for field in ("steps", "executed_steps"):
        try:
            res[field] = json.loads(res[field])
        except Exception:
            res[field] = []
    res["tags"] = (res.get("tags") or "").split()
    return res


def _apply_retention(conn: sqlite3.Connection, limit: int | None = None) -> None:
    """Archive-then-delete the oldest rows beyond the active cap.

    Unlike KENN's reasoning retention (which deletes outright), evicted
    rows are appended to an append-only JSONL archive first so history is
    never silently lost — only demoted out of the fast/active FTS index.

    ``limit`` defaults to the module-level ACTIVE_LIMIT, read at call time
    (not bound as a function default) so tests can lower it via
    monkeypatching ``thursday.plan_memory.ACTIVE_LIMIT``.
    """
    if limit is None:
        limit = ACTIVE_LIMIT
    try:
        row = conn.execute("SELECT COUNT(*) as count FROM plan_memory").fetchone()
        if not row or row["count"] <= limit:
            return

        keep_rows = conn.execute(
            "SELECT plan_id FROM plan_memory ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
        keep_ids = {r["plan_id"] for r in keep_rows}

        evict_rows = conn.execute("SELECT * FROM plan_memory").fetchall()
        to_evict = [r for r in evict_rows if r["plan_id"] not in keep_ids]
        if not to_evict:
            return

        archive_records = [_row_to_dict(r) for r in to_evict]
        _atomic_append_jsonl(_get_archive_path(), archive_records)

        evict_ids = [r["plan_id"] for r in to_evict]
        placeholders = ",".join("?" for _ in evict_ids)
        try:
            conn.execute(
                f"DELETE FROM plan_memory_fts WHERE plan_id IN ({placeholders})",
                evict_ids,
            )
        except sqlite3.OperationalError:
            pass
        conn.execute(f"DELETE FROM plan_memory WHERE plan_id IN ({placeholders})", evict_ids)
    except sqlite3.Error as e:
        logger.warning(f"Failed to apply plan_memory retention: {redact(str(e))}")


def save_plan_trace(
    query: str,
    abstract: str,
    steps: list[dict[str, Any]],
    status: str,
    *,
    service_id: str | None = None,
    executed_steps: list[dict[str, Any]] | None = None,
    result_summary: str | None = None,
    lesson: str | None = None,
    tags: list[str] | None = None,
    plan_id: str | None = None,
) -> str | None:
    """Save a plan trace (what was asked/planned/executed/outcome). Fails soft."""
    try:
        import datetime

        init_db()
        pid = plan_id or str(uuid.uuid4())
        created = datetime.datetime.now(datetime.timezone.utc).isoformat()
        steps_str = json.dumps(steps or [])
        executed_str = json.dumps(executed_steps if executed_steps is not None else (steps or []))
        tags_str = " ".join(tags or [])

        with _get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO plan_memory (
                    plan_id, created_at, query, abstract, steps, executed_steps,
                    status, service_id, result_summary, lesson, tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid, created, query, abstract, steps_str, executed_str,
                    status, service_id, result_summary, lesson, tags_str,
                ),
            )
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO plan_memory_fts (plan_id, query, abstract, lesson, tags)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (pid, query, abstract, lesson or "", tags_str),
                )
            except sqlite3.OperationalError:
                pass

            _apply_retention(conn)

            return pid
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Fallback triggered: failed to save plan trace: {redact(str(e))}")
        return None


def get_plan_trace(plan_id: str) -> dict[str, Any] | None:
    """Load a plan trace by plan_id."""
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM plan_memory WHERE plan_id = ?", (plan_id,)
            ).fetchone()
            if row:
                return _row_to_dict(row)
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to retrieve plan trace {plan_id}: {redact(str(e))}")
    return None


def query_similar_plans(query_text: str, limit: int = 3) -> list[dict[str, Any]]:
    """Query past plans using FTS5 MATCH, falling back to LIKE if FTS fails.

    Ranked by FTS5 relevance (`ORDER BY rank`), not recency, and matched only
    on content words (stop words stripped) -- see _STOPWORDS above and
    reasoning.py's query_reasoning_traces for the full incident writeup: the
    old recency-ordered, unfiltered query surfaced the most recent plan for
    almost any message, regardless of topic. If nothing but stop words
    remain, there is no real topic to match against, so this returns no
    hits rather than an arbitrary recent plan.
    """
    try:
        init_db()
        words = re.findall(r"\w+", query_text)
        if not words:
            return list_plan_history(limit=limit)
        significant = _significant_words(query_text)
        if not significant:
            return []

        fts_query = " OR ".join(f'"{w}"*' for w in significant)
        results = []

        with _get_conn() as conn:
            try:
                match_rows = conn.execute(
                    """
                    SELECT plan_id FROM plan_memory_fts
                    WHERE plan_memory_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
                ordered_ids = [r["plan_id"] for r in match_rows]
                if not ordered_ids:
                    return []
                placeholders = ",".join("?" for _ in ordered_ids)
                rows_by_id = {
                    r["plan_id"]: r
                    for r in conn.execute(
                        f"SELECT * FROM plan_memory WHERE plan_id IN ({placeholders})",
                        ordered_ids,
                    ).fetchall()
                }
                rows = [rows_by_id[pid] for pid in ordered_ids if pid in rows_by_id]
            except sqlite3.OperationalError:
                like_pattern = f"%{query_text}%"
                rows = conn.execute(
                    """
                    SELECT * FROM plan_memory
                    WHERE query LIKE ? OR abstract LIKE ? OR tags LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (like_pattern, like_pattern, like_pattern, limit),
                ).fetchall()

            for row in rows:
                results.append(_row_to_dict(row))
            return results
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to query plan_memory: {redact(str(e))}")
        return []


def list_plan_history(query_text: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """List plan history traces, optionally filtered."""
    try:
        init_db()
        results = []
        with _get_conn() as conn:
            if query_text:
                like_pattern = f"%{query_text}%"
                rows = conn.execute(
                    """
                    SELECT * FROM plan_memory
                    WHERE query LIKE ? OR abstract LIKE ? OR tags LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (like_pattern, like_pattern, like_pattern, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM plan_memory ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()

            for row in rows:
                results.append(_row_to_dict(row))
            return results
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to list plan history: {redact(str(e))}")
        return []
