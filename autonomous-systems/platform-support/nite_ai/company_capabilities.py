"""Company capability registry (Phase 4B).

Exposes structured company state as registered nite_ai capabilities. All
read-only queries are LOW risk; approval decisions are WRITE-level and change
internal state only — executing an approved external action is a separate,
separately-permissioned operation that does not exist yet.

Grounding rule: handlers report empty/missing state honestly. No synthetic
company data is ever substituted outside tests.
"""

from __future__ import annotations

from typing import Any

from nite_ai.adapters import ProductAdapter
from nite_ai.briefing import assemble_daily_brief, assemble_weekly_review
from nite_ai.capabilities import CapabilityRegistry
from nite_ai.company_store import CompanyStore
from nite_ai.contracts import (
    AgentRequest,
    AgentResult,
    CapabilityDefinition,
    LatencyClass,
    ResultStatus,
)
from nite_ai.errors import AgentError, ErrorCategory, ValidationError
from nite_ai.permissions import ActionRisk, Permission

PLATFORM_PROVIDER_ID = "nite_ai.company_store"


def _def(capability_id: str, description: str, *, risk: ActionRisk = ActionRisk.LOW,
         permissions: tuple = (Permission.READ,), version: str = "0.1.0") -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
        version=version,
        description=description,
        permissions=permissions,
        risk=risk,
        provider_id=PLATFORM_PROVIDER_ID,
        latency_class=LatencyClass.INTERACTIVE,
    )


def _success(request: AgentRequest, payload: dict[str, Any]) -> AgentResult:
    return AgentResult(request_id=request.request_id, status=ResultStatus.SUCCESS,
                       result=payload)


def register_company_capabilities(
    adapter: ProductAdapter, registry: CapabilityRegistry, store: CompanyStore
) -> dict[str, str]:
    """Register the read-only company capability set plus approval decision."""
    def brief_daily(req: AgentRequest) -> AgentResult:
        return _success(req, {"daily_brief": assemble_daily_brief(store).to_dict()})

    def review_weekly(req: AgentRequest) -> AgentResult:
        return _success(req, {"weekly_review": assemble_weekly_review(store).to_dict()})

    def goals_list(req: AgentRequest) -> AgentResult:
        goals = store.list_goals()
        return _success(req, {
            "count": len(goals),
            "goals": [
                {"goal_id": g.goal_id, "kind": g.kind.value, "title": g.title,
                 "status": g.status.value, "progress": g.progress,
                 "parent_goal_id": g.parent_goal_id}
                for g in goals
            ],
            "state_note": "no company state recorded yet" if not goals else "",
        })

    def tasks_list(req: AgentRequest) -> AgentResult:
        tasks = store.list_tasks()
        return _success(req, {
            "count": len(tasks),
            "tasks": [
                {"task_id": t.task_id, "title": t.title, "project_id": t.project_id,
                 "status": t.status.value, "priority": t.priority,
                 "blocked_by": list(t.blocked_by)}
                for t in tasks
            ],
            "state_note": "no company state recorded yet" if not tasks else "",
        })

    def risks_list(req: AgentRequest) -> AgentResult:
        risks = store.list_active_risks()
        return _success(req, {"count": len(risks), "risks": risks})

    def decisions_pending(req: AgentRequest) -> AgentResult:
        decisions = store.list_open_decisions()
        return _success(req, {"count": len(decisions), "decisions": decisions})

    def agents_status(req: AgentRequest) -> AgentResult:
        runs = store.recent_agent_runs(limit=25)
        return _success(req, {
            "recent_runs": runs,
            "completed_count": sum(1 for r in runs if r["status"] == "completed"),
            "failed_count": sum(1 for r in runs if r["status"] == "failed"),
        })

    def approvals_pending(req: AgentRequest) -> AgentResult:
        pending = store.list_pending_approvals()
        return _success(req, {"count": len(pending), "approvals": pending})

    def approvals_decide(req: AgentRequest) -> AgentResult:
        # WRITE-level internal state change. Never executes external actions.
        payload = req.payload or {}
        try:
            record = store.decide_approval(
                approval_id=str(payload.get("approval_id", "")),
                approved=bool(payload.get("approved", False)),
                decided_by=str(payload.get("decided_by", "")),
            )
        except ValidationError as exc:
            return AgentResult(
                request_id=req.request_id,
                status=ResultStatus.FAILED,
                error=AgentError(ErrorCategory.INVALID_INPUT, str(exc), retryable=False),
            )
        return _success(req, {"approval": record})

    specs = [
        (_def("company.brief.daily",
              "Deterministic daily company brief from structured company state"),
         brief_daily),
        (_def("company.review.weekly",
              "Deterministic weekly company review from structured company state"),
         review_weekly),
        (_def("company.goals.list", "List persisted company goals"), goals_list),
        (_def("company.tasks.list", "List persisted company tasks"), tasks_list),
        (_def("company.risks.list", "List active company risks"), risks_list),
        (_def("company.decisions.pending", "List open decisions awaiting action"),
         decisions_pending),
        (_def("company.agents.status", "Recent agent run status overview"), agents_status),
        (_def("company.approvals.pending", "List approvals awaiting owner decision"),
         approvals_pending),
        (_def("company.approvals.decide",
              "Record an owner decision on a pending approval (internal state only)",
              risk=ActionRisk.HIGH, permissions=(Permission.READ, Permission.WRITE)),
         approvals_decide),
    ]
    for definition, handler in specs:
        adapter.register(registry, definition, handler)
    return {d.capability_id: d.version for d, _ in specs}


__all__ = ["PLATFORM_PROVIDER_ID", "register_company_capabilities"]

