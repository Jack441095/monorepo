"""Tests for thursday/agent_briefing.py -- composing a real-evidence
handoff briefing for another AI agent, per the spec's "Can you brief
Codex/Gemini/another agent on this?" command. Every figure in the
briefing must be a pass-through of an already-tested module's own
function; these tests confirm the topic-based section filtering and that
the evidence-discipline instruction is always present.
"""

from __future__ import annotations

import thursday.ops.agent_briefing as ab
import thursday.ops.task_ledger as tl
import thursday.ops.marketing_ops as mo
import thursday.ops.advertising_ops as ao
import thursday.ops.funding_ops as fo
import pytest


@pytest.fixture(autouse=True)
def _isolated_stores(monkeypatch, tmp_path):
    # compose_agent_briefing() lazily calls into marketing_ops/
    # advertising_ops/funding_ops for their topic sections -- isolate all
    # of them, not just task_ledger, so these tests don't read whatever
    # real state happens to be on disk.
    monkeypatch.setattr(tl, "TASK_LEDGER_FILE", tmp_path / "task_ledger.json")
    monkeypatch.setattr(mo, "MARKETING_PLANS_FILE", tmp_path / "marketing_plans.json")
    monkeypatch.setattr(ao, "CAMPAIGN_PLANS_FILE", tmp_path / "ad_campaign_plans.json")
    monkeypatch.setattr(fo, "_resolve_list_records", lambda: None)


# ── parse_brief_agent_command ────────────────────────────────────────────


def test_parse_bare_command_no_topic():
    assert ab.parse_brief_agent_command("brief another agent") == ""


def test_parse_with_topic():
    assert ab.parse_brief_agent_command("brief another agent on funding") == "funding"


def test_parse_codex_variant():
    assert ab.parse_brief_agent_command("brief codex on the beta launch") == "the beta launch"


def test_parse_gemini_bare():
    assert ab.parse_brief_agent_command("brief gemini") == ""


def test_parse_longest_prefix_wins_over_topic_less_shorter_one():
    # "brief another agent" is a prefix of "brief another agent on X" --
    # must match the longer, topic-bearing form, not truncate the topic.
    result = ab.parse_brief_agent_command("brief another agent on X")
    assert result == "X"


def test_parse_returns_none_for_unrelated_text():
    assert ab.parse_brief_agent_command("what's the weather") is None
    assert ab.parse_brief_agent_command("active tasks") is None


def test_parse_never_raises_on_empty_topic():
    # Unlike task creation, a topic-less briefing is a legitimate request,
    # not an error -- confirmed by not raising here.
    result = ab.parse_brief_agent_command("brief an agent on")
    assert result == ""


# ── topic-based section filtering ────────────────────────────────────────


def test_no_topic_includes_all_sections():
    data = ab.compose_agent_briefing("")
    assert set(data["sections_included"]) == {"tasks", "beta", "funding", "marketing"}


def test_beta_topic_includes_only_tasks_and_beta():
    data = ab.compose_agent_briefing("the beta launch")
    assert set(data["sections_included"]) == {"tasks", "beta"}
    assert "beta_readiness_report" in data
    assert "funding_readiness_report" not in data


def test_funding_topic_includes_only_tasks_and_funding():
    data = ab.compose_agent_briefing("funding")
    assert set(data["sections_included"]) == {"tasks", "funding"}
    assert "funding_readiness_report" in data
    assert "beta_readiness_report" not in data


def test_marketing_topic_includes_marketing_and_advertising_reports():
    data = ab.compose_agent_briefing("marketing")
    assert "marketing_readiness_report" in data
    assert "ad_readiness_report" in data


# ── render / evidence discipline ─────────────────────────────────────────


def test_render_always_includes_evidence_discipline():
    out = ab.brief_agent("")
    assert "EVIDENCE DISCIPLINE" in out
    assert "Do not extend, round up, or fill gaps" in out


def test_render_reflects_real_task_ledger_state():
    t = tl.create_task("engineering", "Fix crash.", priority="urgent")
    tl.update_task(t.task_id, status="active")
    out = ab.brief_agent("")
    assert t.task_id in out
    assert "Fix crash." in out


def test_render_honest_when_no_tasks():
    out = ab.brief_agent("")
    assert "Active: none." in out
    assert "Blocked: none." in out


def test_render_includes_topic_and_timestamp():
    out = ab.brief_agent("funding")
    assert "Topic: funding" in out
    assert "Generated:" in out
