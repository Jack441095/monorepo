"""The semantic cache replays knowledge answers, never answers that describe the session at one moment.

The non-stream path cached any high-confidence payload, so asking the same single-turn question twice replayed
the first proposal and its already-spent confirmation token without a fresh Live read. It also ignored the
plug-in session that the stream path already refuses to cache across.
"""

from __future__ import annotations

import pytest

from kenn.core import answer_upgrades, chat_answer, session_memory

QUESTION = "Explain compressor release"


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    from kenn.core import project_memory_advisory
    from kenn.retrieval import retrieval

    monkeypatch.setattr(answer_upgrades, "_TURNS", {})
    monkeypatch.setattr(answer_upgrades, "_RESULTS", {})
    monkeypatch.setattr(project_memory_advisory, "evaluate_memory_chat_intent", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(session_memory, "SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr(session_memory, "_L1_EXACT_CACHE", {})
    monkeypatch.setattr(session_memory, "_L2_MATRIX", None)
    for name in ("_L2_QUERIES", "_L2_SESSION_IDS", "_L2_VERSIONS", "_L2_EVENTS", "_L2_TIMESTAMPS"):
        monkeypatch.setattr(session_memory, name, [])
    monkeypatch.setattr(retrieval, "embed_text", lambda *args: None)


def _engine(monkeypatch, **extra):
    calls = []

    def raw(query, *args, **kwargs):
        calls.append(kwargs.get("plugin_session_id", ""))
        return {"answer": "Release sets recovery time.", "confidence": "high", **extra}

    monkeypatch.setattr(chat_answer, "_answer_payload_raw", raw)
    return calls


def test_a_plain_knowledge_answer_is_still_served_from_the_cache(monkeypatch):
    calls = _engine(monkeypatch)
    chat_answer.answer_payload(QUESTION, session_id="song-a")
    second = chat_answer.answer_payload(QUESTION, session_id="song-a")
    assert len(calls) == 1 and second["semantic_cache_hit"] is True


@pytest.mark.parametrize("extra", [
    {"proposal": {"id": "p1"}, "confirmation_token": "tok-1", "requires_confirmation": True},
    {"proposal": {"id": "p1"}},
    {"confirmation_token": "tok-1"},
    {"requires_confirmation": True},
    {"orchestration": {"agent_name": "live_reader"}},
])
def test_non_stream_state_bound_answers_are_not_cached(monkeypatch, extra):
    calls = _engine(monkeypatch, **extra)
    chat_answer.answer_payload(QUESTION, session_id="song-a")
    second = chat_answer.answer_payload(QUESTION, session_id="song-a")
    assert len(calls) == 2 and "semantic_cache_hit" not in second


def test_non_stream_plugin_bound_request_neither_reads_nor_writes_the_cache(monkeypatch):
    calls = _engine(monkeypatch)
    chat_answer.answer_payload(QUESTION, session_id="song-a", plugin_session_id="plugin-a")
    chat_answer.answer_payload(QUESTION, session_id="song-a", plugin_session_id="plugin-b")
    assert calls == ["plugin-a", "plugin-b"]
    assert session_memory.get_semantic_cache_hit(QUESTION, session_id="song-a") is None


def test_a_cache_entry_does_not_answer_a_later_plugin_bound_request(monkeypatch):
    calls = _engine(monkeypatch)
    chat_answer.answer_payload(QUESTION, session_id="song-a")
    again = chat_answer.answer_payload(QUESTION, session_id="song-a", plugin_session_id="plugin-a")
    assert calls == ["", "plugin-a"] and "semantic_cache_hit" not in again


def test_stream_orchestrator_answer_is_not_cached(monkeypatch):
    def engine(*args, **kwargs):
        yield {"event": "metadata", "data": {
            "answer": "Track 3 is Bass.", "confidence": "high", "orchestration": {"agent_name": "live_reader"},
        }}
        yield {"event": "token", "token": "Track 3 is Bass."}

    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", engine)
    list(chat_answer.answer_payload_stream(QUESTION, session_id="song-a"))
    assert session_memory.get_semantic_cache_hit(QUESTION, session_id="song-a") is None
