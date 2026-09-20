"""Feedback-driven retrieval signals for KENN.

Reads aggregated user feedback (thumbs-up/down) from the session_feedback table
and computes per-source boosting multipliers.  Sources with consistently positive
feedback get a modest score boost; sources with negative feedback get a penalty.

The multipliers are cached in memory and refreshed lazily (at most once per
REFRESH_INTERVAL_SECONDS).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "session_memory.db"
REFRESH_INTERVAL_SECONDS = 300  # 5 minutes

_lock = threading.Lock()
_cache: dict[str, float] = {}
_cache_time: float = 0.0


def _load_source_feedback() -> dict[str, float]:
    """Query session_feedback + session turns to build per-source multipliers.

    For each source note that has received explicit ratings:
    - Count thumbs-up (rating >= 4) and thumbs-down (rating <= 2).
    - Compute a multiplier: 1.0 + 0.05 * (up - down), clamped to [0.85, 1.15].

    This keeps adjustments subtle enough to avoid runaway feedback loops while
    still rewarding consistently-helpful notes.
    """
    if not DB_PATH.exists():
        return {}

    multipliers: dict[str, float] = {}
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        conn.row_factory = sqlite3.Row

        # Join feedback with session turns to get the sources that were shown
        rows = conn.execute("""
            SELECT st.sources_json, sf.explicit_rating
            FROM session_feedback sf
            JOIN session_turns st ON sf.turn_id = st.turn_id
            WHERE sf.explicit_rating IS NOT NULL
              AND st.sources_json IS NOT NULL
        """).fetchall()
        conn.close()

        source_votes: dict[str, dict[str, int]] = {}
        for row in rows:
            rating = row["explicit_rating"]
            try:
                sources = json.loads(row["sources_json"])
            except (json.JSONDecodeError, TypeError):
                continue

            for src in sources:
                label = src if isinstance(src, str) else (src.get("label") or src.get("source") or "")
                if not label:
                    continue
                if label not in source_votes:
                    source_votes[label] = {"up": 0, "down": 0}
                if rating >= 4:
                    source_votes[label]["up"] += 1
                elif rating <= 2:
                    source_votes[label]["down"] += 1

        for label, votes in source_votes.items():
            delta = votes["up"] - votes["down"]
            mult = 1.0 + 0.05 * delta
            multipliers[label] = max(0.85, min(1.15, mult))

    except (sqlite3.Error, OSError):
        pass

    return multipliers


def get_feedback_multipliers() -> dict[str, float]:
    """Return cached per-source feedback multipliers, refreshing if stale."""
    global _cache, _cache_time
    now = time.time()
    if now - _cache_time > REFRESH_INTERVAL_SECONDS:
        with _lock:
            if now - _cache_time > REFRESH_INTERVAL_SECONDS:
                _cache = _load_source_feedback()
                _cache_time = now
    return _cache


def apply_feedback_boost(
    results: list[tuple[float, dict]],
) -> list[tuple[float, dict]]:
    """Apply per-source feedback multipliers to retrieval results.

    Each result whose source matches a label in the feedback multipliers
    has its score adjusted.  The results are re-sorted after adjustment.
    """
    multipliers = get_feedback_multipliers()
    if not multipliers:
        return results

    boosted: list[tuple[float, dict]] = []
    for score, chunk in results:
        source = chunk.get("source") or ""
        mult = multipliers.get(source, 1.0)
        boosted.append((score * mult, chunk))

    boosted.sort(key=lambda x: x[0], reverse=True)
    return boosted


def reset_cache() -> None:
    """Clear the feedback cache (for testing or after feedback imports)."""
    global _cache, _cache_time
    with _lock:
        _cache = {}
        _cache_time = 0.0
