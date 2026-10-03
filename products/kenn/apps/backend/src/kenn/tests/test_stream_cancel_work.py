import json

import pytest

from kenn.core import answer_upgrades, chat_answer
from kenn.llm import llm_rewrite


@pytest.mark.parametrize("provider", ["ollama", "openai"])
@pytest.mark.parametrize("after", ["metadata", "token", "during_read"])
@pytest.mark.parametrize("revocation", ["cancel", "replacement", "other_chat", "unbound"])
def test_cancelled_stream_closes_without_starting_or_reading_more_model_work(monkeypatch, provider, after, revocation):
    # The owner check followed next(raw), allowing stale requests to start or read more inference.
    monkeypatch.setenv("KENN_LLM_CACHE", "0")
    monkeypatch.setenv("KENN_LLM_THINK", "off")
    monkeypatch.setattr(answer_upgrades, "_TURNS", {})
    monkeypatch.setattr(answer_upgrades, "_RESULTS", {})
    monkeypatch.setattr(chat_answer, "_short_circuit_evaluator", lambda *args, **kwargs: None)
    monkeypatch.setattr(llm_rewrite, "mlx_selected", lambda task: False)
    monkeypatch.setattr(llm_rewrite, "config", lambda task: {
        "provider": provider, "model": "kenn-brain-qwen3-8b",
        "base_url": "http://127.0.0.1:11434/v1", "timeout": 20, "api_key": "",
    })
    state = {"opened": 0, "reads": 0, "closed": 0, "raw_closed": 0}
    session_id = "" if revocation == "unbound" else "song-a"

    def revoke():
        if revocation == "cancel":
            answer_upgrades.invalidate("song-a")
        else:
            answer_upgrades.begin_turn("song-b" if revocation == "other_chat" else "song-a")

    class Reply:
        def __enter__(self):
            state["opened"] += 1
            return self

        def __exit__(self, *exc):
            state["closed"] += 1

        def raise_for_status(self):
            pass

        def iter_lines(self):
            for text in ("First", "Second", ""):
                state["reads"] += 1
                if after == "during_read" and state["reads"] == 1:
                    revoke()
                if provider == "ollama":
                    yield json.dumps({"message": {"content": text}, "done": not text})
                else:
                    yield ("data: " + json.dumps({"choices": [{"delta": {"content": text}}]})) if text else "data: [DONE]"

    class Client:
        def stream(self, *args, **kwargs):
            return Reply()

    monkeypatch.setattr(llm_rewrite, "_get_client", lambda: Client())

    def raw(*args, **kwargs):
        try:
            yield {"event": "metadata", "data": {"answer": "", "route": "production"}}
            provider_stream = llm_rewrite.chat_completion_stream([{"role": "user", "content": "Explain release"}], "rewrite")
            try:
                for text, usage in provider_stream:
                    if text:
                        yield {"event": "token", "token": text}
                    if usage:
                        yield {"event": "metadata", "data": {"answer": "FirstSecond"}}
            finally:
                provider_stream.close()
        finally:
            state["raw_closed"] += 1

    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", raw)
    with llm_rewrite.capture_usage() as records:
        stream = chat_answer.answer_payload_stream(
            "Explain release", history=[{"role": "user", "content": "Compression"}],
            session_id=session_id, plugin_session_id="plugin-fixture", correlation_id="cancel-work-fixture",
        )
        assert next(stream)["event"] == "metadata"
        if after == "token":
            assert next(stream) == {"event": "token", "token": "First"}
        if after != "during_read":
            revoke()
        if revocation in {"cancel", "replacement"}:
            discarded = next(stream)
            assert state["raw_closed"] == 1
            assert state["closed"] == int(after != "metadata")
            remaining = [discarded, *stream]
        else:
            remaining = list(stream)

    stale = revocation in {"cancel", "replacement"}
    expected_reads = (0 if after == "metadata" else 1) if stale else 3
    assert state == {"opened": int(expected_reads > 0), "reads": expected_reads,
                     "closed": int(expected_reads > 0), "raw_closed": 1}
    if stale:
        discarded, = remaining
        assert discarded["data"]["answer_delivery_discarded"] is True
        assert discarded["data"]["inference_aborted"] is False
        assert discarded["data"]["answer"] == ""
        assert discarded["data"]["session_id"] == session_id
        assert discarded["data"]["plugin_session_id"] == "plugin-fixture"
        assert discarded["data"]["correlation_id"] == "cancel-work-fixture"
        assert len(records) == int(expected_reads > 0)
        if records:
            assert records[0].status == "interrupted" and records[0].provider_done is False
    else:
        assert remaining[-1]["data"]["answer"] == "FirstSecond"
        assert len(records) == 1 and records[0].provider_done is True
