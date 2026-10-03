"""A question answered from the semantic cache is still a turn in the session.

The engine records the exchange when it runs, and a cache hit skips the engine. Ask A, then B, then A again and
the session still said the last question was B with two turns, so the next follow-up resolved against the wrong
exchange. The replayed payload also carried the session block from the first asking.
"""

from __future__ import annotations

import pytest

from kenn.core import answer_upgrades, chat_answer, session_memory

FIRST = "Explain compressor release"
SECOND = "What does a limiter ceiling do?"


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
    monkeypatch.setattr(chat_answer, "mix_review_timeline_lookup", lambda query: None)
    monkeypatch.setattr(chat_answer, "latest_track_memory_lookup", lambda query: None)


def _engine(monkeypatch):
    """Stands in for the real tail of the engine: record the turn, then attach the session block."""
    runs = []

    def raw(query, *args, session_id="", **kwargs):
        runs.append(query)
        answer = f"Answer to {query}"
        chat_answer._update_session(
            query, answer, route="knowledge", answer_mode="short", confidence="high",
            intent="explain", session_id=session_id, retrieved_results=[(1.0, {"title": "first asking"})],
        )
        return {
            "answer": answer, "confidence": "high", "route": "knowledge", "answer_mode": "short",
            "intent": "explain", "session": chat_answer._session_info(session_id=session_id),
        }

    monkeypatch.setattr(chat_answer, "_answer_payload_raw", raw)
    return runs


def _stream_engine(monkeypatch):
    runs = []

    def engine(query, *args, session_id="", **kwargs):
        runs.append(query)
        answer = f"Answer to {query}"
        yield {"event": "metadata", "data": {
            "answer": answer, "confidence": "high", "route": "knowledge", "answer_mode": "short",
            "intent": "explain",
        }}
        yield {"event": "token", "token": answer}
        chat_answer._update_session(
            query, answer, route="knowledge", answer_mode="short", confidence="high",
            intent="explain", session_id=session_id, retrieved_results=[],
        )
        yield {"event": "session", "data": chat_answer._session_info(session_id=session_id)}

    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", engine)
    return runs


def test_a_repeated_question_answered_from_the_cache_still_counts_as_a_turn(monkeypatch):
    runs = _engine(monkeypatch)
    chat_answer.answer_payload(FIRST, session_id="song-a")
    chat_answer.answer_payload(SECOND, session_id="song-a")
    again = chat_answer.answer_payload(FIRST, session_id="song-a")
    state = session_memory.load_session(session_id="song-a")
    assert again["semantic_cache_hit"] is True and runs == [FIRST, SECOND]
    assert state["turn_count"] == 3
    assert state["last_question"] == FIRST and state["last_answer"] == f"Answer to {FIRST}"


def test_the_replayed_payload_carries_the_session_as_it_is_now(monkeypatch):
    _engine(monkeypatch)
    first = chat_answer.answer_payload(FIRST, session_id="song-a")
    chat_answer.answer_payload(SECOND, session_id="song-a")
    again = chat_answer.answer_payload(FIRST, session_id="song-a")
    assert first["session"]["turn_count"] == 1
    assert again["session"]["turn_count"] == 3 and again["session"]["last_question"] == FIRST


def test_retrieval_results_from_the_first_asking_are_not_kept_for_the_replayed_turn(monkeypatch):
    _engine(monkeypatch)
    chat_answer.answer_payload(FIRST, session_id="song-a")
    chat_answer.answer_payload(FIRST, session_id="song-a")
    assert not session_memory.load_session(session_id="song-a").get("last_retrieved_results")


def test_a_streamed_cache_hit_records_the_turn_and_replays_a_fresh_session_event(monkeypatch):
    runs = _stream_engine(monkeypatch)
    list(chat_answer.answer_payload_stream(FIRST, session_id="song-a"))
    list(chat_answer.answer_payload_stream(SECOND, session_id="song-a"))
    events = list(chat_answer.answer_payload_stream(FIRST, session_id="song-a"))
    metadata = next(e["data"] for e in events if e["event"] == "metadata")
    session = next(e["data"] for e in events if e["event"] == "session")
    state = session_memory.load_session(session_id="song-a")
    assert metadata["semantic_cache_hit"] is True and runs == [FIRST, SECOND]
    assert state["turn_count"] == 3 and state["last_question"] == FIRST
    assert session["turn_count"] == 3 and session["last_question"] == FIRST


@pytest.mark.parametrize("supersede", ["cancel", "next-turn"])
def test_a_streamed_cache_hit_superseded_just_before_the_replay_records_nothing(monkeypatch, supersede):
    _stream_engine(monkeypatch)
    list(chat_answer.answer_payload_stream(FIRST, session_id="song-a"))

    def superseded_while_checking_shortcuts(*args, **kwargs):
        if supersede == "cancel":
            answer_upgrades.invalidate("song-a")
        else:
            answer_upgrades.begin_turn("song-a")

    monkeypatch.setattr(chat_answer, "_short_circuit_evaluator", superseded_while_checking_shortcuts)
    owner = answer_upgrades.begin_turn("song-a")
    events = list(chat_answer._answer_payload_stream(FIRST, session_id="song-a", request_turn_id=owner))
    assert [e["data"].get("answer_delivery_discarded") for e in events if e["event"] == "metadata"] == [True]
    assert session_memory.load_session(session_id="song-a")["turn_count"] == 1


@pytest.mark.parametrize("supersede", ["cancel", "next-turn", "other-chat"])
def test_payload_cache_hit_rechecks_the_owner_before_recording_the_turn(monkeypatch, supersede):
    _engine(monkeypatch)
    chat_answer.answer_payload(FIRST, session_id="song-a")
    get_hit = session_memory.get_semantic_cache_hit

    def superseded_during_cache_lookup(*args, **kwargs):
        cached = get_hit(*args, **kwargs)
        if supersede == "cancel":
            answer_upgrades.invalidate("song-a")
        else:
            answer_upgrades.begin_turn("song-b" if supersede == "other-chat" else "song-a")
        return cached

    monkeypatch.setattr(session_memory, "get_semantic_cache_hit", superseded_during_cache_lookup)
    result = chat_answer.answer_payload(FIRST, session_id="song-a")
    if supersede == "other-chat":
        assert result["semantic_cache_hit"] is True
        assert session_memory.load_session(session_id="song-a")["turn_count"] == 2
    else:
        assert result["answer_delivery_discarded"] is True and result["answer"] == ""
        assert session_memory.load_session(session_id="song-a")["turn_count"] == 1
