"""KENN Adaptive Trust Scores module.

Manages dynamic trust ratings for knowledge sources based on historical usage
and user correction signals.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from kenn.knowledge.reasoning import _get_conn, init_db

logger = logging.getLogger("kenn.knowledge.trust_scores")


def get_source_default_trust(source_name: str) -> float:
    """Determine the default trust score based on source naming/type conventions."""
    lower_name = source_name.lower()
    if "manual" in lower_name or lower_name.endswith(".pdf"):
        return 1.0
    if lower_name.endswith(".md") or "note" in lower_name:
        return 0.9
    if "transcript" in lower_name or lower_name.endswith(".txt") or "youtube" in lower_name or "podcast" in lower_name:
        return 0.7
    return 0.5


def get_source_trust(source_name: str) -> float:
    """Retrieve the trust score for a source, creating it with default if not present."""
    init_db()
    name = source_name.strip()
    if not name:
        return 0.5
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT trust_score FROM source_trust WHERE source_name = ?",
                (name,)
            ).fetchone()
            if row:
                return float(row["trust_score"])
            
            # Create default entry
            default_score = get_source_default_trust(name)
            conn.execute(
                """
                INSERT OR IGNORE INTO source_trust (source_name, trust_score, corrections_count, citations_count)
                VALUES (?, ?, 0, 0)
                """,
                (name, default_score)
            )
            return default_score
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to get source trust for {name}: {e}")
        return get_source_default_trust(name)


def record_citation(source_name: str) -> None:
    """Increment citation count and slightly boost trust (capped at 1.0)."""
    name = source_name.strip()
    if not name:
        return
    try:
        init_db()
        current_score = get_source_trust(name)
        new_score = min(1.0, current_score + 0.01)
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO source_trust (source_name, trust_score, corrections_count, citations_count)
                VALUES (?, ?, 0, 1)
                ON CONFLICT(source_name) DO UPDATE SET
                    citations_count = citations_count + 1,
                    trust_score = MIN(1.0, trust_score + 0.01)
                """,
                (name, new_score)
            )
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to record citation for {name}: {e}")


def record_correction(source_name: str) -> None:
    """Increment correction count and decrement trust (bounded at 0.1)."""
    name = source_name.strip()
    if not name:
        return
    try:
        init_db()
        current_score = get_source_trust(name)
        new_score = max(0.1, current_score - 0.1)
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO source_trust (source_name, trust_score, corrections_count, citations_count)
                VALUES (?, ?, 1, 0)
                ON CONFLICT(source_name) DO UPDATE SET
                    corrections_count = corrections_count + 1,
                    trust_score = MAX(0.1, trust_score - 0.1)
                """,
                (name, new_score)
            )
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to record correction for {name}: {e}")


def set_source_trust(source_name: str, score: float) -> None:
    """Manually set trust score override for a source."""
    name = source_name.strip()
    if not name:
        return
    try:
        init_db()
        bounded_score = max(0.0, min(1.0, score))
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO source_trust (source_name, trust_score, corrections_count, citations_count)
                VALUES (?, ?, 0, 0)
                ON CONFLICT(source_name) DO UPDATE SET
                    trust_score = ?
                """,
                (name, bounded_score, bounded_score)
            )
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to override trust score for {name}: {e}")


def list_source_trust() -> list[dict[str, Any]]:
    """List all tracked sources and their trust ratings."""
    try:
        init_db()
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM source_trust ORDER BY trust_score DESC, citations_count DESC"
            ).fetchall()
            return [dict(row) for row in rows]
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to list trust scores: {e}")
        return []
