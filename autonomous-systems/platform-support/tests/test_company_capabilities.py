"""Phase 4B/4F tests: company capabilities, approval inbox, grounding honesty."""

import json

import pytest

from nite_ai.adapters import ProductAdapter
from nite_ai.capabilities import CapabilityRegistry
from nite_ai.company_capabilities import register_company_capabilities
from nite_ai.company_store import open_store
from nite_ai.contracts import AgentRequest, ResultStatus
from nite_ai.domain import Goal, GoalKind, ItemStatus, Project, Task
from nite_ai.errors import ErrorCategory
from nite_ai.permissions import Permission

NOW = 1_755_744_000.0


@pytest.fixture
def populated_store(tmp_path):
    conn, st = open_store(tmp_path / "company.db")
    st.create_goal(Goal(goal_id="g-co", kind=GoalKind.COMPANY, title="Ship products"))
    q = Goal(goal_id="g-q", kind=GoalKind.QUARTERLY, title="Q readiness",
             parent_goal_id="g-co", progress=0.5, status=ItemStatus.ACTIVE)
    st.create_goal(q)
    st.create_project(Project(project_id="p1", title="SLO", goal_id="g-q"))
    st.create_task(Task(task_id="t-1", title="Release blocker", project_id="p1",
                        status=ItemStatus.BLOCKED, blocked_by=("t-2",), priority=9))
    st.create_task(Task(task_id="t-2", title="Overdue review", project_id="p1",
                        status=ItemStatus.ACTIVE, due_epoch=NOW - 3600, priority=8))
    st.record_decision("d-1", "Defer runtime POC")
    st.record_risk("r-1", "Bus factor", severity="high")
    st.record_agent_run("run-1", agent_id="kenn-main", status="completed",
                        task_id="t-2", trace_id="tr-1")
    st.record_approval("ap-1", action_level="write", capability_id="company.store.write",
                       summary="publish release notes", requested_by="thursday")
    yield st
    conn.close()


@pytest.fixture
def company_adapter(populated_store):
    adapter = ProductAdapter("nite_ai.company")
    registry = CapabilityRegistry()
    registered = register_company_capabilities(adapter, registry, populated_store)
    assert len(registered) == 9
    return adapter, registry


def make_req(capability, granted=(Permission.READ,), payload=None):
    return AgentRequest(request_id="req-1", trace_id="trace-1", capability_id=capability,
                        payload=payload or {}, granted_permissions=tuple(granted))


def test_daily_brief_capability(company_adapter):
    adapter, _ = company_adapter
    result = adapter.dispatch(make_req("company.brief.daily"))
    assert result.ok
    b = result.result["daily_brief"]
    assert b["top_priorities"] == ["t-2"]          # overdue first
    assert b["blockers"] == ["t-1"]
    assert b["agent_completions"] == ["kenn-main"]


def test_weekly_review_capability(company_adapter):
    adapter, _ = company_adapter
    result = adapter.dispatch(make_req("company.review.weekly"))
    assert result.ok
    review = result.result["weekly_review"]
    assert ["g-q", 0.5] in review["goals_progress"]
    assert review["risks"] == ["r-1"] and "d-1" in review["decisions_made"]


def test_empty_state_is_honest(tmp_path):
    conn, empty = open_store(tmp_path / "empty.db")
    adapter = ProductAdapter("nite_ai.company")
    register_company_capabilities(adapter, CapabilityRegistry(), empty)
    result = adapter.dispatch(make_req("company.goals.list"))
    assert result.ok
    assert result.result["count"] == 0
    assert result.result["state_note"] == "no company state recorded yet"
    tasks = adapter.dispatch(make_req("company.tasks.list"))
    assert tasks.result["state_note"] == "no company state recorded yet"
    conn.close()


def test_agent_status_capability(company_adapter):
    adapter, _ = company_adapter
    result = adapter.dispatch(make_req("company.agents.status"))
    assert result.ok
    assert result.result["completed_count"] == 1 and result.result["failed_count"] == 0


def test_approval_pending_and_decide(company_adapter):
    adapter, _ = company_adapter
    pending = adapter.dispatch(make_req("company.approvals.pending"))
    assert pending.result["count"] == 1

    denied = adapter.dispatch(make_req("company.approvals.decide", granted=()))
    assert not denied.ok and denied.error.category == ErrorCategory.PERMISSION_DENIED

    decided = adapter.dispatch(make_req(
        "company.approvals.decide",
        granted=(Permission.READ, Permission.WRITE),
        payload={"approval_id": "ap-1", "approved": True, "decided_by": "owner"},
    ))
    assert decided.ok and decided.result["approval"]["status"] == "approved"
    after = adapter.dispatch(make_req("company.approvals.pending"))
    assert after.result["count"] == 0


def test_approval_decide_validation(company_adapter):
    adapter, _ = company_adapter
    bad = adapter.dispatch(make_req(
        "company.approvals.decide", granted=(Permission.READ, Permission.WRITE),
        payload={"approval_id": "ap-1", "approved": True, "decided_by": ""},
    ))
    assert not bad.ok and bad.error.category == ErrorCategory.INVALID_INPUT
    missing = adapter.dispatch(make_req(
        "company.approvals.decide", granted=(Permission.READ, Permission.WRITE),
        payload={"approval_id": "nope", "approved": True, "decided_by": "owner"},
    ))
    assert not missing.ok
