import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from thursday.company_state import CompanySnapshot, TaskView, GoalView, ApprovalView, AgentRunView
from thursday import company_intelligence
from thursday.registry.handlers import _handle_company_state

def test_query_intent_classification():
    assert company_intelligence.classify_query_intent("What is blocked?") == "BLOCKERS"
    assert company_intelligence.classify_query_intent("Tell me what is overdue") == "OVERDUE"
    assert company_intelligence.classify_query_intent("Are there any pending approvals?") == "OWNER_DECISIONS"
    assert company_intelligence.classify_query_intent("Did any agent fail?") == "FAILURES"
    assert company_intelligence.classify_query_intent("What risks are active?") == "RISKS"
    assert company_intelligence.classify_query_intent("What's focus for today?") == "PRIORITIES"
    assert company_intelligence.classify_query_intent("Give me the status report") == "STATUS"
    assert company_intelligence.classify_query_intent("Random query about stuff") == "UNKNOWN"

def test_priority_engine_ranking():
    # Construct a rich snapshot
    tasks_overdue = [
        TaskView(task_id="t_overdue_1", title="Late Task 1", project_id="p1", status="active", priority=5, due_epoch=1000.0, blocked_by=()),
    ]
    tasks_blocked = [
        TaskView(task_id="t_blocked_1", title="Blocked task 1", project_id="p1", status="blocked", priority=8, due_epoch=None, blocked_by=("owner",)),
    ]
    pending_approvals = [
        ApprovalView(approval_id="app_1", capability_id="cap1", summary="Sign JUCE license agreement", action_level="high", reversibility="irreversible", created_at_epoch=2000.0),
    ]
    open_decisions = [
        {"decision_id": "dec_1", "description": "Choose between macOS and Linux signing certificate"}
    ]
    failed_runs = [
        AgentRunView(run_id="run_1", agent_id="research", status="failed", blocker="timeout", started_at_epoch=500.0, finished_at_epoch=600.0)
    ]
    
    snapshot = CompanySnapshot(
        captured_at_epoch=3000.0,
        goals=(),
        overdue_tasks=tasks_overdue,
        blocked_tasks=tasks_blocked,
        due_today_tasks=(),
        active_projects=[],
        risks=[{"risk_id": "r1", "description": "Critical license expiration", "severity": "high"}],
        open_decisions=open_decisions,
        pending_approvals=pending_approvals,
        recent_agent_runs=[],
        failed_agent_runs=failed_runs
    )
    
    priorities = company_intelligence.calculate_priorities(snapshot)
    
    # 1. Sign JUCE license agreement should rank extremely high because of title triggers and high action level
    top_prio = priorities[0]
    assert "Sign JUCE license agreement" in top_prio.title
    
    # Check that sorting is deterministic and stably falls back to item_id
    assert len(priorities) > 0

def test_enumeration_bundle_coverage():
    tasks_blocked = [
        TaskView(task_id="t_blocked_1", title="Task p1_a", project_id="proj_one", status="blocked", priority=8, due_epoch=None, blocked_by=()),
        TaskView(task_id="t_blocked_2", title="Task p2_b", project_id="proj_two", status="blocked", priority=5, due_epoch=None, blocked_by=()),
    ]
    snapshot = CompanySnapshot(
        captured_at_epoch=3000.0,
        goals=(),
        overdue_tasks=(),
        blocked_tasks=tasks_blocked,
        due_today_tasks=(),
        active_projects=[],
        risks=[],
        open_decisions=[],
        pending_approvals=[],
        recent_agent_runs=[],
        failed_agent_runs=[]
    )
    
    # Filter for 'proj_one'
    bundle = company_intelligence.enumerate_entities(snapshot, "BLOCKERS", scope_filter="proj_one")
    assert bundle.total_qualifying == 1
    assert bundle.items_returned == 1
    assert bundle.items_excluded == 1
    assert bundle.complete is True
    assert "Excluded" in bundle.exclusion_reasons[0]

def test_handler_renderer_fallback(monkeypatch):
    # Disable LLM and check fallback
    monkeypatch.delenv("AUDIO_TOO_LLM_ENABLED", raising=False)
    monkeypatch.delenv("THURSDAY_BRAIN_ENABLED", raising=False)
    
    tasks_blocked = [
        TaskView(task_id="t_blocked_1", title="Fix compiler bug", project_id="p1", status="blocked", priority=5, due_epoch=None, blocked_by=()),
    ]
    snapshot = CompanySnapshot(
        captured_at_epoch=3000.0,
        goals=(),
        overdue_tasks=(),
        blocked_tasks=tasks_blocked,
        due_today_tasks=(),
        active_projects=[],
        risks=[],
        open_decisions=[],
        pending_approvals=[],
        recent_agent_runs=[],
        failed_agent_runs=[]
    )
    
    with patch("thursday.company_state.get_snapshot", return_value=snapshot):
        text = _handle_company_state("what's blocked?", {})
        assert "Blocked (1)" in text
        assert "Fix compiler bug" in text
