"""Tests for thursday/task_ledger.py -- the founder-facing persistent task
ledger (Thursday Ops upgrade, phase 1: task lifecycle). Deliberately
separate from thursday/taskgraph.py (in-process subagent dependency
graphs) and orchestration_models.py (internal dispatch state machine) --
see task_ledger.py's module docstring for why conflating them would be a
mistake. Not a replacement for the real confirmation-token approval
system either (confirmation.py/action_receipts.py) -- approval_required
here is a founder-facing planning flag only.
"""

from __future__ import annotations

import pytest

import thursday.ops.task_ledger as tl
from thursday.registry.handlers import _handle_create_task


@pytest.fixture(autouse=True)
def _isolated_ledger(monkeypatch, tmp_path):
    monkeypatch.setattr(tl, "TASK_LEDGER_FILE", tmp_path / "task_ledger.json")


# ── create_task ──────────────────────────────────────────────────────────


def test_create_task_defaults():
    t = tl.create_task("marketing", "Prepare this week's marketing plan.")
    assert t.workstream == "marketing"
    assert t.objective == "Prepare this week's marketing plan."
    assert t.status == "proposed"
    assert t.priority == "medium"
    assert t.risk_level == "low"
    assert t.approval_required is False
    assert t.evidence == []
    assert t.blockers == []


def test_create_task_ids_are_deterministic_and_sequential():
    a = tl.create_task("engineering", "Fix bug.")
    b = tl.create_task("engineering", "Fix another bug.")
    c = tl.create_task("marketing", "Draft post.")
    assert a.task_id == "task-engineering-1"
    assert b.task_id == "task-engineering-2"
    assert c.task_id == "task-marketing-3"


def test_create_task_rejects_unknown_workstream():
    with pytest.raises(tl.InvalidWorkstream):
        tl.create_task("astrology", "Read the stars.")


def test_create_task_rejects_unknown_priority():
    with pytest.raises(ValueError):
        tl.create_task("engineering", "x", priority="asap")


def test_create_task_persists_across_loads():
    created = tl.create_task("funding", "Prepare grant evidence pack.", priority="high")
    fetched = tl.get_task(created.task_id)
    assert fetched == created


# ── update_task / complete_task / block_task ─────────────────────────────


def test_update_task_merges_fields_and_bumps_updated_at():
    t = tl.create_task("product", "Ship beta.")
    updated = tl.update_task(t.task_id, status="active", next_action="Cut release branch.")
    assert updated.status == "active"
    assert updated.next_action == "Cut release branch."
    assert updated.updated_at >= t.updated_at


def test_update_task_rejects_unknown_status():
    t = tl.create_task("product", "Ship beta.")
    with pytest.raises(tl.InvalidStatus):
        tl.update_task(t.task_id, status="vibing")


def test_update_task_raises_on_unknown_id():
    with pytest.raises(tl.TaskNotFound):
        tl.update_task("task-nope-999", status="done")


def test_complete_task_clears_blockers_and_appends_evidence():
    t = tl.create_task("qa", "Run regression suite.")
    tl.block_task(t.task_id, "Waiting on CI runner.")
    completed = tl.complete_task(t.task_id, evidence=["tests/thursday: 844 passed"])
    assert completed.status == "done"
    assert completed.blockers == []
    assert completed.evidence == ["tests/thursday: 844 passed"]


def test_block_task_appends_to_existing_blockers():
    t = tl.create_task("infrastructure", "Deploy readiness check.")
    tl.block_task(t.task_id, "DNS not verified.")
    twice_blocked = tl.block_task(t.task_id, "Payment webhook untested.")
    assert twice_blocked.status == "blocked"
    assert twice_blocked.blockers == ["DNS not verified.", "Payment webhook untested."]


# ── listing / filtering ───────────────────────────────────────────────────


def test_list_tasks_empty_ledger():
    assert tl.list_tasks() == []
    assert tl.active_tasks() == []
    assert tl.blocked_tasks() == []
    assert tl.tasks_requiring_approval() == []


def test_active_tasks_excludes_done_and_cancelled():
    a = tl.create_task("marketing", "Draft launch post.")
    b = tl.create_task("engineering", "Fix crash.")
    tl.update_task(a.task_id, status="active")
    tl.update_task(b.task_id, status="done")
    active_ids = {t.task_id for t in tl.active_tasks()}
    assert active_ids == {a.task_id}


def test_tasks_by_workstream_filters_correctly():
    tl.create_task("marketing", "Draft post.")
    tl.create_task("engineering", "Fix bug.")
    tl.create_task("marketing", "Content calendar.")
    marketing = tl.tasks_by_workstream("marketing")
    assert len(marketing) == 2
    assert all(t.workstream == "marketing" for t in marketing)


def test_tasks_requiring_approval_only_open_and_flagged():
    approved_open = tl.create_task("advertising", "Launch ad campaign.", approval_required=True)
    tl.create_task("advertising", "Draft ad copy.", approval_required=False)
    done_but_flagged = tl.create_task("funding", "Submit grant.", approval_required=True)
    tl.update_task(done_but_flagged.task_id, status="done")

    pending = tl.tasks_requiring_approval()
    assert [t.task_id for t in pending] == [approved_open.task_id]


def test_list_tasks_sorted_by_created_at():
    first = tl.create_task("research", "A")
    second = tl.create_task("research", "B")
    third = tl.create_task("research", "C")
    ids_in_order = [t.task_id for t in tl.list_tasks()]
    assert ids_in_order == [first.task_id, second.task_id, third.task_id]


# ── parse_create_task_command ───────────────────────────────────────────


def test_parse_basic_colon_form():
    assert tl.parse_create_task_command("create task marketing: draft this week's post") == (
        "marketing", "draft this week's post",
    )


def test_parse_add_task_for_with_dash():
    assert tl.parse_create_task_command("add task for advertising - prepare campaign brief") == (
        "advertising", "prepare campaign brief",
    )


def test_parse_new_task_variant():
    assert tl.parse_create_task_command("new task engineering: fix the crash on export") == (
        "engineering", "fix the crash on export",
    )


def test_parse_resolves_workstream_aliases():
    assert tl.parse_create_task_command("create task finance: chase overdue invoice") == (
        "finance_admin", "chase overdue invoice",
    )
    assert tl.parse_create_task_command("create task ads: draft copy") == (
        "advertising", "draft copy",
    )
    assert tl.parse_create_task_command("create task finance admin: reconcile books") == (
        "finance_admin", "reconcile books",
    )


def test_parse_is_case_insensitive():
    assert tl.parse_create_task_command("CREATE TASK Marketing: Draft Post") == (
        "marketing", "Draft Post",
    )


def test_parse_returns_none_for_non_matching_text():
    assert tl.parse_create_task_command("what's my daily status") is None
    assert tl.parse_create_task_command("active tasks") is None
    assert tl.parse_create_task_command("") is None


def test_parse_raises_on_unknown_workstream():
    with pytest.raises(tl.UnrecognizedWorkstream):
        tl.parse_create_task_command("create task astrology: read the stars")


def test_parse_returns_none_for_empty_objective():
    # The regex's objective group requires at least one character, so
    # "task marketing:" with nothing after the colon simply isn't a match
    # -- not a command with an empty objective to reject.
    assert tl.parse_create_task_command("create task marketing:") is None


def test_parse_raises_on_whitespace_only_objective():
    # Colon followed by only spaces DOES match the regex (the lazy .+?
    # consumes a space), but strips to an empty objective -- this is the
    # case the explicit "empty objective" check in the parser exists for.
    with pytest.raises(ValueError):
        tl.parse_create_task_command("create task marketing:    ")


# ── _handle_create_task ──────────────────────────────────────────────────


def test_handler_creates_task_and_confirms():
    out = _handle_create_task("create task marketing: draft this week's post")
    assert "Created task-marketing-1" in out
    assert "draft this week's post" in out
    task = tl.get_task("task-marketing-1")
    assert task.workstream == "marketing"
    assert task.status == "proposed"


def test_handler_reports_unknown_workstream_with_valid_list():
    out = _handle_create_task("create task astrology: read the stars")
    assert "astrology" in out
    assert "marketing" in out  # part of the known-workstreams list


def test_handler_reports_non_command_text_helpfully():
    out = _handle_create_task("what's the weather")
    assert "didn't recognize" in out
    assert "create task <workstream>: <objective>" in out
