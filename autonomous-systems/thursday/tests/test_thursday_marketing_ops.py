"""Tests for thursday/marketing_ops.py (Thursday Ops upgrade, phase 2).

Non-fabrication contract: create_marketing_plan() never invents an
audience, core message, or proof point that wasn't supplied -- unfilled
fields render "Not specified" rather than guessed content. Every plan is
linked to an approval_required=True task_ledger entry.
"""

from __future__ import annotations

import pytest

import thursday.ops.marketing_ops as mo
import thursday.ops.task_ledger as tl
from thursday.registry.handlers import _handle_create_marketing_plan


@pytest.fixture(autouse=True)
def _isolated_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(mo, "MARKETING_PLANS_FILE", tmp_path / "marketing_plans.json")
    monkeypatch.setattr(tl, "TASK_LEDGER_FILE", tmp_path / "task_ledger.json")


# ── parse_create_marketing_plan_command ─────────────────────────────────


def test_parse_objective_only():
    assert mo.parse_create_marketing_plan_command(
        "create marketing plan: Prepare Submit launch content"
    ) == ("Prepare Submit launch content", {})


def test_parse_with_pipe_delimited_fields():
    text = (
        "create marketing plan: Prepare Submit launch content "
        "| audience: beta testers and early adopters "
        "| channels: website, linkedin "
        "| content ideas: progress update post, feature demo"
    )
    objective, fields = mo.parse_create_marketing_plan_command(text)
    assert objective == "Prepare Submit launch content"
    assert fields["audience"] == "beta testers and early adopters"
    assert fields["channels"] == ["website", "linkedin"]
    assert fields["content_ideas"] == ["progress update post", "feature demo"]


def test_parse_ignores_unrecognized_field_keys():
    text = "create marketing plan: X | nonsense field: whatever"
    objective, fields = mo.parse_create_marketing_plan_command(text)
    assert objective == "X"
    assert fields == {}


def test_parse_returns_none_for_non_matching_text():
    assert mo.parse_create_marketing_plan_command("what's the weather") is None
    assert mo.parse_create_marketing_plan_command("active tasks") is None


def test_parse_raises_on_empty_objective():
    with pytest.raises(ValueError):
        mo.parse_create_marketing_plan_command("create marketing plan: | audience: x")


# ── create_marketing_plan / render ───────────────────────────────────────


def test_create_plan_links_an_approval_required_task():
    plan = mo.create_marketing_plan("Prepare launch content")
    task = tl.get_task(plan.task_id)
    assert task.workstream == "marketing"
    assert task.approval_required is True
    assert task.objective == "Prepare launch content"


def test_render_marks_unfilled_fields_not_specified_never_invented():
    plan = mo.create_marketing_plan("Prepare launch content")
    rendered = mo.render_marketing_plan(plan)
    assert "AUDIENCE: Not specified" in rendered
    assert "CORE MESSAGE: Not specified" in rendered
    assert "CHANNELS: Not specified" in rendered
    # Never fabricates a plausible-sounding audience/message.
    assert "early adopters" not in rendered
    assert "producers and engineers" not in rendered


def test_render_includes_supplied_fields_verbatim():
    plan = mo.create_marketing_plan(
        "Prepare launch content",
        audience="beta testers",
        channels=["website", "linkedin"],
    )
    rendered = mo.render_marketing_plan(plan)
    assert "AUDIENCE: beta testers" in rendered
    assert "CHANNELS: website, linkedin" in rendered


def test_render_always_states_approval_required_before_publishing():
    plan = mo.create_marketing_plan("X")
    rendered = mo.render_marketing_plan(plan)
    assert "APPROVAL REQUIRED BEFORE: publishing" in rendered


def test_list_marketing_plans_sorted_by_created_at():
    a = mo.create_marketing_plan("A")
    b = mo.create_marketing_plan("B")
    ids = [p.plan_id for p in mo.list_marketing_plans()]
    assert ids == [a.plan_id, b.plan_id]


# ── audit_marketing_readiness ────────────────────────────────────────────


def test_readiness_audit_is_honest_about_no_data_source():
    out = mo.audit_marketing_readiness()
    assert "Evidence missing" in out  # website/tone/performance are unverifiable
    assert "Marketing plans on file: 0" in out


def test_readiness_audit_counts_real_plans_and_tasks():
    mo.create_marketing_plan("A")
    mo.create_marketing_plan("B")
    out = mo.audit_marketing_readiness()
    assert "Marketing plans on file: 2" in out
    assert "Marketing tasks in the ledger: 2" in out
    assert "Plans awaiting approval: 2" in out


# ── _handle_create_marketing_plan ────────────────────────────────────────


def test_handler_end_to_end():
    out = _handle_create_marketing_plan(
        "create marketing plan: Prepare launch content | audience: beta testers"
    )
    assert "MARKETING PLAN" in out
    assert "OBJECTIVE: Prepare launch content" in out
    assert "AUDIENCE: beta testers" in out


def test_handler_reports_non_command_helpfully():
    out = _handle_create_marketing_plan("what's the weather")
    assert "didn't recognize" in out
