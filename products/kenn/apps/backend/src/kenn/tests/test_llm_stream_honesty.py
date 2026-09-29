"""Mid-stream LLM failures must surface, not end the stream quietly.

Regression (29 Sept 2026 honesty audit): chat_completion_stream and
enhance_stream caught every unexpected error, printed a warning, and
returned -- so a connection that died halfway through an answer looked
identical to a finished answer, and chat_answer validated the truncated
candidate as if the model had stopped writing on its own.
"""

import pytest

from kenn.llm import llm_rewrite


class _CutShortStream:
    """Stands in for the httpx streaming response: one token, then the wire dies."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        yield 'data: {"choices":[{"delta":{"content":"Half an answer"}}]}'
        raise ConnectionResetError("peer closed the connection mid-stream")


class _FakeClient:
    def stream(self, method, url, **kwargs):
        return _CutShortStream()


class _CleanStream(_CutShortStream):
    """Same single token, but terminates honestly with the provider's DONE marker."""

    def iter_lines(self):
        yield 'data: {"choices":[{"delta":{"content":"A full answer"}}]}'
        yield "data: [DONE]"


class _CleanClient:
    def stream(self, method, url, **kwargs):
        return _CleanStream()


def _offline_stream_env(monkeypatch, client):
    # Pin the call to the HTTP path with an empty cache so the test exercises
    # exactly the failure handling under audit, not MLX or cached answers.
    monkeypatch.setattr(llm_rewrite, "mlx_selected", lambda task: False)
    monkeypatch.setattr(llm_rewrite, "_cache_get", lambda key: None)
    monkeypatch.setattr(llm_rewrite, "_get_client", lambda: client)


MESSAGES = [
    {"role": "system", "content": "answer"},
    {"role": "user", "content": "How do I de-ess?"},
]


def test_midstream_failure_raises_instead_of_ending_quietly(monkeypatch) -> None:
    _offline_stream_env(monkeypatch, _FakeClient())
    tokens: list[str] = []
    with pytest.raises(RuntimeError, match="cut short"):
        for token, _usage in llm_rewrite.chat_completion_stream(MESSAGES, "rewrite"):
            tokens.append(token)
    # The partial token still reaches the caller (streaming can't take it back),
    # but the stream must not look like a normal finish.
    assert tokens == ["Half an answer"]


def test_clean_stream_still_ends_with_usage_signal(monkeypatch) -> None:
    _offline_stream_env(monkeypatch, _CleanClient())
    chunks = list(llm_rewrite.chat_completion_stream(MESSAGES, "rewrite"))
    assert chunks[0][0] == "A full answer"
    assert chunks[-1][0] == "" and chunks[-1][1] is not None


def test_enhance_stream_propagates_a_cut_short(monkeypatch) -> None:
    # The prompt builder is not under test here; keep the fixture minimal so the
    # test isolates the propagate-vs-swallow contract of the event loop.
    monkeypatch.setattr(llm_rewrite, "is_enabled", lambda task="rewrite": True)
    monkeypatch.setattr(llm_rewrite, "_build_synthesis_messages", lambda *a, **k: [])

    def fake_stream(messages, task, **kwargs):
        yield "first half ", None
        raise ConnectionResetError("gone")

    monkeypatch.setattr(llm_rewrite, "chat_completion_stream", fake_stream)
    with pytest.raises(ConnectionResetError):
        list(
            llm_rewrite.enhance_stream(
                "q", "template", [], [], "", lambda chunk: "", lambda history: history
            )
        )