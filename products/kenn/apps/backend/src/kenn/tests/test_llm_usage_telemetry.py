"""Provider failures and closed streams must remain visible without retaining their text."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import httpx
import pytest

from kenn.llm import llm_rewrite


MESSAGES = [{"role": "system", "content": "Use the evidence."}, {"role": "user", "content": "Explain compression."}]
METRICS = {
    "done": True, "done_reason": "stop", "prompt_eval_count": 200, "eval_count": 25,
    "total_duration": 5_123_456_789, "load_duration": 1_234_567,
    "prompt_eval_duration": 3_123_456_789, "eval_duration": 2_000_000_000,
    "prompt_eval_cached_count": 145,
}


class Reply:
    def __init__(self, data):
        self.data = data
        self.closed = False

    def raise_for_status(self):
        pass

    def json(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def iter_lines(self):
        for item in self.data:
            if isinstance(item, Exception):
                raise item
            yield item if isinstance(item, str) else json.dumps(item)


@pytest.fixture
def offline(monkeypatch):
    cfg = {"provider": "ollama", "model": "kenn-brain-qwen3-8b",
           "base_url": "http://127.0.0.1:11434/v1", "timeout": 20, "api_key": ""}
    writes = []
    monkeypatch.setattr(llm_rewrite, "config", lambda task="rewrite": cfg)
    monkeypatch.setattr(llm_rewrite, "mlx_selected", lambda task: False)
    monkeypatch.setattr(llm_rewrite, "is_enabled", lambda task="rewrite": True)
    monkeypatch.setattr(llm_rewrite, "_cache_get", lambda key: None)
    monkeypatch.setattr(llm_rewrite, "_cache_put", lambda key, text: writes.append(text))
    monkeypatch.setattr(llm_rewrite, "_global_usage", [])
    monkeypatch.setenv("KENN_LLM_THINK", "off")
    return writes


def _post(monkeypatch, data):
    reply = Reply(data)
    monkeypatch.setattr(llm_rewrite, "_get_client", lambda: SimpleNamespace(post=lambda *a, **k: reply))
    return reply


def _stream(monkeypatch, lines):
    reply = Reply(lines)
    monkeypatch.setattr(llm_rewrite, "_get_client", lambda: SimpleNamespace(stream=lambda *a, **k: reply))
    return reply


def _assert_metrics(usage):
    assert usage.provider_total_duration_ns == METRICS["total_duration"]
    assert usage.load_duration_ns == METRICS["load_duration"]
    assert usage.prompt_eval_duration_ns == METRICS["prompt_eval_duration"]
    assert usage.eval_duration_ns == METRICS["eval_duration"]
    assert usage.prompt_eval_cached_count == 145
    assert usage.completion_reason == "stop" and usage.provider_done is True
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (200, 25, 225)


@pytest.mark.parametrize("task", ["rewrite", "command"])
def test_native_reply_preserves_phase_durations_in_nanoseconds(offline, monkeypatch, task):
    _post(monkeypatch, {**METRICS, "message": {"content": "Grounded answer"}})
    with llm_rewrite.capture_usage() as calls:
        text, usage = llm_rewrite._chat_completion(MESSAGES, task=task)
    assert text == "Grounded answer" and calls == [usage]
    assert usage.status == "completed" and usage.task == task
    _assert_metrics(usage)


def test_direct_route_call_is_counted_with_its_native_metrics(offline, monkeypatch):
    _post(monkeypatch, {**METRICS, "message": {"content": "production"}})
    with llm_rewrite.capture_usage() as calls:
        assert llm_rewrite.llm_route_query("Explain compression") == "production"
    assert len(calls) == 1 and calls[0].task == "route"
    _assert_metrics(calls[0])


@pytest.mark.parametrize("cached_count", [None, 0])
def test_missing_native_metrics_remain_unknown_and_explicit_zero_is_preserved(offline, monkeypatch, cached_count):
    data = {"message": {"content": "Grounded answer"}, "done": True}
    if cached_count is not None:
        data["prompt_eval_cached_count"] = cached_count
    _post(monkeypatch, data)
    _, usage = llm_rewrite._chat_completion(MESSAGES)
    assert usage.prompt_eval_cached_count == cached_count
    assert usage.provider_total_duration_ns is None and usage.load_duration_ns is None
    assert usage.prompt_eval_duration_ns is None and usage.eval_duration_ns is None
    assert usage.completion_reason is None


@pytest.mark.parametrize("value", [-1, True, 1.25, "123", None])
def test_malformed_optional_timing_does_not_break_an_answer(offline, monkeypatch, value):
    _post(monkeypatch, {"message": {"content": "Grounded answer"}, "load_duration": value})
    text, usage = llm_rewrite._chat_completion(MESSAGES)
    assert text == "Grounded answer" and usage.load_duration_ns is None


def test_empty_reply_keeps_metrics_but_counts_as_failed_and_is_not_cached(offline, monkeypatch):
    _post(monkeypatch, {**METRICS, "message": {"content": ""}})
    with llm_rewrite.capture_usage() as calls, pytest.raises(ValueError, match="empty content"):
        llm_rewrite._chat_completion(MESSAGES)
    assert len(calls) == 1 and calls[0].status == "failed"
    assert calls[0].error_type == "ValueError" and offline == []
    _assert_metrics(calls[0])


def test_connection_retry_records_two_attempts_without_counting_the_pause_twice(offline, monkeypatch):
    failures = [httpx.ConnectError("private connection detail"), Reply({**METRICS, "message": {"content": "Answer"}})]
    def post(*args, **kwargs):
        item = failures.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    clocks = iter([10.0, 10.25, 12.0, 12.5])
    pauses = []
    monkeypatch.setattr(llm_rewrite, "time", SimpleNamespace(perf_counter=lambda: next(clocks), sleep=pauses.append))
    monkeypatch.setattr(llm_rewrite, "_get_client", lambda: SimpleNamespace(post=post))
    with llm_rewrite.capture_usage() as calls:
        assert llm_rewrite._chat_completion(MESSAGES)[0] == "Answer"
    assert [call.status for call in calls] == ["failed", "completed"]
    assert [call.latency_ms for call in calls] == [250, 500] and pauses == [1.0]
    assert calls[0].error_type == "ConnectError"
    assert "private connection detail" not in json.dumps([call.to_dict() for call in calls])


def test_native_stream_final_usage_contains_phase_metrics(offline, monkeypatch):
    _stream(monkeypatch, [{"message": {"content": "Answer"}}, METRICS])
    with llm_rewrite.capture_usage() as calls:
        chunks = list(llm_rewrite.chat_completion_stream(MESSAGES))
    assert chunks[0] == ("Answer", None) and chunks[-1] == ("", calls[0])
    assert calls[0].status == "completed" and offline == ["Answer"]
    _assert_metrics(calls[0])


@pytest.mark.parametrize("final_frame", [False, True])
def test_closed_stream_records_once_and_never_caches_its_candidate(offline, monkeypatch, final_frame):
    frame = {"message": {"content": "Candidate text"}, **(METRICS if final_frame else {})}
    reply = _stream(monkeypatch, [frame])
    with llm_rewrite.capture_usage() as calls:
        generator = llm_rewrite.chat_completion_stream(MESSAGES)
        assert next(generator) == ("Candidate text", None)
        generator.close()
        generator.close()
    assert reply.closed and offline == []
    assert len(calls) == len(llm_rewrite.get_accumulated_usage()) == 1
    assert calls[0].status == "interrupted" and calls[0].provider_done is final_frame
    assert "Candidate text" not in json.dumps(calls[0].to_dict())
    if final_frame:
        _assert_metrics(calls[0])
    else:
        assert calls[0].eval_duration_ns is None


@pytest.mark.parametrize("failure,expected_error", [(httpx.ReadTimeout("private detail"), TimeoutError),
                                                   (ConnectionResetError("private detail"), RuntimeError)])
def test_stream_failures_still_record_attempts_without_error_text(offline, monkeypatch, failure, expected_error):
    _stream(monkeypatch, [{"message": {"content": "Partial"}}, failure])
    with llm_rewrite.capture_usage() as calls, pytest.raises(expected_error):
        list(llm_rewrite.chat_completion_stream(MESSAGES))
    assert len(calls) == 1 and calls[0].status == "failed" and offline == []
    assert calls[0].error_type == expected_error.__name__
    assert calls[0].provider_done is False and calls[0].provider_total_duration_ns is None
    assert "private detail" not in json.dumps(calls[0].to_dict())


def test_failure_after_native_done_retains_metrics_and_reports_failure(offline, monkeypatch):
    _stream(monkeypatch, [METRICS, ConnectionResetError("private detail")])
    with llm_rewrite.capture_usage() as calls, pytest.raises(RuntimeError):
        list(llm_rewrite.chat_completion_stream(MESSAGES))
    assert calls[0].status == "failed" and offline == []
    _assert_metrics(calls[0])


def test_openai_stream_keeps_token_counts_and_completion_reason_without_native_timings(offline, monkeypatch):
    cfg = {**llm_rewrite.config(), "provider": "openai"}
    monkeypatch.setattr(llm_rewrite, "config", lambda task="rewrite": cfg)
    _stream(monkeypatch, [
        'data: {"choices":[{"delta":{"content":"Answer"},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{},"finish_reason":"length"}],"usage":{"prompt_tokens":200,"completion_tokens":25,"total_tokens":225}}',
        'data: [DONE]',
    ])
    with llm_rewrite.capture_usage() as calls:
        list(llm_rewrite.chat_completion_stream(MESSAGES))
    usage = calls[0]
    assert usage.status == "completed" and usage.completion_reason == "length" and usage.provider_done is True
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (200, 25, 225)
    assert usage.provider_total_duration_ns is None and usage.prompt_eval_cached_count is None


@pytest.mark.parametrize("streaming", [False, True])
def test_failed_mlx_attempt_is_counted_before_the_existing_http_fallback(offline, monkeypatch, streaming):
    from kenn.tests.test_llm_generation_bounds import _mlx_engine

    engine = _mlx_engine(monkeypatch)
    def fail(*args, **kwargs):
        raise RuntimeError("private engine detail")
    engine.generate = engine.stream_generate = fail
    if streaming:
        _stream(monkeypatch, [{"message": {"content": "Answer"}}, METRICS])
    else:
        _post(monkeypatch, {**METRICS, "message": {"content": "Answer"}})
    with llm_rewrite.capture_usage() as calls:
        if streaming:
            list(llm_rewrite.chat_completion_stream(MESSAGES))
        else:
            llm_rewrite._chat_completion(MESSAGES)
    assert [call.provider for call in calls] == ["mlx", "ollama"]
    assert [call.status for call in calls] == ["failed", "completed"]
    assert calls[0].error_type == "RuntimeError" and calls[0].load_duration_ns is None
    _assert_metrics(calls[1])


def test_closed_mlx_stream_is_recorded_without_falling_back_or_caching(offline, monkeypatch):
    from kenn.tests.test_llm_generation_bounds import _mlx_engine

    _mlx_engine(monkeypatch)
    with llm_rewrite.capture_usage() as calls:
        generator = llm_rewrite.chat_completion_stream(MESSAGES)
        assert next(generator) == ("A short ", None)
        generator.close()
    assert len(calls) == 1 and calls[0].provider == "mlx" and calls[0].status == "interrupted"
    assert calls[0].eval_duration_ns is None and offline == []


def test_wire_eof_without_done_is_visible_as_incomplete(offline, monkeypatch):
    _stream(monkeypatch, [{"message": {"content": "Partial"}}])
    with llm_rewrite.capture_usage() as calls:
        list(llm_rewrite.chat_completion_stream(MESSAGES))
    assert calls[0].status == "incomplete" and calls[0].provider_done is False
    assert calls[0].eval_duration_ns is None


def test_response_cache_hit_is_forwarded_without_a_provider_attempt(offline, monkeypatch):
    monkeypatch.setattr(llm_rewrite, "_cache_get", lambda key: "Cached answer")
    monkeypatch.setattr(llm_rewrite, "_build_synthesis_messages", lambda *a, **k: (MESSAGES, []))
    with llm_rewrite.capture_usage() as calls:
        events = list(llm_rewrite.enhance_stream("q", "template", [], [], "", str, list))
    usage = [event["data"] for event in events if event["event"] == "llm_usage"]
    assert len(calls) == len(usage) == 1
    assert usage[0]["cache_hit"] is True and usage[0]["provider_attempted"] is False
    assert usage[0]["status"] == "cache_hit" and usage[0]["latency_ms"] == 0
    assert usage[0]["eval_duration_ns"] is None and offline == []
    stats = llm_rewrite.get_public_usage_stats()
    assert stats["provider_attempts"] == 0 and stats["cache_hits"] == 1


def test_grounding_rejection_closes_and_records_the_real_provider_stream(offline, monkeypatch):
    from kenn.tests.test_streamed_generation_prefix_guard import _stream as answer_stream, _text_and_metadata
    reply = _stream(monkeypatch, [{"message": {"content": token}}
                                for token in ["Set release to ", "900", " ms", "never delivered"]])
    with llm_rewrite.capture_usage() as calls:
        text, metadata = _text_and_metadata(list(answer_stream(monkeypatch, llm_rewrite.enhance_stream)))
    assert metadata["generation_validation"]["accepted"] is False
    assert metadata["generation_validation"]["unsupported_measurements"] == ["900ms"]
    assert "900" not in text and "never delivered" not in text
    assert reply.closed and offline == []
    assert len(calls) == 1 and calls[0].status == "interrupted"


def test_finished_provider_cost_is_kept_when_the_full_grounding_gate_rejects(offline, monkeypatch):
    from kenn.tests.test_streamed_generation_prefix_guard import LOW_OVERLAP_ANSWER, _stream as answer_stream, _text_and_metadata

    _stream(monkeypatch, [{"message": {"content": LOW_OVERLAP_ANSWER}}, METRICS])
    with llm_rewrite.capture_usage() as calls:
        _, metadata = _text_and_metadata(list(answer_stream(monkeypatch, llm_rewrite.enhance_stream)))
    assert metadata["generation_validation"]["accepted"] is False
    assert "generated answer has insufficient evidence overlap" in metadata["generation_validation"]["warnings"]
    assert len(calls) == 1 and calls[0].status == "completed"
    _assert_metrics(calls[0])


def test_usage_capture_isolates_threads_and_restores_after_an_exception(offline, monkeypatch):
    barrier = Barrier(2)
    def post(*args, **kwargs):
        barrier.wait(timeout=5)
        return Reply({**METRICS, "message": {"content": "Answer"}})
    monkeypatch.setattr(llm_rewrite, "_get_client", lambda: SimpleNamespace(post=post))
    def ask(task):
        with llm_rewrite.capture_usage() as calls:
            llm_rewrite._chat_completion(MESSAGES, task=task)
        return [call.task for call in calls]
    with llm_rewrite.capture_usage() as outer:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(ask, ["rewrite", "command"])) == [["rewrite"], ["command"]]
        with pytest.raises(ValueError), llm_rewrite.capture_usage() as inner:
            llm_rewrite._add_usage(llm_rewrite.LLMUsage(task="inner"))
            raise ValueError("test")
        llm_rewrite._add_usage(llm_rewrite.LLMUsage(task="outer"))
    assert [call.task for call in inner] == ["inner"]
    assert [call.task for call in outer] == ["outer"]
    assert llm_rewrite._usage_capture.get() is None
