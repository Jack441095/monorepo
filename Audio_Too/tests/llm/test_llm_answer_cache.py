"""Tests for the KENN LLM answer cache (llm_rewrite).

Identical prompts (same model + messages) should reuse a cached answer instead of
paying 6-8 s of CPU generation again; different prompts (different context/history)
must miss; the cache must be disablable and bounded.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

KENN = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn"
if str(KENN) not in sys.path:
    sys.path.insert(0, str(KENN))

from kenn.llm import llm_rewrite as lr  # noqa: E402

_CFG = {
    "model": "test-model",
    "provider": "ollama",
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "",
    "timeout": 30,
    "enabled": True,
}


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {
            "choices": [{"message": {"content": self._content}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
        }


class _FakeClient:
    def __init__(self, content: str) -> None:
        self.calls = 0
        self._content = content

    def post(self, *args, **kwargs) -> _FakeResponse:
        self.calls += 1
        return _FakeResponse(self._content)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    lr.clear_answer_cache()
    monkeypatch.setenv("KENN_LLM_CACHE", "1")
    monkeypatch.setattr(lr, "config", lambda task="rewrite": dict(_CFG))
    yield
    lr.clear_answer_cache()


def _msgs(q: str) -> list[dict]:
    return [{"role": "user", "content": q}]


def test_identical_prompt_is_cached(monkeypatch):
    fake = _FakeClient("kick punch answer")
    monkeypatch.setattr(lr, "_get_client", lambda: fake)
    c1, _ = lr._chat_completion(_msgs("how do I make my kick punch"), system_prompt="sys")
    c2, u2 = lr._chat_completion(_msgs("how do I make my kick punch"), system_prompt="sys")
    assert c1 == c2 == "kick punch answer"
    assert fake.calls == 1  # second served from cache, no LLM call
    assert u2.task.endswith(":cached")


def test_different_prompt_misses(monkeypatch):
    fake = _FakeClient("answer")
    monkeypatch.setattr(lr, "_get_client", lambda: fake)
    lr._chat_completion(_msgs("question one"), system_prompt="sys")
    lr._chat_completion(_msgs("question two"), system_prompt="sys")
    assert fake.calls == 2


def test_cache_disabled_by_env(monkeypatch):
    monkeypatch.setenv("KENN_LLM_CACHE", "0")
    fake = _FakeClient("answer")
    monkeypatch.setattr(lr, "_get_client", lambda: fake)
    lr._chat_completion(_msgs("q"), system_prompt="sys")
    lr._chat_completion(_msgs("q"), system_prompt="sys")
    assert fake.calls == 2  # no caching when disabled


def test_streaming_path_is_cached(monkeypatch):
    fake = _FakeClient("x")  # unused for streaming; guards against accidental post()
    monkeypatch.setattr(lr, "_get_client", lambda: fake)
    # Pre-seed the cache as if a prior stream completed, then a stream hit should
    # replay it as a single chunk without calling the client.
    key = lr._cache_key(_CFG, [{"role": "system", "content": "sys"}, *_msgs("widen the mix")])
    lr._cache_put(key, "make it wider like this")
    chunks = list(lr.chat_completion_stream(_msgs("widen the mix"), system_prompt="sys"))
    text = "".join(c for c, _u in chunks)
    assert "make it wider like this" in text
    assert fake.calls == 0  # served from cache, no streaming call


def test_helpers_bound_and_clear():
    lr.clear_answer_cache()
    key = lr._cache_key({"model": "m"}, _msgs("x"))
    lr._cache_put(key, "v")
    assert lr._cache_get(key) == "v"
    lr.clear_answer_cache()
    assert lr._cache_get(key) is None


def test_topic_locking_context_reuse(monkeypatch):
    from kenn.core.chat_answer import _resolve_results_with_topic_lock
    from kenn.core import chat_answer as ca
    from kenn.core.session_memory import clear_session, update_session

    # Mock search function
    search_calls = 0
    def mock_search(query, chunks, terms, limit=8):
        nonlocal search_calls
        search_calls += 1
        return [(10.0, {"text": "dummy note text", "title": "dummy note", "source": "dummy"})]

    monkeypatch.setattr(ca, "search", mock_search)

    session_id = "test_session_topic_lock"
    clear_session(session_id)

    # First turn: fresh query (no history)
    history = []
    res1, use_history, relevance_query, search_query, reused = _resolve_results_with_topic_lock(
        "how do I compress vocals?", history, 4, [], {}, session_id
    )
    assert not use_history
    assert not reused
    assert search_calls == 1

    # Update session memory to cache the retrieved results
    update_session("how do I compress vocals?", "compressed vocals answer", session_id=session_id, retrieved_results=res1)

    # Second turn: follow-up query (use_history should be True)
    history = [
        {"role": "user", "content": "how do I compress vocals?"},
        {"role": "assistant", "content": "compressed vocals answer"}
    ]

    # We ask a follow-up
    res2, use_history2, relevance_query2, search_query2, reused2 = _resolve_results_with_topic_lock(
        "why does it matter?", history, 4, [], {}, session_id
    )
    assert use_history2
    assert reused2
    assert search_calls == 1  # search was bypassed!
    assert res1 == res2
