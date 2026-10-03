import json

import pytest

from kenn.core import answer_upgrades, chat_answer
from kenn.llm import llm_rewrite


@pytest.fixture(params=["ollama", "openai"])
def provider_cache(monkeypatch, tmp_path, request):
    monkeypatch.setenv("KENN_LLM_CACHE", "1")
    monkeypatch.setenv("KENN_LLM_THINK", "off")
    monkeypatch.setattr(llm_rewrite, "_get_db_path", lambda: tmp_path / "llm_cache.db")
    monkeypatch.setattr(llm_rewrite, "mlx_selected", lambda task: False)
    monkeypatch.setattr(llm_rewrite, "config", lambda task: {
        "provider": request.param, "model": "kenn-brain-qwen3-8b",
        "base_url": "http://127.0.0.1:11434/v1", "timeout": 20, "api_key": "",
    })
    monkeypatch.setattr(answer_upgrades, "_TURNS", {})
    monkeypatch.setattr(answer_upgrades, "_RESULTS", {})
    state = {"calls": 0, "revoke": lambda: None}

    class Reply:
        def __init__(self, content, native):
            self.content, self.native = content, native

        def raise_for_status(self):
            pass

        def json(self):
            state["revoke"]()
            return {"message": {"content": self.content}, "done": True,
                    "choices": [{"message": {"content": self.content}, "finish_reason": "stop"}]}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def iter_lines(self):
            if self.native:
                yield json.dumps({"message": {"content": self.content}, "done": False})
                state["revoke"]()
                yield json.dumps({"done": True})
            else:
                yield "data: " + json.dumps({"choices": [{"delta": {"content": self.content}}]})
                state["revoke"]()
                yield "data: [DONE]"

    class Client:
        def post(self, url, **kwargs):
            state["calls"] += 1
            return Reply(f"response-{state['calls']}", url.endswith("/api/chat"))

        def stream(self, method, url, **kwargs):
            return self.post(url, **kwargs)

    monkeypatch.setattr(llm_rewrite, "_get_client", lambda: Client())

    def messages(question):
        return [{"role": "user", "content": question}]

    def payload_engine(question, *args, **kwargs):
        content, _ = llm_rewrite._chat_completion(messages(question), "rewrite")
        return {"answer": content}

    def stream_engine(question, *args, **kwargs):
        for content, usage in llm_rewrite.chat_completion_stream(messages(question), "rewrite"):
            if content:
                yield {"event": "token", "token": content}
            if usage:
                yield {"event": "metadata", "data": {"answer": "Completed"}}

    monkeypatch.setattr(chat_answer, "_answer_payload", payload_engine)
    monkeypatch.setattr(chat_answer, "_answer_payload_stream", stream_engine)

    def cached_answer(question):
        return llm_rewrite._chat_completion(messages(question), "rewrite")

    return state, cached_answer


@pytest.mark.parametrize("surface", ["payload", "stream"])
@pytest.mark.parametrize("revocation", ["cancel", "replacement", "other_chat"])
def test_superseded_chat_cannot_populate_the_provider_response_cache(provider_cache, surface, revocation):
    # Final provider text used to enter SQLite even after the request lost delivery ownership.
    state, cached_answer = provider_cache
    if revocation == "cancel":
        state["revoke"] = lambda: answer_upgrades.invalidate("song-a")
    else:
        state["revoke"] = lambda: answer_upgrades.begin_turn("song-a" if revocation == "replacement" else "song-b")
    with llm_rewrite.capture_usage() as records:
        if surface == "payload":
            chat_answer.answer_payload("Explain bass compression", session_id="song-a")
        else:
            list(chat_answer.answer_payload_stream("Explain bass compression", session_id="song-a"))
    assert len(records) == 1 and records[0].provider_attempted and records[0].provider_done
    state["revoke"] = lambda: None
    content, usage = cached_answer("Explain bass compression")
    current = revocation == "other_chat"
    assert content == ("response-1" if current else "response-2")
    assert usage.cache_hit is current
    assert state["calls"] == (1 if current else 2)


def test_suspended_stream_does_not_lend_its_cache_owner_to_other_calls(provider_cache):
    state, cached_answer = provider_cache
    first = chat_answer.answer_payload_stream("First question", session_id="song-a")
    second = chat_answer.answer_payload_stream("Second question", session_id="song-b")
    assert next(first)["token"] == "response-1"
    assert next(second)["token"] == "response-2"
    answer_upgrades.invalidate("song-a")
    assert cached_answer("Unbound question")[0] == "response-3"
    list(first)
    list(second)
    assert cached_answer("First question")[1].cache_hit is False
    assert cached_answer("Second question")[1].cache_hit is True
    assert cached_answer("Unbound question")[1].cache_hit is True
    assert state["calls"] == 4


def test_closing_a_cancelled_stream_keeps_cleanup_cache_writes_revoked(provider_cache, monkeypatch):
    _, cached_answer = provider_cache
    cleanup = []

    def engine(*args, **kwargs):
        try:
            yield {"event": "token", "token": "Draft"}
        finally:
            cached_answer("Cleanup question")
            cleanup.append(True)

    monkeypatch.setattr(chat_answer, "_answer_payload_stream", engine)
    stream = chat_answer.answer_payload_stream("First question", session_id="song-a")
    next(stream)
    answer_upgrades.invalidate("song-a")
    stream.close()
    assert cleanup == [True]
    assert cached_answer("Cleanup question")[1].cache_hit is False


def test_failed_payload_restores_unbound_provider_cache_writes(provider_cache, monkeypatch):
    _, cached_answer = provider_cache

    def engine(*args, **kwargs):
        answer_upgrades.invalidate("song-a")
        raise RuntimeError("Failed request")

    monkeypatch.setattr(chat_answer, "_answer_payload", engine)
    with pytest.raises(RuntimeError, match="Failed request"):
        chat_answer.answer_payload("First question", session_id="song-a")
    assert cached_answer("Unbound question")[1].cache_hit is False
    assert cached_answer("Unbound question")[1].cache_hit is True


def test_failed_stream_restores_unbound_provider_cache_writes(provider_cache, monkeypatch):
    _, cached_answer = provider_cache

    def engine(*args, **kwargs):
        yield {"event": "token", "token": "Draft"}
        answer_upgrades.invalidate("song-a")
        raise RuntimeError("Failed stream")

    monkeypatch.setattr(chat_answer, "_answer_payload_stream", engine)
    stream = chat_answer.answer_payload_stream("First question", session_id="song-a")
    next(stream)
    with pytest.raises(RuntimeError, match="Failed stream"):
        next(stream)
    assert cached_answer("Unbound question")[1].cache_hit is False
    assert cached_answer("Unbound question")[1].cache_hit is True


@pytest.mark.parametrize("surface", ["payload", "stream", "background"])
def test_provider_cache_save_holds_the_request_owner_lock(provider_cache, monkeypatch, surface):
    _, cached_answer = provider_cache
    saved_under_lock = []
    save = llm_rewrite._cache_put_unchecked

    def track_save(key, content):
        saved_under_lock.append(answer_upgrades._LOCK.locked())
        save(key, content)

    monkeypatch.setattr(llm_rewrite, "_cache_put_unchecked", track_save)
    if surface == "stream":
        list(chat_answer.answer_payload_stream("First question", session_id="song-a"))
    else:
        kwargs = {}
        if surface == "background":
            kwargs = {"request_turn_id": answer_upgrades.begin_turn("song-a"), "record_session": False}
        chat_answer.answer_payload("First question", session_id="song-a", **kwargs)
    assert saved_under_lock == [True]
    assert cached_answer("First question")[1].cache_hit is True
