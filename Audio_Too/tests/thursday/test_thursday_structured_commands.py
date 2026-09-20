"""Tests for thursday/structured_commands.py -- the pre-scoring dispatcher
that prevents a structured command's free-text tail from being hijacked
by thursday.registry's fuzzy trigger scoring (found live 2026-09-02:
"create task marketing: draft a post" routing to the Marketing Agent
instead of creating a task; see the module's own docstring).
"""

from __future__ import annotations

import pytest

import thursday.ops.task_ledger as tl
import thursday.ops.marketing_ops as mo
import thursday.ops.advertising_ops as ao
from thursday.ops.structured_commands import try_dispatch


@pytest.fixture(autouse=True)
def _isolated_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(tl, "TASK_LEDGER_FILE", tmp_path / "task_ledger.json")
    monkeypatch.setattr(mo, "MARKETING_PLANS_FILE", tmp_path / "marketing_plans.json")
    monkeypatch.setattr(ao, "CAMPAIGN_PLANS_FILE", tmp_path / "ad_campaign_plans.json")


def test_none_for_unrelated_text():
    assert try_dispatch("what's the weather") is None
    assert try_dispatch("how's business") is None


def test_dispatches_task_creation():
    result = try_dispatch("create task marketing: draft this week's post")
    assert result is not None
    name, response = result
    assert name == "create_task"
    assert "Created task-marketing-1" in response


def test_dispatches_marketing_plan_even_with_colliding_words():
    # The exact text that hijacked routing before this dispatcher existed:
    # contains "marketing" and "draft...post", both real marketing_agent
    # triggers, embedded in the objective this command is supposed to own.
    result = try_dispatch(
        "create task marketing: draft this week's Submit post"
    )
    assert result is not None
    name, response = result
    assert name == "create_task"
    assert "Marketing Agent" not in response
    assert "no output" not in response


def test_dispatches_create_marketing_plan():
    result = try_dispatch("create marketing plan: Prepare launch content")
    assert result is not None
    name, response = result
    assert name == "create_marketing_plan"
    assert "MARKETING PLAN" in response


def test_dispatches_create_campaign_plan():
    result = try_dispatch("create campaign plan: Submit | platform: google")
    assert result is not None
    name, response = result
    assert name == "create_campaign_plan"
    assert "AD CAMPAIGN PLAN" in response


def test_matched_but_invalid_command_still_handled_not_none():
    # Matches the "create task" shape but with an unknown workstream --
    # this must still be handled here (a real error message), not fall
    # through to None/general routing.
    result = try_dispatch("create task astrology: read the stars")
    assert result is not None
    name, response = result
    assert name == "create_task"
    assert "astrology" in response


def test_first_matching_command_wins_task_before_marketing_plan():
    # "create task" and "create marketing plan" have disjoint prefixes, so
    # this is really just confirming dispatch order doesn't accidentally
    # cross-match one command's parser against another's text.
    result = try_dispatch("create marketing plan: X")
    assert result[0] == "create_marketing_plan"
