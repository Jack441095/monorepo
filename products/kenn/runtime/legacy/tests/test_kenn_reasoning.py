import tempfile
import sqlite3
import pytest
from pathlib import Path

from kenn.knowledge.reasoning import (
    save_reasoning_trace,
    get_reasoning_trace,
    query_reasoning_traces,
    list_reasoning_history,
    init_db,
    _get_conn,
)

@pytest.fixture
def temp_db_env(monkeypatch):
    """Fixture to isolate reasoning DB in a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kenn.db"
        monkeypatch.setenv("KENN_DB_PATH", str(db_path))
        monkeypatch.setenv("KENN_CHATS_DIR", tmpdir)
        yield db_path

def test_db_initialization(temp_db_env):
    """Verify that reasoning tables and FTS5 index are created."""
    init_db()
    assert temp_db_env.exists()
    
    conn = sqlite3.connect(str(temp_db_env))
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "knowledge_reasoning" in tables
    assert "knowledge_reasoning_fts" in tables

def test_save_and_retrieve_trace(temp_db_env):
    """Verify saving a reasoning trace and retrieving it by ID or search query."""
    tid = save_reasoning_trace(
        query="How do I set Ableton compression threshold?",
        route="production",
        evidence_ids=["chunk1", "chunk2"],
        conclusion="Set it to -6 dB for gentle control.",
        confidence="high",
        tags=["compression", "threshold"],
    )
    assert tid is not None
    
    trace = get_reasoning_trace(tid)
    assert trace is not None
    assert trace["query"] == "How do I set Ableton compression threshold?"
    assert trace["route"] == "production"
    assert trace["evidence_ids"] == ["chunk1", "chunk2"]
    assert trace["conclusion"] == "Set it to -6 dB for gentle control."
    assert trace["confidence"] == "high"
    assert trace["tags"] == ["compression", "threshold"]
    
    matches = query_reasoning_traces("compression threshold")
    assert len(matches) == 1
    assert matches[0]["trace_id"] == tid


def test_query_ranks_by_relevance_not_recency(temp_db_env):
    """Regression (2026-07-27): query_reasoning_traces used to ORDER BY
    created_at DESC, so the most recent trace won regardless of topic --
    "whats 17 times 24" pulled in an unrelated joke asked moments earlier
    purely because both shared a stray word. An older, topically-relevant
    trace must now outrank a newer, unrelated one.
    """
    save_reasoning_trace(
        query="How do I sidechain a kick under a bassline?",
        route="production",
        evidence_ids=["chunk1"],
        conclusion="Duck the bass around 60-120Hz keyed off the kick.",
        confidence="high",
        tags=["sidechain", "bass"],
    )
    # A newer, completely unrelated trace saved after it.
    save_reasoning_trace(
        query="tell me a joke",
        route="chat",
        evidence_ids=[],
        conclusion="What's the difference between an engineer and a pizza?",
        confidence="medium",
        tags=["chat"],
    )

    matches = query_reasoning_traces("how do I sidechain the bass under a kick", limit=1)
    assert len(matches) == 1
    assert "sidechain" in matches[0]["query"].lower()


def test_query_with_only_stopwords_returns_no_hits(temp_db_env):
    """A query sharing nothing but stop words with past traces (e.g. "whats
    17 times 24" against a saved "tell me a joke" trace) must not surface an
    unrelated trace just because both contain common function words.
    """
    save_reasoning_trace(
        query="tell me a joke",
        route="chat",
        evidence_ids=[],
        conclusion="What's the difference between an engineer and a pizza?",
        confidence="medium",
        tags=["chat"],
    )

    matches = query_reasoning_traces("whats 17 times 24")
    assert matches == []


def test_retention_policy(temp_db_env):
    """Verify that saving traces over the limit of 1000 deletes the oldest."""
    init_db()
    
    from kenn.knowledge.reasoning import _apply_retention
    
    for i in range(5):
        save_reasoning_trace(
            query=f"Query {i}",
            route="test",
            evidence_ids=[f"chunk{i}"],
            conclusion=f"Conclusion {i}",
            confidence="medium",
            tags=[f"tag{i}"],
            trace_id=f"id-{i}",
        )
    
    history = list_reasoning_history()
    assert len(history) == 5
    
    with _get_conn() as conn:
        _apply_retention(conn, limit=3)
        
    history = list_reasoning_history()
    assert len(history) == 3
    queries = {t["query"] for t in history}
    assert queries == {"Query 4", "Query 3", "Query 2"}
    assert "Query 0" not in queries
    assert "Query 1" not in queries

def test_sqlite_fallback(temp_db_env, monkeypatch):
    """Verify that if SQLite is unavailable/locked, reasoning fails gracefully and returns fallback values."""
    def mock_get_conn():
        raise sqlite3.OperationalError("database is locked")
        
    monkeypatch.setattr("kenn.knowledge.reasoning._get_conn", mock_get_conn)
    
    tid = save_reasoning_trace(
        query="Query",
        route="test",
        evidence_ids=[],
        conclusion="Conclusion",
        confidence="medium",
    )
    assert tid is None
    
    trace = get_reasoning_trace("some-id")
    assert trace is None
    
    matches = query_reasoning_traces("something")
    assert matches == []


def test_build_template_answer_never_injects_past_reasoning_into_the_written_answer(temp_db_env):
    """2026-08-02: chat_answer.build_intent_answer used to stitch a "Past
    reasoning on this topic:" block (raw retrieved query/conclusion pairs
    from query_reasoning_traces) directly into the written answer. Jack
    live-reported this as a "very strange" response -- and
    tests/kenn/test_kenn_handoff_past_reasoning.py's docstring documents a
    worse, prior incident: the block's *global*, not topic-scoped, lookup
    once replaced an unrelated answer's actual content with a past,
    topically-different conclusion. Removed at the source (not just
    downstream-stripped for one consumer) -- this proves it stays gone even
    when the DB genuinely holds a matching past trace for the exact query.
    """
    from kenn.core import chat

    save_reasoning_trace(
        query="How do I sidechain bass to the kick?",
        route="production",
        evidence_ids=[],
        conclusion="I would approach the session like this.",
        confidence="medium",
        trace_id="dup-0",
    )

    mock_chunk = {
        "kind": "note",
        "title": "Sidechaining Kick and Bass",
        "source": "sidechain.md",
        "text": (
            "Tags: compression, bass, sidechain\nShort answer:\n"
            "Use sidechaining.\n\nTry this:\n1. Insert compressor.\n\n"
            "Avoid this:\nDon't bypass the check.\n\nWhy it matters:\nKeep it tidy."
        ),
    }
    results = [(15.0, mock_chunk)]

    answer = chat.build_template_answer(
        query="what's the best way to sidechain the bass to the kick drum",
        results=results,
        route="production",
    )

    assert "Past reasoning on this topic:" not in answer
    assert "I would approach the session like this." not in answer
