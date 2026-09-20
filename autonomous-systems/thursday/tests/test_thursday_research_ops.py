"""Tests for thursday/ops/research_ops.py (founder request, 2026-09-02).

No real network calls -- Tavily's HTTP call is mocked at the
urllib.request.urlopen boundary so these tests are deterministic and
offline, same discipline as the rest of this suite. What's under test is
this module's own logic: honest degradation with no API key, parsing,
rendering, and the target-audience default -- not Tavily's API itself.
"""

from __future__ import annotations

import json
import urllib.error

import thursday.ops.research_ops as ro


def test_web_search_reports_evidence_missing_without_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    result = ro.web_search("music production forums")
    assert result["ok"] is False
    assert result["results"] == []
    assert "TAVILY_API_KEY" in result["error"]


def test_web_search_rejects_empty_query(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    result = ro.web_search("   ")
    assert result["ok"] is False
    assert "Empty search query" in result["error"]


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_web_search_returns_real_results_shape(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    fake_payload = {
        "results": [
            {"title": "r/university subreddit", "url": "https://reddit.com/r/university", "content": "A community for university students."},
        ]
    }
    monkeypatch.setattr(ro.urllib.request, "urlopen", lambda req, timeout: _FakeResponse(fake_payload))
    result = ro.web_search("student communities")
    assert result["ok"] is True
    assert result["results"] == [
        {"title": "r/university subreddit", "url": "https://reddit.com/r/university", "snippet": "A community for university students."},
    ]


def test_web_search_handles_http_error(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")

    def _raise(req, timeout):
        raise urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(ro.urllib.request, "urlopen", _raise)
    result = ro.web_search("test")
    assert result["ok"] is False
    assert "401" in result["error"]


def test_render_search_results_never_fabricates_on_error():
    out = ro.render_search_results("test query", {"ok": False, "results": [], "error": "boom"})
    assert "boom" in out
    assert "test query" in out


def test_render_search_results_lists_real_results():
    result = {
        "ok": True,
        "results": [{"title": "Example", "url": "https://example.com", "snippet": "A snippet."}],
        "error": None,
    }
    out = ro.render_search_results("example query", result)
    assert "Example" in out
    assert "https://example.com" in out
    assert "A snippet." in out
    assert "not verified leads" in out


def test_find_potential_customers_uses_default_target_audience(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    out = ro.find_potential_customers("")
    assert ro._DEFAULT_TARGET_AUDIENCE_QUERY in out


def test_find_potential_customers_uses_given_query(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    out = ro.find_potential_customers("music production forums UK")
    assert "music production forums UK" in out
    assert ro._DEFAULT_TARGET_AUDIENCE_QUERY not in out


def test_parse_find_customers_command_matches_prefixes():
    assert ro.parse_find_customers_command("find customers: UK students") == "UK students"
    assert ro.parse_find_customers_command("look for potential customers") == ""
    assert ro.parse_find_customers_command("find customers") == ""
    assert ro.parse_find_customers_command("totally unrelated text") is None


def test_parse_web_search_command_matches_prefixes():
    assert ro.parse_web_search_command("web search: mixing engineers") == "mixing engineers"
    assert ro.parse_web_search_command("search the web for competitor pricing") == "competitor pricing"
    assert ro.parse_web_search_command("unrelated text") is None
