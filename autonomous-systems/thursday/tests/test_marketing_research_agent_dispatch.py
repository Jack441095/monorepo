"""Tests for the marketing/research agent chat-dispatch path
(thursday/registry/handlers.py, thursday/client.py) -- previously zero
coverage existed for this path at all (only the unrelated deterministic
ops/marketing_ops.py module was tested), which is presumably why a
two-layer bug (missing __main__ guard + argument-shape mismatch) went
unnoticed. Unit tests here mock api.marketing_agent/research_agent so no
real subprocess runs; a separate, opt-in integration test actually invokes
the fixed Audio_Too entry points if that sibling repo is present.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from thursday.registry import handlers


class _FakeApi:
    def __init__(self):
        self.marketing_agent = MagicMock(return_value="ok")
        self.research_agent = MagicMock(return_value="ok")


def test_post_request_defaults_platform_to_instagram():
    api = _FakeApi()
    handlers._handle_marketing_agent(api, "draft a social post about our new rates")
    api.marketing_agent.assert_called_once()
    args = api.marketing_agent.call_args[0]
    assert args[0] == "post"
    assert args[1] == "instagram"
    assert "rates" in args[2]


def test_post_request_detects_named_platform():
    api = _FakeApi()
    handlers._handle_marketing_agent(api, "write a post on twitter about the sale")
    args = api.marketing_agent.call_args[0]
    assert args[0] == "post"
    assert args[1] == "twitter"


def test_campaign_request_defaults_type_to_general():
    api = _FakeApi()
    handlers._handle_marketing_agent(api, "draft a campaign for the summer discount")
    args = api.marketing_agent.call_args[0]
    assert args[0] == "campaign"
    assert args[1] == "general"


def test_campaign_request_detects_type_keyword():
    api = _FakeApi()
    handlers._handle_marketing_agent(api, "run a marketing campaign for the product launch")
    args = api.marketing_agent.call_args[0]
    assert args[0] == "campaign"
    assert args[1] == "launch"


def test_outreach_request_extracts_lead_name():
    api = _FakeApi()
    handlers._handle_marketing_agent(api, "draft outreach to Jordan about the new pricing")
    args = api.marketing_agent.call_args[0]
    assert args[0] == "outreach"
    assert args[1] == "Jordan"


def test_outreach_request_defaults_lead_when_no_name_found():
    api = _FakeApi()
    handlers._handle_marketing_agent(api, "write a cold email")
    args = api.marketing_agent.call_args[0]
    assert args[0] == "outreach"
    assert args[1] == "the contact"


def test_new_lead_request_declines_honestly_instead_of_calling_nonexistent_function():
    api = _FakeApi()
    result = handlers._handle_marketing_agent(api, "add a new lead called Morgan")
    api.marketing_agent.assert_not_called()
    assert "can't" in result.lower() or "not" in result.lower()


def test_research_request_sends_topic_not_suggest():
    api = _FakeApi()
    handlers._handle_research_agent(api, "research mastering techniques")
    api.research_agent.assert_called_once()
    args = api.research_agent.call_args[0]
    assert args[0] == "topic"
    assert "mastering techniques" in args[1]


def test_research_request_with_no_topic_asks_for_one():
    api = _FakeApi()
    result = handlers._handle_research_agent(api, "research")
    api.research_agent.assert_not_called()
    assert "topic" in result.lower()


def test_client_marketing_agent_forwards_variadic_fields_to_run_agent(monkeypatch):
    from thursday import client

    captured = {}

    def fake_run_agent(agent_path, *args, timeout=60):
        captured["agent_path"] = agent_path
        captured["args"] = args
        return "ok"

    monkeypatch.setattr(client, "_run_agent", fake_run_agent)
    client.marketing_agent("post", "instagram", "new hours")
    assert captured["agent_path"] == "Marketing"
    assert captured["args"] == ("post", "instagram", "new hours")


def test_client_research_agent_forwards_variadic_fields_to_run_agent(monkeypatch):
    from thursday import client

    captured = {}

    def fake_run_agent(agent_path, *args, timeout=60):
        captured["agent_path"] = agent_path
        captured["args"] = args
        return "ok"

    monkeypatch.setattr(client, "_run_agent", fake_run_agent)
    client.research_agent("topic", "mastering")
    assert captured["agent_path"] == "Research"
    assert captured["args"] == ("topic", "mastering")


# ─── Opt-in real-subprocess regression test ────────────────────────────────
# This is the test that would have caught the original bug: it actually
# invokes the fixed Audio_Too entry points as a subprocess, the same way
# thursday/client.py::_run_agent does. Two separate gates, not one:
#
# 1. Skipped if the sibling Audio_Too repo isn't present (mirrors how other
#    cross-repo tests in this suite already guard on real coupling being
#    available).
# 2. Skipped unless THURSDAY_RUN_SLOW_AGENT_TESTS=1 is set, even when
#    Audio_Too IS present -- this invokes MarketingAgent's real
#    AutonomousCoderAgent-based LLM planning loop, whose latency genuinely
#    varies (found live: the "post" subcommand completed in ~10s, "leads"
#    exceeded a 60s timeout on a slower run) the same way every other LLM
#    call measured this session did. That variance makes it unsuitable to
#    run unconditionally as part of the default `pytest tests -q` suite --
#    it would make routine runs slow and occasionally flaky for reasons
#    having nothing to do with a regression. Run explicitly with:
#    THURSDAY_RUN_SLOW_AGENT_TESTS=1 python3 -m pytest tests/test_marketing_research_agent_dispatch.py -k subprocess

def _audio_too_marketing_main() -> Path | None:
    # thursday/ repo root is this file's grandparent's parent; Audio_Too is
    # a sibling of the autonomous-systems/ directory that contains thursday.
    repo_root = Path(__file__).resolve().parents[1]
    candidate = repo_root.parent.parent / "Audio_Too" / "business" / "agents" / "Marketing" / "main.py"
    return candidate if candidate.exists() else None


@pytest.mark.skipif(_audio_too_marketing_main() is None, reason="Audio_Too sibling repo not present")
@pytest.mark.skipif(
    os.environ.get("THURSDAY_RUN_SLOW_AGENT_TESTS") != "1",
    reason="Real LLM-backed agent call, variable latency -- opt in with THURSDAY_RUN_SLOW_AGENT_TESTS=1",
)
def test_marketing_main_subprocess_produces_real_output_not_silence():
    main_path = _audio_too_marketing_main()
    result = subprocess.run(
        [sys.executable, str(main_path), "post", "instagram", "new studio hours"],
        capture_output=True, text=True, timeout=120,
        cwd=str(main_path.parents[2]),  # Audio_Too/ so relative imports resolve
    )
    assert result.stdout.strip(), (
        f"Marketing/main.py produced no output at all -- the original silent "
        f"no-op bug (missing __main__ guard) may have regressed. stderr: {result.stderr[:500]}"
    )
