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


def test_semantic_cache_isolates_answers_between_project_sessions(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "kenn.db")
    monkeypatch.setattr(session_memory, "_semantic_cache_version", lambda: "current:v2")
    session_memory._L1_EXACT_CACHE.clear()
    session_memory._L2_QUERIES.clear()
    session_memory._L2_SESSION_IDS.clear()
    session_memory._L2_VERSIONS.clear()
    session_memory._L2_MATRIX = None
    session_memory._L2_EVENTS.clear()
    session_memory._L2_TIMESTAMPS.clear()

    events_a = [{"event": "token", "token": "Project A specific advice for Kick"}]
    events_b = [{"event": "token", "token": "Project B specific advice for Kick"}]

    # Save answer in Session A
    session_memory.save_to_semantic_cache("how to eq kick", events_a, session_id="project_alpha")

    # Session A retrieves its own cached answer
    assert session_memory.get_semantic_cache_hit("how to eq kick", session_id="project_alpha") == events_a

    # Session B must never receive Project A's advice
    assert session_memory.get_semantic_cache_hit("how to eq kick", session_id="project_beta") is None

    # Save distinct answer in Session B
    session_memory.save_to_semantic_cache("how to eq kick", events_b, session_id="project_beta")

    # Both projects receive their own isolated answers
    assert session_memory.get_semantic_cache_hit("how to eq kick", session_id="project_alpha") == events_a
    assert session_memory.get_semantic_cache_hit("how to eq kick", session_id="project_beta") == events_b


def test_soft_semantic_hit_does_not_pollute_l1_exact_cache(tmp_path, monkeypatch) -> None:
    import numpy as np

    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "kenn.db")
    monkeypatch.setattr(session_memory, "_semantic_cache_version", lambda: "current:v2")
    session_memory._L1_EXACT_CACHE.clear()
    session_memory._L2_QUERIES.clear()
    session_memory._L2_SESSION_IDS.clear()
    session_memory._L2_VERSIONS.clear()
    session_memory._L2_MATRIX = None
    session_memory._L2_EVENTS.clear()
    session_memory._L2_TIMESTAMPS.clear()

    # Create two close embeddings with cosine similarity ~0.97
    emb1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    emb2 = np.array([0.97, 0.24, 0.0], dtype=np.float32)
    emb2 = emb2 / np.linalg.norm(emb2)

    def fake_embed(text: str) -> np.ndarray:
        if "drum" in text:
            return emb2
        return emb1

    monkeypatch.setattr("kenn.retrieval.retrieval.embed_text", fake_embed)

    events = [{"event": "token", "token": "EQ kick at 60 Hz"}]
    session_memory.save_to_semantic_cache("eq kick", events, session_id="proj1")

    # Clear L1 to force query through L2 semantic matrix
    session_memory._L1_EXACT_CACHE.clear()

    # Query with slightly different wording: hits L2 with score >= 0.95
    hit = session_memory.get_semantic_cache_hit("eq kick drum", threshold=0.95, session_id="proj1")
    assert hit == events

    # L1 must NOT have recorded "eq kick drum" as an exact match
    assert ("proj1", "eq kick drum") not in session_memory._L1_EXACT_CACHE

    # Exact query populates L1
    hit_exact = session_memory.get_semantic_cache_hit("eq kick", session_id="proj1")
    assert hit_exact == events
    assert ("proj1", "eq kick") in session_memory._L1_EXACT_CACHE


def test_l2_cache_fifo_eviction_bounds_memory_to_max_size(tmp_path, monkeypatch) -> None:
    import numpy as np

    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "kenn.db")
    monkeypatch.setattr(session_memory, "_semantic_cache_version", lambda: "current:v2")
    monkeypatch.setattr("kenn.retrieval.retrieval.embed_text", lambda text: np.array([1.0, 0.0], dtype=np.float32))

    session_memory._L1_EXACT_CACHE.clear()
    session_memory._L2_QUERIES.clear()
    session_memory._L2_SESSION_IDS.clear()
    session_memory._L2_VERSIONS.clear()
    session_memory._L2_MATRIX = None
    session_memory._L2_EVENTS.clear()
    session_memory._L2_TIMESTAMPS.clear()

    # Temporarily set max size small to test FIFO eviction cleanly
    monkeypatch.setattr(session_memory, "_L2_MAX_SIZE", 5)

    for i in range(8):
        session_memory.save_to_semantic_cache(
            f"query_{i}",
            [{"event": "token", "token": f"answer_{i}"}],
            session_id="session_fifo",
        )

    # We bound L2 to _L2_MAX_SIZE (5 entries)
    assert len(session_memory._L2_QUERIES) == 5
    assert len(session_memory._L2_SESSION_IDS) == 5
    assert len(session_memory._L2_EVENTS) == 5
    assert session_memory._L2_MATRIX.shape[0] == 5
    # The oldest 3 entries (query_0, query_1, query_2) must have been evicted
    assert session_memory._L2_QUERIES == [f"query_{i}" for i in range(3, 8)]
