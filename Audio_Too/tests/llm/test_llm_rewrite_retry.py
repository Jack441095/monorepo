"""_chat_completion() retries once on a transient httpx.ConnectError instead
of dropping straight to the unpolished template answer (P4 fix, 2026-07-13).
Ollama's ~5-minute idle cold-reload is a documented recurring cause of
exactly this class of one-off connection blip (see llm_rewrite.py comments).

2026-08-02: this file was briefly overwritten (uncommitted, by a parallel
agent) with tests for an unrelated enhance()-level self-critique retry loop.
That loop was reverted the same day (it was producing over-templated,
self-referential-feeling answers -- live-reported and confirmed) -- restored
here rather than just deleted, since the _chat_completion()-level connection
retry this file actually tests is still live and was left with zero
coverage in the meantime."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
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


class _FlakyOnceClient:
    """Raises ConnectError on the first call, succeeds on the second."""

    def __init__(self, content: str) -> None:
        self.calls = 0
        self._content = content

    def post(self, *args, **kwargs) -> _FakeResponse:
        self.calls += 1
        if self.calls == 1:
            raise httpx.ConnectError("connection refused", request=None)
        return _FakeResponse(self._content)


class _AlwaysConnectErrorClient:
    def __init__(self) -> None:
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        raise httpx.ConnectError("connection refused", request=None)


class _AlwaysTimeoutClient:
    def __init__(self) -> None:
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        raise httpx.TimeoutException("timed out")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    lr.clear_answer_cache()
    monkeypatch.setenv("KENN_LLM_CACHE", "0")
    monkeypatch.setattr(lr, "config", lambda task="rewrite": dict(_CFG))
    monkeypatch.setattr(lr.time, "sleep", lambda *_: None)  # skip the real 1s pause
    yield
    lr.clear_answer_cache()


def _msgs(q: str) -> list[dict]:
    return [{"role": "user", "content": q}]


def test_retries_once_on_connect_error_and_succeeds(monkeypatch):
    fake = _FlakyOnceClient("recovered answer")
    monkeypatch.setattr(lr, "_get_client", lambda: fake)

    content, _usage = lr._chat_completion(_msgs("question"), system_prompt="sys")

    assert content == "recovered answer"
    assert fake.calls == 2


def test_gives_up_after_one_retry_on_persistent_connect_error(monkeypatch):
    fake = _AlwaysConnectErrorClient()
    monkeypatch.setattr(lr, "_get_client", lambda: fake)

    with pytest.raises(RuntimeError, match="LLM connection failed after retry"):
        lr._chat_completion(_msgs("question"), system_prompt="sys")

    assert fake.calls == 2  # original attempt + exactly one retry, not more


def test_timeout_is_not_retried(monkeypatch):
    fake = _AlwaysTimeoutClient()
    monkeypatch.setattr(lr, "_get_client", lambda: fake)

    with pytest.raises(TimeoutError):
        lr._chat_completion(_msgs("question"), system_prompt="sys")

    assert fake.calls == 1  # a timeout already used the full configured budget


class _CapturingClient:
    """Records the kwargs each call site actually sent to httpx, so the
    real bug (cfg["timeout"] never reaching the request -- the shared
    client's fixed 90s default silently governed everything regardless
    of AUDIO_TOO_LLM_TIMEOUT) can't regress unnoticed. Found live
    2026-08-10: even a slow local Ollama model made questions wait up to
    90s before the graceful template fallback kicked in, since the
    config value only ever reached a cosmetic error-message string, not
    the actual request."""

    def __init__(self, content: str = "answer") -> None:
        self.post_kwargs: dict | None = None
        self._content = content

    def post(self, *args, **kwargs) -> _FakeResponse:
        self.post_kwargs = kwargs
        return _FakeResponse(self._content)


def test_chat_completion_passes_the_configured_timeout_to_the_request(monkeypatch):
    fake = _CapturingClient()
    monkeypatch.setattr(lr, "_get_client", lambda: fake)

    lr._chat_completion(_msgs("question"), system_prompt="sys")

    assert fake.post_kwargs is not None
    timeout = fake.post_kwargs.get("timeout")
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == _CFG["timeout"]


def test_route_query_passes_the_configured_timeout_to_the_request(monkeypatch):
    fake = _CapturingClient('{"route": "production"}')
    monkeypatch.setattr(lr, "_get_client", lambda: fake)
    monkeypatch.setattr(lr, "is_enabled", lambda task="rewrite": True)

    lr.llm_route_query("how do I eq a kick")

    assert fake.post_kwargs is not None
    timeout = fake.post_kwargs.get("timeout")
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == _CFG["timeout"]
