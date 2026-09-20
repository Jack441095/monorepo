"""Phase 4B-5C tests: working memory, approvals, evaluation runner, company domain."""

import json

import pytest

from nite_ai.approvals import ActionLevel, ApprovalDecision, ApprovalRequest, Reversibility
from nite_ai.domain import AgentStatus, DailyBriefData, Goal, GoalKind, ItemStatus, Task
from nite_ai.errors import ValidationError
from nite_ai.evaluation import EvaluationCase, EvaluationSuite, ExpectedOutcome, ObservedOutcome
from nite_ai.evaluation_runner import run_suite
from nite_ai.permissions import Permission
from nite_ai.working_memory import TaskStatus, WorkingMemory


def test_task_transitions_legal_and_illegal():
    wm = WorkingMemory(task_id="t-1")
    wm = wm.transition(TaskStatus.PLANNED).transition(TaskStatus.RUNNING)
    wm = wm.transition(TaskStatus.WAITING_APPROVAL).transition(TaskStatus.RUNNING)
    assert wm.status is TaskStatus.RUNNING
    with pytest.raises(ValidationError):
        wm.transition(TaskStatus.RECEIVED)  # terminal/earlier states not reachable


def test_working_memory_serialization_round_trip():
    wm = WorkingMemory(task_id="t-2", scratch={"k": 1})
    d = json.loads(json.dumps(wm.to_dict()))
    assert d["status"] == "received" and d["scratch"] == {"k": 1}


def test_destructive_approval_requires_permission_declaration():
    with pytest.raises(ValidationError):
        ApprovalRequest(
            approval_id="ap-1",
            action_level=ActionLevel.DESTRUCTIVE,
            capability_id="system.file.delete",
            summary="delete generated cache directory",
        )
    ok = ApprovalRequest(
        approval_id="ap-2",
        action_level=ActionLevel.DESTRUCTIVE,
        capability_id="system.file.delete",
        summary="delete generated cache directory",
        reversibility=Reversibility.PARTIALLY_REVERSIBLE,
        required_permissions=(Permission.DESTRUCTIVE,),
    )
    assert ok.requires_human_approval


def test_irreversible_cannot_claim_undo():
    with pytest.raises(ValidationError):
        ApprovalRequest(
            approval_id="ap-3",
            action_level=ActionLevel.WRITE,
            capability_id="doc.write",
            summary="overwrite document",
            reversibility=Reversibility.IRREVERSIBLE,
            undo_ref="undo-artifact-1",
        )
    decision = ApprovalDecision(approval_id="ap-3", approved=False, decided_by="owner")
    assert not decision.approved


def test_read_actions_stay_low_friction():
    r = ApprovalRequest(
        approval_id="ap-4",
        action_level=ActionLevel.READ,
        capability_id="workflow.status.summary",
        summary="read status",
    )
    assert not r.requires_human_approval


def test_suite_runner_deterministic_and_crash_safe():
    suite = EvaluationSuite(
        suite_id="routing-smoke",
        cases=(
            EvaluationCase(
                case_id="c1", kind="routing",
                expected=ExpectedOutcome(status="success", capability_id="a.b"),
            ),
            EvaluationCase(case_id="c2", kind="routing", expected=ExpectedOutcome(status="success")),
        ),
    )

    def evaluator(case):
        return ObservedOutcome(status="success", capability_id="a.b")

    report = run_suite(suite, evaluator)
    assert report.total == 2 and report.all_passed
    exported = json.loads(report.export_json())
    assert exported["suite_id"] == "routing-smoke"

    def crasher(case):
        raise RuntimeError("boom")

    bad = EvaluationSuite(suite_id="s2", cases=(EvaluationCase(case_id="x", kind="unit"),))
    report_bad = run_suite(bad, crasher)
    assert report_bad.failed == 1  # evaluator crash becomes structured case failure


def test_goal_hierarchy_rules():
    company = Goal(goal_id="g-company", kind=GoalKind.COMPANY, title="Ship platform")
    quarterly = Goal(
        goal_id="g-q1", kind=GoalKind.QUARTERLY, title="Q1 adoption",
        parent_goal_id=company.goal_id,
    )
    assert quarterly.parent_goal_id == "g-company"
    with pytest.raises(ValidationError):
        Goal(goal_id="g-q2", kind=GoalKind.QUARTERLY, title="orphan")


def test_blocked_task_must_reference_blockers():
    with pytest.raises(ValidationError):
        Task(task_id="t-9", title="blocked thing", project_id="p-1", status=ItemStatus.BLOCKED)
    ok = Task(
        task_id="t-10", title="blocked properly", project_id="p-1",
        status=ItemStatus.BLOCKED, blocked_by=("t-11",),
    )
    assert ok.blocked_by == ("t-11",)


def test_daily_brief_serializes_deterministically():
    brief = DailyBriefData(brief_date="2026-08-22", top_priorities=("t-1", "t-2"))
    text = json.dumps(brief.to_dict(), sort_keys=True)
    assert json.loads(text)["brief_date"] == "2026-08-22"


def test_agent_status_contract():
    a = AgentStatus(
        agent_id="kenn-main", role="audio-engineer", state="running",
        current_task_id="t-5", trace_id="abc123",
    )
    assert a.state == "running"
