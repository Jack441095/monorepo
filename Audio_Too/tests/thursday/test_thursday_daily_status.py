"""Tests for thursday/daily_status.py -- the founder-facing "where are we
today" ops status (Thursday Ops upgrade, phase 1). Anti-hallucination
contract: PRODUCT STATUS / COMMERCIAL STATUS have no real data source
wired up yet and must say so plainly, never invent a status; the
recommended action and "can prepare" lists must be derived only from real
task_ledger records, never guessed.
"""

from __future__ import annotations

import pytest

import thursday.ops.task_ledger as tl
from thursday.ops.daily_status import compose_daily_status, render_daily_status


@pytest.fixture(autouse=True)
def _isolated_ledger(monkeypatch, tmp_path):
    monkeypatch.setattr(tl, "TASK_LEDGER_FILE", tmp_path / "task_ledger.json")


def test_empty_ledger_is_honest_not_fabricated():
    status = compose_daily_status()
    assert status["active_count"] == 0
    assert status["top_priorities"] == []
    assert "No active tasks in the ledger" in status["recommended_action"]

    rendered = render_daily_status(status)
    assert "No active tasks in the ledger." in rendered
    assert "Evidence missing" in rendered  # product/commercial sections
    # Never claims a product status it has no data for.
    assert "Submit: on track" not in rendered
    assert "Submit: shipped" not in rendered


def test_top_priorities_ordered_urgent_first():
    low = tl.create_task("research", "Read a paper.", priority="low")
    urgent = tl.create_task("engineering", "Fix payment bug.", priority="urgent")
    medium = tl.create_task("marketing", "Draft post.", priority="medium")
    for t in (low, urgent, medium):
        tl.update_task(t.task_id, status="active")

    status = compose_daily_status()
    ids_in_order = [t.task_id for t in status["top_priorities"]]
    assert ids_in_order == [urgent.task_id, medium.task_id, low.task_id]


def test_top_priorities_capped_at_three():
    for i in range(5):
        t = tl.create_task("engineering", f"Task {i}", priority="high")
        tl.update_task(t.task_id, status="active")
    status = compose_daily_status()
    assert len(status["top_priorities"]) == 3
    assert status["active_count"] == 5


def test_recommended_action_uses_top_task_next_action():
    t = tl.create_task("advertising", "Prepare campaign.", priority="urgent",
                        next_action="Draft three ad copy variants.")
    tl.update_task(t.task_id, status="active")
    status = compose_daily_status()
    assert status["recommended_action"] == "Draft three ad copy variants."


def test_recommended_action_flags_missing_next_action_honestly():
    t = tl.create_task("qa", "Regression pass.", priority="urgent")
    tl.update_task(t.task_id, status="active")  # no next_action set
    status = compose_daily_status()
    assert "no next_action recorded yet" in status["recommended_action"]


def test_blocked_tasks_show_their_blocker_reason():
    t = tl.create_task("infrastructure", "Deploy readiness.")
    tl.block_task(t.task_id, "DNS not verified.")
    rendered = render_daily_status(compose_daily_status())
    assert "DNS not verified." in rendered
    assert t.task_id in rendered


def test_no_blockers_says_so_plainly():
    rendered = render_daily_status(compose_daily_status())
    assert "BLOCKERS:" in rendered
    idx = rendered.index("BLOCKERS:")
    assert "None recorded in the ledger." in rendered[idx:idx + 100]


def test_approvals_needed_lists_flagged_open_tasks_only():
    needs_it = tl.create_task("funding", "Submit grant application.", approval_required=True)
    tl.update_task(needs_it.task_id, status="active")
    doesnt_need_it = tl.create_task("marketing", "Draft internal notes.", approval_required=False)
    tl.update_task(doesnt_need_it.task_id, status="active")

    status = compose_daily_status()
    approval_ids = {t.task_id for t in status["needs_approval"]}
    assert approval_ids == {needs_it.task_id}

    rendered = render_daily_status(status)
    assert needs_it.task_id in rendered
    assert doesnt_need_it.task_id not in rendered.split("APPROVALS NEEDED:")[1].split("RECOMMENDED")[0]


def test_can_prepare_lists_proposed_tasks():
    proposed = tl.create_task("marketing", "Content calendar.")
    tl.update_task(proposed.task_id, status="active")
    tl.update_task(proposed.task_id, status="proposed")  # back to proposed, still "active" per OPEN_STATUSES
    status = compose_daily_status()
    joined = " ".join(status["thursday_can_prepare"])
    assert "Content calendar." in joined
