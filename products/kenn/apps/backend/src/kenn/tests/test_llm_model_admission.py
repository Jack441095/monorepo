"""A held local stream must not admit another model request or delay a cached reply."""

from types import SimpleNamespace

import pytest

from kenn.llm import llm_rewrite as llm
from kenn.tests.test_llm_usage_telemetry import MESSAGES, Reply
from scripts.measure_model_admission import probe


@pytest.mark.parametrize("surface", ["payload", "stream"])
def test_foreground_model_request_is_busy_while_background_generation_holds_the_provider(surface):
    # Background-only admission previously allowed foreground generation to overlap it.
    result = probe(surface)
    assert result["peak_provider_requests"] == 1
    assert result["foreground_entered_before_background_release"] is False
    assert result["foreground_errors"] == ["LLMBusyError"]
    assert result["second_background_blocked"] is True


@pytest.fixture
def held_stream(monkeypatch):
    cfg = {"provider": "ollama", "model": "kenn-brain-qwen3-8b",
           "base_url": "http://127.0.0.1:11434/v1", "timeout": 20, "api_key": ""}
    calls = []
    reply = Reply([{"message": {"content": "First"}, "done": False},
                   {"message": {"content": "Last"}, "done": True}])
    def stream(*args, **kwargs):
        calls.append("stream")
        return reply
    def post(*args, **kwargs):
        calls.append("post")
        return Reply({"message": {"content": "Answer"}, "done": True})
    monkeypatch.setattr(llm, "config", lambda task="rewrite": cfg)
    monkeypatch.setattr(llm, "mlx_selected", lambda task: False)
    monkeypatch.setattr(llm, "is_enabled", lambda task="rewrite": True)
    monkeypatch.setattr(llm, "_cache_get", lambda key: None)
    monkeypatch.setattr(llm, "_cache_put", lambda *args: None)
    monkeypatch.setattr(llm, "_global_usage", [])
    monkeypatch.setattr(llm, "_get_client", lambda: SimpleNamespace(stream=stream, post=post))
    monkeypatch.setattr(llm.httpx, "post", post)
    monkeypatch.setenv("KENN_LLM_THINK", "off")
    first = llm.chat_completion_stream(MESSAGES)
    assert next(first) == ("First", None)
    try:
        yield first, calls, cfg, reply
    finally:
        first.close()


@pytest.mark.parametrize("surface", ["payload", "stream", "routing", "keep_alive"])
def test_held_local_stream_refuses_other_provider_work_without_queueing(held_stream, surface):
    first, calls, cfg, reply = held_stream
    with llm.capture_usage() as usage:
        if surface == "routing":
            assert llm.llm_route_query("Explain compression") is None
        elif surface == "keep_alive":
            llm._ping_ollama_keep_alive(cfg)
        else:
            with pytest.raises(llm.LLMBusyError):
                if surface == "payload":
                    llm.chat_completion(MESSAGES)
                else:
                    list(llm.chat_completion_stream(MESSAGES))
    assert calls == ["stream"]
    if surface != "keep_alive":
        assert len(usage) == 1
        assert usage[0].status == "busy" and usage[0].provider_attempted is False
        assert usage[0].error_type == "LLMBusyError" and usage[0].completion_tokens == 0
    assert not reply.closed
    first.close()
    assert reply.closed
    assert llm.chat_completion(MESSAGES) == "Answer"
    assert calls == ["stream", "post"]


@pytest.mark.parametrize("surface", ["payload", "stream"])
def test_cached_answer_stays_available_while_local_generation_is_busy(held_stream, monkeypatch, surface):
    monkeypatch.setattr(llm, "_cache_get", lambda key: "Cached answer")
    with llm.capture_usage() as usage:
        answer = ("".join(text for text, _ in llm.chat_completion_stream(MESSAGES))
                  if surface == "stream" else llm.chat_completion(MESSAGES))
    assert answer == "Cached answer" and held_stream[1] == ["stream"]
    assert usage[0].cache_hit is True and usage[0].provider_attempted is False


def test_busy_mlx_request_does_not_load_weights_or_fall_back_to_http(held_stream, monkeypatch):
    from kenn.llm.mlx_inference_engine import MLXInferenceEngine
    monkeypatch.setattr(llm, "mlx_selected", lambda task: True)
    monkeypatch.setattr(MLXInferenceEngine, "is_available", lambda: True)
    def forbidden():
        raise AssertionError("Busy generation loaded weights")
    monkeypatch.setattr(MLXInferenceEngine, "get_instance", forbidden)
    for call in (lambda: llm.chat_completion(MESSAGES), lambda: list(llm.chat_completion_stream(MESSAGES))):
        with pytest.raises(llm.LLMBusyError), llm.capture_usage() as usage:
            call()
        assert len(usage) == 1 and usage[0].provider == "mlx" and usage[0].status == "busy"
    assert held_stream[1] == ["stream"]


def test_remote_provider_remains_available_while_local_generation_is_busy(held_stream, monkeypatch):
    cfg = {**held_stream[2], "provider": "openai"}
    monkeypatch.setattr(llm, "config", lambda task="rewrite": cfg)
    monkeypatch.setattr(llm, "_get_client", lambda: SimpleNamespace(post=lambda *a, **k:
                        Reply({"choices": [{"message": {"content": "Remote answer"}}]})))
    assert llm.chat_completion(MESSAGES) == "Remote answer"


@pytest.mark.parametrize("surface", ["payload", "stream"])
def test_first_answer_owns_admission_before_client_startup_can_ping_the_model(held_stream, monkeypatch, surface):
    # Creating the shared HTTP client starts the pinger, which must not steal the first answer's slot.
    held_stream[0].close()
    get_client = llm._get_client
    def start_client():
        assert llm._model_slot.locked()
        llm._ping_ollama_keep_alive(held_stream[2])
        return get_client()
    monkeypatch.setattr(llm, "_get_client", start_client)
    if surface == "payload":
        assert llm.chat_completion(MESSAGES) == "Answer"
        assert held_stream[1] == ["stream", "post"]
    else:
        assert "".join(text for text, _ in llm.chat_completion_stream(MESSAGES)) == "FirstLast"
        assert held_stream[1] == ["stream", "stream"]


@pytest.mark.parametrize("surface", ["payload", "stream"])
def test_busy_model_keeps_the_grounded_template_on_both_chat_surfaces(held_stream, monkeypatch, surface):
    from kenn.core import chat_answer
    from kenn.tests.test_streamed_generation_prefix_guard import CHUNKS, QUERY, _stream, _text_and_metadata
    monkeypatch.setattr(chat_answer, "llm_enabled", lambda: True)
    monkeypatch.setattr(chat_answer, "should_use_llm_rewrite", lambda *a, **k: True)
    monkeypatch.setattr(llm, "_build_synthesis_messages", lambda *a, **k: (MESSAGES, []))
    with llm.capture_usage() as usage:
        if surface == "payload":
            monkeypatch.setattr(chat_answer, "llm_enhance_answer", llm.enhance)
            template, _ = chat_answer.make_answer(QUERY, list(CHUNKS), allow_llm=False)
            answer, enhanced = chat_answer.make_answer(QUERY, list(CHUNKS), allow_llm=True)
            assert answer == template and enhanced is False
        else:
            text, metadata = _text_and_metadata(list(_stream(monkeypatch, llm.enhance_stream)))
            assert text and "First" not in text and metadata["llm_enhanced"] is False
            assert metadata["generation_validation"]["accepted"] is False
    assert len(usage) == 1 and usage[0].status == "busy"
    assert held_stream[1] == ["stream"]
    assert llm.get_public_usage_stats()["busy_calls"] == 1


@pytest.mark.parametrize("surface", ["payload", "stream", "keep_alive"])
def test_failed_local_provider_releases_admission_for_the_next_answer(held_stream, monkeypatch, surface):
    first, calls, cfg, reply = held_stream
    first.close()
    def fail(*args, **kwargs):
        raise RuntimeError("Provider fixture failed")
    with monkeypatch.context() as patch:
        patch.setattr(llm, "_get_client", lambda: SimpleNamespace(post=fail, stream=fail))
        patch.setattr(llm.httpx, "post", fail)
        if surface == "keep_alive":
            llm._ping_ollama_keep_alive(cfg)
        else:
            with pytest.raises((RuntimeError, ValueError)):
                if surface == "payload":
                    llm.chat_completion(MESSAGES)
                else:
                    list(llm.chat_completion_stream(MESSAGES))
    assert llm.chat_completion(MESSAGES) == "Answer"
