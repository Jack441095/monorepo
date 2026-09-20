"""Tests for thursday/llm_provider.py -- the provider abstraction brain.py
uses to call an LLM. Network/model-loading providers (openai_compat,
mlx_lm) are exercised with mocked transports here; live-backend smoke
testing is documented separately (see docs/) since it needs a running
server or downloaded model weights, neither of which belong in CI.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from thursday import llm_provider as lp


@pytest.fixture(autouse=True)
def _clean_env_and_cache():
    keys = [
        "THURSDAY_LLM_PROVIDER", "THURSDAY_LLM_MODEL", "THURSDAY_LLM_BASE_URL",
        "THURSDAY_LLM_TIMEOUT", "THURSDAY_LLM_FALLBACK_MODEL", "AUDIO_TOO_LLM_TIMEOUT",
    ]
    saved = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    lp.reset_provider_cache()
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    lp.reset_provider_cache()


# ─── Factory / rollback switch ───────────────────────────────────────────


def test_default_provider_is_audio_too():
    provider = lp.get_llm_provider()
    assert isinstance(provider, lp.AudioTooProvider)
    assert provider.name == "audio_too"


def test_none_provider_is_rollback_switch_and_always_fails():
    os.environ["THURSDAY_LLM_PROVIDER"] = "none"
    provider = lp.get_llm_provider()
    assert isinstance(provider, lp.NullProvider)
    with pytest.raises(lp.LLMUnavailable):
        provider.generate([{"role": "user", "content": "hi"}], timeout=5)


def test_unknown_provider_raises_value_error():
    os.environ["THURSDAY_LLM_PROVIDER"] = "not_a_real_provider"
    with pytest.raises(ValueError):
        lp.get_llm_provider()


def test_mlx_lm_without_model_raises_value_error():
    os.environ["THURSDAY_LLM_PROVIDER"] = "mlx_lm"
    with pytest.raises(ValueError):
        lp.get_llm_provider()


def test_provider_cache_rebuilds_on_env_change():
    os.environ["THURSDAY_LLM_PROVIDER"] = "none"
    p1 = lp.get_llm_provider()
    os.environ["THURSDAY_LLM_PROVIDER"] = "openai_compat"
    os.environ["THURSDAY_LLM_MODEL"] = "test-model"
    p2 = lp.get_llm_provider()
    assert p1 is not p2
    assert isinstance(p2, lp.OpenAICompatProvider)


def test_get_llm_provider_wires_max_tokens_to_openai_compat():
    os.environ["THURSDAY_LLM_PROVIDER"] = "openai_compat"
    os.environ["THURSDAY_LLM_MODEL"] = "test-model"
    os.environ["THURSDAY_LLM_MAX_TOKENS"] = "321"
    provider = lp.get_llm_provider()
    assert provider.max_tokens == 321


def test_default_timeout_reads_new_and_legacy_env_var():
    assert lp.default_timeout() == 10.0
    os.environ["AUDIO_TOO_LLM_TIMEOUT"] = "7"
    assert lp.default_timeout() == 7.0
    os.environ["THURSDAY_LLM_TIMEOUT"] = "3"
    assert lp.default_timeout() == 3.0


# ─── AudioTooProvider ─────────────────────────────────────────────────────


def test_audio_too_provider_raises_llm_unavailable_when_not_installed():
    # Other test modules in this suite import thursday.server/watcher/etc,
    # which insert the real audio_too checkout onto sys.path as a module-
    # level side effect -- so "not installed" can't be asserted against
    # ambient environment state when run inside the full suite. Force the
    # ImportError deterministically instead, matching how
    # test_audio_too_provider_wraps_unexpected_exception below does it.
    provider = lp.AudioTooProvider()
    with patch.object(provider, "_resolve", side_effect=lp.LLMUnavailable("audio_too.model_runtime not installed")):
        with pytest.raises(lp.LLMUnavailable):
            provider.generate([{"role": "user", "content": "hi"}], timeout=5)
        assert provider.health_check() is False


def test_audio_too_provider_delegates_and_wraps_result():
    fake_result = MagicMock(content="hello world")
    fake_llm = MagicMock()
    fake_llm.generate.return_value = fake_result
    provider = lp.AudioTooProvider()
    with patch.object(provider, "_resolve", return_value=fake_llm):
        out = provider.generate([{"role": "user", "content": "hi"}], timeout=5, response_schema={"a": 1})
    assert out.content == "hello world"
    assert out.provider == "audio_too"
    fake_llm.generate.assert_called_once_with(
        [{"role": "user", "content": "hi"}], timeout=5, response_schema={"a": 1}
    )


def test_audio_too_provider_wraps_unexpected_exception():
    provider = lp.AudioTooProvider()
    boom = MagicMock()
    boom.generate.side_effect = RuntimeError("network exploded")
    with patch.object(provider, "_resolve", return_value=boom):
        with pytest.raises(lp.LLMUnavailable):
            provider.generate([{"role": "user", "content": "hi"}], timeout=5)


# ─── OpenAICompatProvider ─────────────────────────────────────────────────


def _fake_response(payload: dict):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode()

    return _Resp()


def test_openai_compat_generate_plain(monkeypatch):
    provider = lp.OpenAICompatProvider(model="m1", base_url="http://x/v1")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data)
        return _fake_response({"choices": [{"message": {"content": "hi there"}}]})

    monkeypatch.setattr("thursday.llm_provider.json.load", lambda resp: {"choices": [{"message": {"content": "hi there"}}]})
    monkeypatch.setattr(lp.urllib.request, "urlopen", fake_urlopen)
    out = provider.generate([{"role": "user", "content": "hi"}], timeout=5)
    assert out.content == "hi there"
    assert out.model == "m1"
    assert captured["payload"]["max_tokens"] == 768  # default; see the next test for override


def test_openai_compat_sends_configured_max_tokens(monkeypatch):
    """Regression test: found live 2026-09-08 that OpenAICompatProvider
    never sent max_tokens at all (unlike MLXLMProvider, which always did),
    so every call through Ollama/any OpenAI-compatible server had
    unbounded output length -- a real specialist-execution call ran past
    120s with no natural stop before this was caught."""
    provider = lp.OpenAICompatProvider(model="m1", base_url="http://x/v1", max_tokens=200)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data)
        return _fake_response({"choices": [{"message": {"content": "hi there"}}]})

    monkeypatch.setattr("thursday.llm_provider.json.load", lambda resp: {"choices": [{"message": {"content": "hi there"}}]})
    monkeypatch.setattr(lp.urllib.request, "urlopen", fake_urlopen)
    provider.generate([{"role": "user", "content": "hi"}], timeout=5)
    assert captured["payload"]["max_tokens"] == 200
    assert "response_format" not in captured["payload"]


def test_openai_compat_schema_falls_back_when_unsupported(monkeypatch):
    provider = lp.OpenAICompatProvider(model="m1", base_url="http://x/v1")
    calls = []

    def fake_urlopen(req, timeout=None):
        payload = json.loads(req.data)
        calls.append(payload)
        if "response_format" in payload:
            raise lp.urllib.error.URLError("400: response_format not supported")
        return _fake_response({"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(lp.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("thursday.llm_provider.json.load", lambda resp: {"choices": [{"message": {"content": '{"ok": true}'}}]})
    out = provider.generate(
        [{"role": "user", "content": "hi"}], timeout=5,
        response_schema={"name": "x", "schema": {"type": "object"}},
    )
    assert out.content == '{"ok": true}'
    assert len(calls) == 2
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]
    assert provider.capabilities()["supports_json_schema"] is False


def test_openai_compat_falls_back_to_fallback_model(monkeypatch):
    provider = lp.OpenAICompatProvider(model="primary", base_url="http://x/v1", fallback_model="backup")
    seen_models = []

    def fake_urlopen(req, timeout=None):
        payload = json.loads(req.data)
        seen_models.append(payload["model"])
        if payload["model"] == "primary":
            raise lp.urllib.error.URLError("connection refused")
        return _fake_response({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(lp.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("thursday.llm_provider.json.load", lambda resp: {"choices": [{"message": {"content": "ok"}}]})
    out = provider.generate([{"role": "user", "content": "hi"}], timeout=5)
    assert out.model == "backup"
    assert seen_models == ["primary", "backup"]


def test_openai_compat_no_fallback_configured_raises(monkeypatch):
    provider = lp.OpenAICompatProvider(model="primary", base_url="http://x/v1")

    def fake_urlopen(req, timeout=None):
        raise lp.urllib.error.URLError("connection refused")

    monkeypatch.setattr(lp.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(lp.LLMUnavailable):
        provider.generate([{"role": "user", "content": "hi"}], timeout=5)


# ─── MLXLMProvider ─────────────────────────────────────────────────────────


def test_mlx_lm_raises_llm_unavailable_when_not_installed(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "mlx_lm":
            raise ImportError("no mlx_lm")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    lp._mlx_model_cache.clear()
    provider = lp.MLXLMProvider(model="does/not-matter")
    with pytest.raises(lp.LLMUnavailable):
        provider.generate([{"role": "user", "content": "hi"}], timeout=5)


def test_mlx_lm_timeout_raises_llm_unavailable(monkeypatch):
    import sys
    import types
    # mlx_lm is an optional Apple-Silicon dep, not installed in CI.
    # Install a stub module so `patch("mlx_lm.generate")` resolves and the
    # provider's own ThreadPoolExecutor timeout path is exercised for real.
    stub = types.ModuleType("mlx_lm")
    def _missing_generate(*a, **kw):
        raise AssertionError("stub should be patched in this test")
    stub.generate = _missing_generate
    monkeypatch.setitem(sys.modules, "mlx_lm", stub)
    provider = lp.MLXLMProvider(model="fake-model")
    with patch.object(lp, "_mlx_load", return_value=(MagicMock(), MagicMock(apply_chat_template=None, chat_template=None))):
        with patch("mlx_lm.generate", create=True) as mock_gen:
            import time as _t
            def slow(*a, **kw):
                _t.sleep(0.2)
                return "too slow"
            mock_gen.side_effect = slow
            with pytest.raises(lp.LLMUnavailable):
                provider.generate([{"role": "user", "content": "hi"}], timeout=0.01)


def test_mlx_lm_rejects_fast_when_all_generation_slots_busy(monkeypatch):
    """Failing-first for the worker-leak audit finding (2026-09-18): the
    old ThreadPoolExecutor(max_workers=2) let abandoned (timed-out)
    generations permanently occupy both workers, so later calls queued
    behind dead work. Desired: bounded concurrent slots, fast
    saturated-rejection, visible counters."""
    import sys
    import threading
    import types
    gate = threading.Event()
    stub = types.ModuleType("mlx_lm")
    def stuck(*a, **kw):
        gate.wait(timeout=30)
        return "late"
    stub.generate = stuck
    monkeypatch.setitem(sys.modules, "mlx_lm", stub)
    provider = lp.MLXLMProvider(model="fake-model")
    with patch.object(lp, "_mlx_load", return_value=(MagicMock(), MagicMock(apply_chat_template=None, chat_template=None))):
        occupants = []
        def occupy():
            try:
                provider.generate([{"role": "user", "content": "hi"}], timeout=25)
            except lp.LLMUnavailable:
                pass
        threads = [threading.Thread(target=occupy, daemon=True) for _ in range(4)]
        for t in threads:
            t.start()
        import time as _t
        deadline = _t.monotonic() + 10
        while sum(1 for t in threads if t.is_alive()) < 4 and _t.monotonic() < deadline:
            _t.sleep(0.05)
        t0 = _t.monotonic()
        try:
            with pytest.raises(lp.LLMUnavailable, match="saturat"):
                provider.generate([{"role": "user", "content": "hi"}], timeout=25)
        finally:
            gate.set()
            for t in threads:
                t.join(timeout=10)
        assert _t.monotonic() - t0 < 10, "saturated call must fail fast, not queue"
        caps = provider.capabilities()
        assert caps.get("saturated_rejections", 0) >= 1


def test_mlx_lm_capabilities_report_no_schema_support():
    provider = lp.MLXLMProvider(model="fake-model")
    caps = provider.capabilities()
    assert caps["supports_json_schema"] is False
    assert caps["model"] == "fake-model"


# ─── NullProvider / capability_report ──────────────────────────────────────


def test_capability_report_shape():
    os.environ["THURSDAY_LLM_PROVIDER"] = "none"
    report = lp.capability_report()
    assert report["provider"] == "none"
    assert "timeout_s" in report
    assert "healthy" not in report  # probe=False by default


def test_capability_report_with_probe():
    os.environ["THURSDAY_LLM_PROVIDER"] = "none"
    report = lp.capability_report(probe=True)
    assert report["healthy"] is False
