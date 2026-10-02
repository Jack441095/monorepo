"""The semantic cache replays knowledge answers, never answers that describe the session at one moment.

The non-stream path cached any high-confidence payload, so asking the same single-turn question twice replayed
the first proposal and its already-spent confirmation token without a fresh Live read. It also ignored the
plug-in session that the stream path already refuses to cache across.

Answers that lean on the session summary, an active diagnostic plan or a saved mix review are state-bound too:
none of that is in the cache key, so "is that too loud?" kept meaning whatever it meant the first time.
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
    monkeypatch.setattr(chat_answer, "mix_review_timeline_lookup", lambda query: None)
    monkeypatch.setattr(chat_answer, "latest_track_memory_lookup", lambda query: None)


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
    {"audiogen": {"job_id": "job-1", "status": "queued"}},
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


def _stream_engine(monkeypatch, **validation):
    def engine(*args, **kwargs):
        yield {"event": "metadata", "data": {
            "answer": "Release sets recovery time.", "confidence": "high",
            "generation_validation": {"attempted": True, "accepted": False, **validation},
        }}
        yield {"event": "token", "token": "Release sets recovery time."}

    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", engine)
    list(chat_answer.answer_payload_stream(QUESTION, session_id="song-a"))


def test_the_template_left_by_a_model_that_timed_out_is_not_cached(monkeypatch):
    _stream_engine(monkeypatch, transient=True)
    assert session_memory.get_semantic_cache_hit(QUESTION, session_id="song-a") is None


def test_the_template_left_by_a_rejected_answer_is_still_cached(monkeypatch):
    _stream_engine(monkeypatch, transient=False)
    assert session_memory.get_semantic_cache_hit(QUESTION, session_id="song-a") is not None


FOLLOWUP = "is that too loud?"
ELLIPTICAL = "the kick is still boomy"


def test_the_fixtures_for_state_bound_questions_mean_what_they_say():
    assert chat_answer.is_followup_query(FOLLOWUP)
    assert not chat_answer.is_followup_query(ELLIPTICAL)
    assert not chat_answer.is_followup_query(QUESTION)


@pytest.mark.parametrize("query", [FOLLOWUP, ELLIPTICAL])
def test_a_followup_in_a_session_is_not_replayed_from_the_cache(monkeypatch, query):
    calls = _engine(monkeypatch)
    chat_answer.answer_payload(query, session_id="song-a")
    second = chat_answer.answer_payload(query, session_id="song-a")
    assert len(calls) == 2 and "semantic_cache_hit" not in second


def test_a_followup_with_no_session_has_no_state_to_depend_on(monkeypatch):
    calls = _engine(monkeypatch)
    chat_answer.answer_payload(FOLLOWUP)
    second = chat_answer.answer_payload(FOLLOWUP)
    assert len(calls) == 1 and second["semantic_cache_hit"] is True


def test_an_answer_to_a_reported_diagnostic_result_is_not_cached(monkeypatch):
    monkeypatch.setattr(chat_answer, "_is_diagnostic_result_report", lambda query, session_id: True)
    calls = _engine(monkeypatch)
    chat_answer.answer_payload(QUESTION, session_id="song-a")
    chat_answer.answer_payload(QUESTION, session_id="song-a")
    assert len(calls) == 2


@pytest.mark.parametrize("name,result", [
    ("mix_review_timeline_lookup", ("Demo", [{"created_at": "1"}])),
    ("latest_track_memory_lookup", {"title": "Demo"}),
])
def test_a_question_that_reads_saved_mix_reviews_is_not_cached(monkeypatch, name, result):
    monkeypatch.setattr(chat_answer, name, lambda query: result)
    calls = _engine(monkeypatch)
    chat_answer.answer_payload(QUESTION, session_id="song-a")
    chat_answer.answer_payload(QUESTION, session_id="song-a")
    assert len(calls) == 2


def test_a_review_saved_after_the_first_answer_reaches_the_second(monkeypatch):
    calls = _engine(monkeypatch)
    chat_answer.answer_payload(QUESTION, session_id="song-a")
    monkeypatch.setattr(chat_answer, "latest_track_memory_lookup", lambda query: {"title": "Demo"})
    chat_answer.answer_payload(QUESTION, session_id="song-a")
    assert len(calls) == 2


@pytest.mark.parametrize("query,lookup", [(FOLLOWUP, None), (QUESTION, "latest_track_memory_lookup")])
def test_the_stream_path_applies_the_same_state_gate(monkeypatch, query, lookup):
    if lookup:
        monkeypatch.setattr(chat_answer, lookup, lambda q: {"title": "Demo"})
    runs = []

    def engine(*args, **kwargs):
        runs.append(1)
        yield {"event": "metadata", "data": {"answer": "Fresh.", "confidence": "high"}}
        yield {"event": "token", "token": "Fresh."}

    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", engine)
    list(chat_answer.answer_payload_stream(query, session_id="song-a"))
    list(chat_answer.answer_payload_stream(query, session_id="song-a"))
    assert len(runs) == 2
