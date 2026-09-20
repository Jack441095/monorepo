"""Tests for audio_too/model_runtime.py's LLM provider abstractions.

Two real bugs found and fixed 2026-07-12 while live-testing Thursday's brain
(Stage O2) against a real local Ollama model:

1. Neither OllamaProvider nor RemoteProvider requested structured JSON
   output. brain.py (their only current caller) requires strict JSON --
   without response_format, a real local model reliably produced a
   correct, well-grounded natural-language answer that brain.py's parser
   then rejected outright because it wasn't valid JSON.
2. EnvGatedProvider's local-Ollama reachability check used a 1.0s timeout
   and silently swallowed the failure (`except Exception: pass`), so a
   momentarily-busy local Ollama (e.g. loading a large model) silently
   fell back to the remote provider -- which has no API key configured
   here and always 401s -- with zero visibility into why.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from nite_core.model_runtime import EnvGatedProvider, LLMResult, OllamaProvider, RemoteProvider


def _fake_response(json_body: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status.return_value = None
    return resp


def _chat_completion_body(content: str) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def test_ollama_provider_requests_json_object_format() -> None:
    provider = OllamaProvider()
    captured = {}

    def fake_post(url, json=None, headers=None):
        captured["payload"] = json
        return _fake_response(_chat_completion_body("{}"))

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = fake_post

    with patch("nite_core.model_runtime.httpx.Client", return_value=mock_client):
        provider.generate([{"role": "user", "content": "hi"}])

    assert captured["payload"]["response_format"] == {"type": "json_object"}


def test_remote_provider_requests_json_object_format() -> None:
    provider = RemoteProvider(api_key="fake-key")
    captured = {}

    def fake_post(url, json=None, headers=None):
        captured["payload"] = json
        return _fake_response(_chat_completion_body("{}"))

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = fake_post

    with patch("nite_core.model_runtime.httpx.Client", return_value=mock_client):
        provider.generate([{"role": "user", "content": "hi"}])

    assert captured["payload"]["response_format"] == {"type": "json_object"}


def test_ollama_provider_json_mode_false_omits_response_format() -> None:
    """2026-08-02: thursday/response_rewrite.py needs genuine free-form text
    (a natural-language reply), not JSON -- json_mode=False must drop
    response_format entirely rather than forcing json_object anyway."""
    provider = OllamaProvider()
    captured = {}

    def fake_post(url, json=None, headers=None):
        captured["payload"] = json
        return _fake_response(_chat_completion_body("A natural sentence."))

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = fake_post

    with patch("nite_core.model_runtime.httpx.Client", return_value=mock_client):
        provider.generate([{"role": "user", "content": "hi"}], json_mode=False)

    assert "response_format" not in captured["payload"]


def test_remote_provider_json_mode_false_omits_response_format() -> None:
    provider = RemoteProvider(api_key="fake-key")
    captured = {}

    def fake_post(url, json=None, headers=None):
        captured["payload"] = json
        return _fake_response(_chat_completion_body("A natural sentence."))

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = fake_post

    with patch("nite_core.model_runtime.httpx.Client", return_value=mock_client):
        provider.generate([{"role": "user", "content": "hi"}], json_mode=False)

    assert "response_format" not in captured["payload"]


def test_ollama_provider_response_schema_wins_over_json_mode_false() -> None:
    """A caller passing both response_schema and json_mode=False is
    contradictory -- response_schema (the stronger constraint) must win,
    since a caller that built a real schema clearly wants structured output."""
    provider = OllamaProvider()
    captured = {}
    schema = {"name": "test_schema", "schema": {"type": "object"}}

    def fake_post(url, json=None, headers=None):
        captured["payload"] = json
        return _fake_response(_chat_completion_body("{}"))

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = fake_post

    with patch("nite_core.model_runtime.httpx.Client", return_value=mock_client):
        provider.generate([{"role": "user", "content": "hi"}], response_schema=schema, json_mode=False)

    assert captured["payload"]["response_format"] == {"type": "json_schema", "json_schema": schema}


def test_env_gated_provider_threads_json_mode_to_local() -> None:
    local = MagicMock()
    local.generate.return_value = LLMResult(content="local", model="qwen2.5:1.5b", usage={})
    remote = MagicMock()
    provider = EnvGatedProvider(local, remote)

    with patch.dict("os.environ", {"AUDIO_TOO_LLM_PROVIDER": "ollama"}):
        provider.generate([{"role": "user", "content": "hi"}], json_mode=False)

    local.generate.assert_called_once_with(
        [{"role": "user", "content": "hi"}], timeout=10, response_schema=None, json_mode=False
    )


def test_env_gated_provider_threads_json_mode_to_remote() -> None:
    local = MagicMock()
    remote = MagicMock()
    remote.generate.return_value = LLMResult(content="remote", model="gpt-4o-mini", usage={})
    provider = EnvGatedProvider(local, remote)

    with patch.dict("os.environ", {"AUDIO_TOO_LLM_PROVIDER": "remote"}):
        provider.generate([{"role": "user", "content": "hi"}], json_mode=False)

    remote.generate.assert_called_once_with(
        [{"role": "user", "content": "hi"}], timeout=10, response_schema=None, json_mode=False
    )


def test_env_gated_provider_uses_local_when_ollama_reachable() -> None:
    local = MagicMock()
    local.generate.return_value = LLMResult(content="local", model="qwen2.5:1.5b", usage={})
    remote = MagicMock()
    provider = EnvGatedProvider(local, remote)

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = _fake_response({"models": []})

    with patch("nite_core.model_runtime.httpx.Client", return_value=mock_client), \
         patch.dict("os.environ", {}, clear=False):
        import os
        os.environ.pop("AUDIO_TOO_LLM_PROVIDER", None)
        result = provider.generate([{"role": "user", "content": "hi"}])

    assert result.content == "local"
    local.generate.assert_called_once()
    remote.generate.assert_not_called()


def test_env_gated_provider_falls_back_to_remote_and_logs_when_unreachable(caplog) -> None:
    """Regression: the fallback must be visible (logged), not a silent pass."""
    import logging
    local = MagicMock()
    remote = MagicMock()
    remote.generate.return_value = LLMResult(content="remote", model="gpt-4o-mini", usage={})
    provider = EnvGatedProvider(local, remote)

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.side_effect = TimeoutError("simulated timeout")

    caplog.set_level(logging.WARNING, logger="nite_core.model_runtime")
    with patch("nite_core.model_runtime.httpx.Client", return_value=mock_client), \
         patch.dict("os.environ", {}, clear=False):
        import os
        os.environ.pop("AUDIO_TOO_LLM_PROVIDER", None)
        result = provider.generate([{"role": "user", "content": "hi"}])

    assert result.content == "remote"
    local.generate.assert_not_called()
    assert any("reachability check failed" in r.message for r in caplog.records)


def test_env_gated_provider_respects_explicit_provider_override() -> None:
    local = MagicMock()
    remote = MagicMock()
    remote.generate.return_value = LLMResult(content="remote", model="gpt-4o-mini", usage={})
    provider = EnvGatedProvider(local, remote)

    with patch.dict("os.environ", {"AUDIO_TOO_LLM_PROVIDER": "remote"}):
        result = provider.generate([{"role": "user", "content": "hi"}])

    assert result.content == "remote"
    local.generate.assert_not_called()
