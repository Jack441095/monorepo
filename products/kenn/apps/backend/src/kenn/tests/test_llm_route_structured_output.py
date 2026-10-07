"""The model route classifier must not guess a route out of free text.

llm_route_query used to read the first route word anywhere in the model's reply, so
"Not ableton, this is production." came back as "ableton". On native Ollama the reply
is now constrained to {"route": <one of VALID_ROUTE_WORDS>}; on the OpenAI-compatible
route, which has no such constraint here, a reply naming more than one route is refused.
"""

from __future__ import annotations

import json

import httpx
import pytest

from kenn.llm import llm_rewrite

QWEN = {
    "KENN_LLM_ENABLED": "1",
    "KENN_LLM_PROVIDER": "ollama",
    "KENN_LLM_BASE_URL": "http://127.0.0.1:11434/v1",
    "KENN_LLM_MODEL": "kenn-brain-qwen3-8b",
}
OPENAI = {
    "KENN_LLM_ENABLED": "1",
    "KENN_LLM_PROVIDER": "openai",
    "KENN_LLM_API_KEY": "test-key",
    "KENN_LLM_BASE_URL": "https://api.openai.com/v1",
    "KENN_LLM_MODEL": "gpt-4o-mini",
}


def _reply(monkeypatch, env: dict, body: dict) -> dict:
    """Stub the transport with one reply; return the dict the request is recorded into."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    posted: dict = {}

    class _Client:
        def post(self, url, json=None, headers=None, timeout=None):
            posted["url"] = url
            posted["json"] = json
            return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm_rewrite, "_get_client", lambda: _Client())
    return posted


def _native(content: str) -> dict:
    return {"message": {"content": content}}


def _openai(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def test_native_request_constrains_the_reply_to_the_route_enum(monkeypatch) -> None:
    posted = _reply(monkeypatch, QWEN, _native('{"route": "ableton"}'))

    assert llm_rewrite.llm_route_query("how do I freeze a track") == "ableton"

    schema = posted["json"]["format"]
    assert schema["properties"]["route"]["enum"] == list(llm_rewrite.VALID_ROUTE_WORDS)
    assert schema["required"] == ["route"]
    assert schema["additionalProperties"] is False
    # The prompt must ask for the same JSON shape the decoder enforces.
    assert '"route"' in posted["json"]["messages"][0]["content"]


@pytest.mark.parametrize("route", llm_rewrite.VALID_ROUTE_WORDS)
def test_native_json_reply_returns_each_route(monkeypatch, route) -> None:
    _reply(monkeypatch, QWEN, _native(json.dumps({"route": route})))

    assert llm_rewrite.llm_route_query("some unmatched question") == route


@pytest.mark.parametrize(
    "content",
    [
        "Not ableton, this is production.",  # free text: the old parser said "ableton"
        "production",  # bare word is not the requested JSON
        '{"route": "mixing"}',  # outside the enum
        '{"category": "production"}',  # wrong key
        '["production"]',
        "",
    ],
)
def test_native_reply_outside_the_schema_falls_through_and_says_why(monkeypatch, capsys, content) -> None:
    _reply(monkeypatch, QWEN, _native(content))

    assert llm_rewrite.llm_route_query("some unmatched question") is None
    out = capsys.readouterr().out
    assert "llm_route_query" in out and "keyword routing" in out


def test_openai_route_refuses_a_reply_naming_two_routes(monkeypatch, capsys) -> None:
    posted = _reply(monkeypatch, OPENAI, _openai("Not ableton, this is production."))

    assert llm_rewrite.llm_route_query("some unmatched question") is None
    assert "format" not in posted["json"]
    assert "keyword routing" in capsys.readouterr().out


@pytest.mark.parametrize("content", ["production", "Production.", "production production"])
def test_openai_route_still_accepts_one_route_word(monkeypatch, content) -> None:
    _reply(monkeypatch, OPENAI, _openai(content))

    assert llm_rewrite.llm_route_query("some unmatched question") == "production"
