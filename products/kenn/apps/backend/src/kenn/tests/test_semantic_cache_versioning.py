"""Semantic answers must not survive a retrieval/index version change."""

from __future__ import annotations

import json
import time

from kenn.core import session_memory


def test_exact_semantic_cache_hit_requires_current_cache_version(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "kenn.db")
    monkeypatch.setattr(session_memory, "_semantic_cache_version", lambda: "current:v2")
    conn = session_memory._get_db()
    now = int(time.time())
    events = [{"event": "metadata", "data": {"route": "game_audio"}}]
    conn.execute(
        """INSERT INTO semantic_cache
           (query, embedding_json, events_json, cache_version, created_at, last_used_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("Chain Selector", "[]", json.dumps(events), "stale:v1", now, now),
    )
    conn.commit()

    assert session_memory.get_semantic_cache_hit("Chain Selector") is None

    conn.execute(
        """UPDATE semantic_cache SET cache_version = ? WHERE query = ?""",
        ("current:v2", "Chain Selector"),
    )
    conn.commit()

    assert session_memory.get_semantic_cache_hit("Chain Selector") == events
