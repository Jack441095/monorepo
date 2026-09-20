"""Tests for thursday/advertising_ops.py (Thursday Ops upgrade, phase 2).

Two safety contracts to hold, beyond the usual "don't fabricate" one:
(1) there is no function anywhere in this module that spends money or
launches a live ad -- create_campaign_plan() only ever produces a plan
and an approval-gated task; (2) ad_readiness_check()'s Decision line must
never exceed "Prepare only" while critical items still read "Evidence
missing" -- no combination of inputs should make it say "Ready".
"""

from __future__ import annotations

import pytest

import thursday.ops.advertising_ops as ao
import thursday.ops.task_ledger as tl
from thursday.registry.handlers import _handle_ad_readiness, _handle_create_campaign_plan


@pytest.fixture(autouse=True)
def _isolated_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(ao, "CAMPAIGN_PLANS_FILE", tmp_path / "ad_campaign_plans.json")
    monkeypatch.setattr(tl, "TASK_LEDGER_FILE", tmp_path / "task_ledger.json")


# ── parse_create_campaign_plan_command ───────────────────────────────────


def test_parse_product_only():
    assert ao.parse_create_campaign_plan_command("create campaign plan: Submit") == ("Submit", {})


def test_parse_with_pipe_delimited_fields():
    text = (
        "create campaign plan: Submit "
        "| platform: google search "
        "| budget: £5/day, £10/day, £25/day "
        "| audience: indie audio engineers"
    )
    product, fields = ao.parse_create_campaign_plan_command(text)
    assert product == "Submit"
    assert fields["platform"] == "google search"
    assert fields["budget_scenarios"] == ["£5/day", "£10/day", "£25/day"]
    assert fields["audience"] == "indie audio engineers"


def test_parse_returns_none_for_non_matching_text():
    assert ao.parse_create_campaign_plan_command("what's the weather") is None


def test_parse_raises_on_empty_product():
    with pytest.raises(ValueError):
        ao.parse_create_campaign_plan_command("create campaign plan: | platform: google")


# ── create_campaign_plan / render ────────────────────────────────────────


def test_no_launch_or_spend_function_exists():
    # A safety property, not just a naming convention: nothing in this
    # module's public surface can spend money or launch a live ad.
    public_names = [n for n in dir(ao) if not n.startswith("_")]
    forbidden_substrings = ("launch", "spend", "publish", "submit_campaign")
    for name in public_names:
        lname = name.lower()
        assert not any(f in lname for f in forbidden_substrings), name


def test_create_plan_links_medium_risk_approval_required_task():
    plan = ao.create_campaign_plan("Submit")
    task = tl.get_task(plan.task_id)
    assert task.workstream == "advertising"
    assert task.approval_required is True
    assert task.risk_level == "medium"


def test_render_marks_unfilled_fields_not_specified():
    plan = ao.create_campaign_plan("Submit")
    rendered = ao.render_campaign_plan(plan)
    assert "PLATFORM: Not specified" in rendered
    assert "BUDGET SCENARIOS: Not specified" in rendered
    assert "AD COPY VARIANTS: Not specified" in rendered


def test_render_includes_supplied_fields():
    plan = ao.create_campaign_plan(
        "Submit", platform="google search", budget_scenarios=["£5/day", "£10/day"],
    )
    rendered = ao.render_campaign_plan(plan)
    assert "PLATFORM: google search" in rendered
    assert "BUDGET SCENARIOS: £5/day, £10/day" in rendered


def test_render_always_requires_approval_before_any_spend():
    plan = ao.create_campaign_plan("Submit")
    rendered = ao.render_campaign_plan(plan)
    assert "APPROVAL REQUIRED: before any spend or launch" in rendered


# ── ad_readiness_check ────────────────────────────────────────────────────


def test_readiness_check_never_says_ready_with_no_data():
    out = ao.ad_readiness_check()
    assert "- Not ready" in out
    assert "Evidence missing" in out
    # Never a bare "Ready" decision under any circumstance this module
    # can construct on its own (no real per-item verification exists).
    assert "- Ready for" not in out


def test_readiness_check_still_says_prepare_only_not_ready_with_plans_on_file():
    ao.create_campaign_plan("Submit", platform="google", budget_scenarios=["£5/day"])
    out = ao.ad_readiness_check()
    assert "- Prepare only" in out
    # Even with a rich plan on file, still never claims full readiness --
    # the critical items (landing page, checkout, analytics) are still
    # Evidence missing and nothing here can override that.
    assert "- Ready for" not in out


def test_readiness_check_reports_real_plan_and_task_counts():
    ao.create_campaign_plan("Submit", audience="engineers")
    out = ao.ad_readiness_check()
    assert "Audience defined? Yes, in at least one plan on file." in out


# ── handlers ──────────────────────────────────────────────────────────────


def test_create_campaign_plan_handler_end_to_end():
    out = _handle_create_campaign_plan("create campaign plan: Submit | platform: google search")
    assert "AD CAMPAIGN PLAN" in out
    assert "PRODUCT: Submit" in out
    assert "PLATFORM: google search" in out


def test_ad_readiness_handler_end_to_end():
    out = _handle_ad_readiness()
    assert "AD READINESS CHECK" in out
