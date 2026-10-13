"""A template left behind by a failed model request must not be cached on the non-streaming path either.

2 Oct 2026 fixed this for the stream: a timed-out stream left a high-confidence template that the semantic cache
kept for an hour, so the same question never reached the model again even after the load had gone. The same
receipt recorded that `answer_payload()` (the companion's /api/ask when background upgrades are off, the
default) was never marked and was left alone. It still cached that template: `_may_store_in_semantic_cache` only
read `generation_validation.transient`, which the payload path never sets. Found 13 Oct 2026 while preparing the
C1 warm-cache runs, where it would make a second foreground pass look like a 0.1 s template answer.
"""

from __future__ import annotations

import pytest

from kenn.core import chat_answer, chat_retrieval, route_log, session_memory
from kenn.llm import llm_rewrite as llm
from kenn.tests.test_streamed_generation_prefix_guard import ACCEPTED_ANSWER, CHUNKS, QUERY


def _model(monkeypatch, reply) -> None:
    """Run the real enhance() and make_answer(), with only the model call faked: text, or an exception to raise."""
    def completion(*args, **kwargs):
        if isinstance(reply, BaseException):
            raise reply
        return reply, None

    monkeypatch.setattr(llm, "is_enabled", lambda *a, **k: True)
    monkeypatch.setattr(llm, "_build_synthesis_messages", lambda *a, **k: ([{"role": "user", "content": "q"}], []))
    monkeypatch.setattr(llm, "_chat_completion", completion)
    monkeypatch.setattr(chat_answer, "llm_enhance_answer", llm.enhance)
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *a, **k: True)
    monkeypatch.setattr(chat_answer, "results_are_weak", lambda *a: False)
    monkeypatch.setattr(chat_answer, "intent_guard_failed", lambda *a: False)


@pytest.fixture
def cache_writes(monkeypatch, tmp_path):
    """answer_payload() over fixture retrieval with the semantic cache reachable; returns what it tried to save."""
    saved = []
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr(session_memory, "SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr(session_memory, "get_semantic_cache_hit", lambda *a, **k: None)
    monkeypatch.setattr(session_memory, "save_to_semantic_cache", lambda query, events, **k: saved.append(events))
    monkeypatch.setattr(route_log, "record", lambda *a, **k: None)
    monkeypatch.setattr(chat_answer, "_critique_and_save_trace", lambda **kwargs: None)
    monkeypatch.setattr(chat_answer, "mix_review_timeline_lookup", lambda query: None)
    monkeypatch.setattr(chat_answer, "latest_track_memory_lookup", lambda query: None)
    terms = {"total_docs": 0, "avg_len": 1.0, "lengths": [], "idf": {}, "postings": {}}
    for module in (chat_retrieval, chat_answer):
        monkeypatch.setattr(module, "load_chunks", lambda: [c for _, c in CHUNKS])
        monkeypatch.setattr(module, "load_terms", lambda: terms)
        monkeypatch.setattr(module, "search", lambda *args, **kwargs: list(CHUNKS))
    return saved


def _ask() -> dict:
    # record_session=True, no history and no session: the plain shape of request that reads and writes the cache.
    # With a session id this fixture question counts as session-dependent and never touches the cache at all.
    return chat_answer.answer_payload(QUERY)


@pytest.mark.parametrize("failure", [TimeoutError("timed out"), RuntimeError("connection refused after retry")])
def test_the_template_left_by_a_failed_model_request_is_not_cached(monkeypatch, cache_writes, failure):
    _model(monkeypatch, failure)

    payload = _ask()

    assert payload["llm_enhanced"] is False
    assert payload["generation_transient"] is True
    assert payload["generation_outcome"] == "generation returned no answer: request failed"
    assert cache_writes == []


def test_a_structure_check_failure_is_still_cached(monkeypatch, cache_writes):
    # The model writing unusable prose tends to repeat for the same prompt, like a guard trip on the stream,
    # so that template may stand in for an hour. Only a failed request says nothing about the next try.
    _model(monkeypatch, "Use a linear-phase EQ on the master bus.")

    payload = _ask()

    assert payload["llm_enhanced"] is False
    assert payload["generation_outcome"] == "generation returned no answer: structure check"
    assert payload["generation_transient"] is False
    assert len(cache_writes) == 1


def test_an_accepted_answer_is_still_cached(monkeypatch, cache_writes):
    _model(monkeypatch, ACCEPTED_ANSWER)

    payload = _ask()

    assert payload["llm_enhanced"] is True
    assert payload["generation_transient"] is False
    assert len(cache_writes) == 1


def test_a_stale_failure_from_an_earlier_answer_on_the_thread_does_not_leak(monkeypatch, cache_writes):
    # make_answer() resets its per-thread outcome on entry; the transient flag must follow the same rule, or a
    # timeout on one question would keep the next, successful one out of the cache.
    _model(monkeypatch, TimeoutError("timed out"))
    _ask()
    # The next answer returns its template before any model call (weak results), so nothing on this request
    # failed; only a stale flag could mark it transient.
    monkeypatch.setattr(chat_answer, "results_are_weak", lambda *a: True)

    payload = _ask()

    assert payload["generation_outcome"] == "model not asked: weak results or intent guard"
    assert payload["generation_transient"] is False


def test_the_cache_predicate_reads_the_payload_flag():
    assert chat_answer._may_store_in_semantic_cache({"confidence": "high", "generation_transient": True}) is False
    assert chat_answer._may_store_in_semantic_cache({"confidence": "high", "generation_transient": False}) is True
