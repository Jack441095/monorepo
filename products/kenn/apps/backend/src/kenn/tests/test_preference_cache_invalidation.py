"""A cached answer carries the preference citation it was written with, so a preference change must clear it.

Before this, forgetting "I master to -9 dB" left the old answer, citation included, coming back from the semantic
cache for up to an hour.
"""

from __future__ import annotations

import numpy as np
import pytest

from kenn.core import session_memory
from kenn.core.assistant_profile_memory import AssistantProfileStore

KEY = "mix_priority"
QUESTION = "how loud should my master be"
EVENTS = [{"event": "metadata", "data": {"answer": "Aim for -9 dB.", "confidence": "high"}}]


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(session_memory, "_L1_EXACT_CACHE", {})
    monkeypatch.setattr(session_memory, "_L2_MATRIX", None)
    for name in ("_L2_QUERIES", "_L2_SESSION_IDS", "_L2_VERSIONS", "_L2_EVENTS", "_L2_TIMESTAMPS"):
        monkeypatch.setattr(session_memory, name, [])
    from kenn.retrieval import retrieval
    monkeypatch.setattr(retrieval, "embed_text", lambda *args: np.array([1.0, 0.0, 0.0], dtype=np.float32))


@pytest.fixture()
def store(tmp_path):
    return AssistantProfileStore(db_path=tmp_path / "profile.db")


def _warm(session_id: str) -> None:
    session_memory.save_to_semantic_cache(QUESTION, EVENTS, session_id=session_id)
    assert session_memory.get_semantic_cache_hit(QUESTION, session_id=session_id) == EVENTS


def _record(store, value="-9 dB", session_id="song-a"):
    return store.record_preference(session_id=session_id, key=KEY, value=value,
                                   source_turn_id="t1", user_statement=f"I master to {value}")


def _cached(session_id: str):
    return session_memory.get_semantic_cache_hit(QUESTION, session_id=session_id)


def test_drop_clears_every_tier_for_that_session_only():
    _warm("song-a")
    _warm("song-b")
    session_memory.drop_session_semantic_cache("song-a")
    assert _cached("song-a") is None
    assert _cached("song-b") == EVENTS
    assert session_memory._L2_SESSION_IDS == ["song-b"]
    assert session_memory._L2_MATRIX.shape[0] == 1
    rows = session_memory._get_db().execute("SELECT session_id FROM semantic_cache").fetchall()
    assert [row["session_id"] for row in rows] == ["song-b"]


def test_dropping_the_last_entry_leaves_an_empty_matrix():
    _warm("song-a")
    session_memory.drop_session_semantic_cache("song-a")
    assert session_memory._L2_MATRIX is None and session_memory._L2_QUERIES == []


def test_saving_a_preference_clears_the_sessions_cached_answers(store):
    _warm("song-a")
    _warm("song-b")
    assert _record(store)["ok"]
    assert _cached("song-a") is None
    assert _cached("song-b") == EVENTS


def test_a_rejected_preference_leaves_the_cache_alone(store):
    _warm("song-a")
    assert not store.record_preference(session_id="song-a", key="not_a_key", value="x",
                                       source_turn_id="t1", user_statement="x")["ok"]
    assert _cached("song-a") == EVENTS


def test_forgetting_a_preference_clears_cached_answers(store):
    _record(store)
    _warm("song-a")
    assert store.forget_preference(session_id="song-a", key=KEY)
    assert _cached("song-a") is None


def test_forgetting_a_preference_that_is_not_there_keeps_the_cache(store):
    _warm("song-a")
    assert not store.forget_preference(session_id="song-a", key=KEY)
    assert _cached("song-a") == EVENTS


def test_restoring_a_preference_clears_cached_answers(store):
    first = _record(store, "-12 dB")
    _record(store, "-9 dB")
    _warm("song-a")
    assert store.restore_preference(session_id="song-a", preference_id=first["preference"]["preference_id"])["restored"]
    assert _cached("song-a") is None


def test_restoring_an_already_active_preference_keeps_the_cache(store):
    current = _record(store)
    _warm("song-a")
    assert store.restore_preference(session_id="song-a", preference_id=current["preference"]["preference_id"])["restored"] is False
    assert _cached("song-a") == EVENTS


def test_clearing_the_profile_clears_cached_answers(store):
    _record(store)
    _warm("song-a")
    _warm("song-b")
    store.clear_profile("song-a")
    assert _cached("song-a") is None
    assert _cached("song-b") == EVENTS
