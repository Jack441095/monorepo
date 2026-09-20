"""Feedback-driven retrieval signals for KENN.

Reads aggregated user feedback from KENN's session_feedback table and computes
per-topic boosting multipliers.  Topics with consistently positive feedback get
a modest score boost; topics with negative feedback get a penalty.

The multipliers are cached in memory and refreshed lazily (at most once per
REFRESH_INTERVAL_SECONDS).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time

from kenn.core.session_memory import DB_PATH

REFRESH_INTERVAL_SECONDS = 300  # 5 minutes

_lock = threading.Lock()
_cache: dict[str, float] = {}
_cache_time: float = 0.0


def _load_topic_feedback() -> dict[str, float]:
    """Query the canonical session feedback table to build topic multipliers.

    The current feedback contract stores the topics shown for a turn directly
    on ``session_feedback``.  Older code joined a non-existent ``session_turns``
    table in a separate database, which made this loop silently inert.

    For each topic that has received explicit ratings:
    - Count thumbs-up (rating >= 4) and thumbs-down (rating <= 2).
    - Compute a smoothed multiplier using a two-vote neutral prior, clamped to
      [0.90, 1.10].

    This keeps adjustments subtle enough to avoid runaway feedback loops while
    still rewarding consistently-helpful retrieval topics.
    """
    if not DB_PATH.exists():
        return {}

    multipliers: dict[str, float] = {}
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT topics, explicit_rating
            FROM session_feedback
            WHERE explicit_rating IS NOT NULL
              AND topics IS NOT NULL
        """).fetchall()
        conn.close()

        topic_votes: dict[str, dict[str, int]] = {}
        for row in rows:
            try:
                rating = int(row["explicit_rating"])
            except (TypeError, ValueError):
                continue
            try:
                topics = json.loads(row["topics"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(topics, list):
                continue

            labels = {
                str(topic).strip().lower()
                for topic in topics
                if isinstance(topic, str) and str(topic).strip()
            }
            for label in labels:
                if not label or len(label) > 80:
                    continue
                if label not in topic_votes:
                    topic_votes[label] = {"up": 0, "down": 0}
                if rating >= 4:
                    topic_votes[label]["up"] += 1
                elif rating <= 2:
                    topic_votes[label]["down"] += 1

        for label, votes in topic_votes.items():
            up, down = votes["up"], votes["down"]
            smoothed_quality = (up + 1.0) / (up + down + 2.0)
            multipliers[label] = round(max(0.90, min(1.10, 0.90 + 0.20 * smoothed_quality)), 4)

    except (sqlite3.Error, OSError):
        pass

    return multipliers


def get_feedback_multipliers() -> dict[str, float]:
    """Return cached per-topic feedback multipliers, refreshing if stale."""
    global _cache, _cache_time
    now = time.time()
    if now - _cache_time > REFRESH_INTERVAL_SECONDS:
        with _lock:
            if now - _cache_time > REFRESH_INTERVAL_SECONDS:
                _cache = _load_topic_feedback()
                _cache_time = now
    return _cache


def apply_feedback_boost(
    results: list[tuple[float, dict]],
) -> list[tuple[float, dict]]:
    """Apply per-topic feedback multipliers to retrieval results.

    A result's topic multipliers are averaged, keeping the adjustment bounded
    even when a chunk has several topics.  Untagged chunks are unchanged.
    The results are re-sorted after adjustment.
    """
    multipliers = get_feedback_multipliers()
    if not multipliers:
        return results

    boosted: list[tuple[float, dict]] = []
    for score, chunk in results:
        topics = chunk.get("topics") or []
        topic_multipliers = [
            multipliers[str(topic).strip().lower()]
            for topic in topics
            if str(topic).strip().lower() in multipliers
        ]
        mult = sum(topic_multipliers) / len(topic_multipliers) if topic_multipliers else 1.0
        boosted.append((score * mult, chunk))

    boosted.sort(key=lambda x: x[0], reverse=True)
    return boosted


def reset_cache() -> None:
    """Clear the feedback cache (for testing or after feedback imports)."""
    global _cache, _cache_time
    with _lock:
        _cache = {}
        _cache_time = 0.0
