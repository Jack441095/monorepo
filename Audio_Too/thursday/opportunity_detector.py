"""Deterministic opportunity detector for Thursday V2-H.

Scans a CompanySnapshot and shadow state to find actionable engineering
situations. Every opportunity MUST have deterministic provenance — no
opportunities are manufactured without evidence.

Anti-busywork policy
--------------------
* Healthy systems frequently produce NO_ACTION. This is the correct output.
* Opportunities without source_evidence are structurally rejected.
* Low-value cleanup is always demoted below threshold unless a specific
  signal (release gate, blocker) elevates it.

Provenance requirement
----------------------
Every Opportunity carries a source_evidence string that answers:
    "Why does this work need to exist right now?"
Evidence classes:
    FAILING_TEST      — machine-verifiable test failure in snapshot
    STALLED_RUN       — agent run with no heartbeat progress
    MISSING_EVIDENCE  — qualification marker absent from expected path
    BENCHMARK_REGRESS — numeric benchmark score below accepted threshold
    CANDIDATE_PENDING — integration candidate waiting for review
    KNOWN_BLOCKER     — task blocked on a resolvable dependency
    STALE_DOC         — documentation freshness marker expired
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from thursday.engineering_contracts import (
    AttentionLevel,
    LoopDecision,
    ResourceClass,
    RiskClass,
    ValueClass,
)


# ---------------------------------------------------------------------------
# Opportunity
# ---------------------------------------------------------------------------

class ProvenanceClass:
    FAILING_TEST       = "FAILING_TEST"
    STALLED_RUN        = "STALLED_RUN"
    MISSING_EVIDENCE   = "MISSING_EVIDENCE"
    BENCHMARK_REGRESS  = "BENCHMARK_REGRESS"
    CANDIDATE_PENDING  = "CANDIDATE_PENDING"
    KNOWN_BLOCKER      = "KNOWN_BLOCKER"
    STALE_DOC          = "STALE_DOC"


@dataclass(frozen=True)
class Opportunity:
    """Actionable engineering situation with mandatory provenance.

    Raises ValueError if source_evidence is empty (anti-busywork guard).
    """
    opportunity_id:   str
    source_project:   str
    source_evidence:  str          # Must be non-empty
    provenance_class: str          # ProvenanceClass constant
    problem_statement: str
    value_class:      ValueClass
    risk_class:       RiskClass
    priority_score:   int          # Lower = more urgent (0 = critical)
    confidence:       float
    attention_level:  AttentionLevel
    recommended_specialists: tuple[str, ...]
    estimated_resource_class: ResourceClass = ResourceClass.LIGHT
    owner_approval_required: bool = False
    raw_evidence:     dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_evidence.strip():
            raise ValueError(
                f"Opportunity {self.opportunity_id!r} missing source_evidence. "
                "Opportunities without provenance are not permitted."
            )


# ---------------------------------------------------------------------------
# Opportunity Detector
# ---------------------------------------------------------------------------

# Minimum confidence to surface an opportunity
_MIN_CONFIDENCE = 0.5

# Maximum priority score (lower wins) before we consider low-value work
_LOW_VALUE_PRIORITY_FLOOR = 80


class OpportunityDetector:
    """Deterministic scanner over CompanySnapshot + shadow programme state.

    Produces a ranked list of Opportunities sorted by priority_score (asc).
    Returns an empty list when the system is healthy — NO_ACTION is valid.
    """

    def __init__(
        self,
        *,
        min_confidence: float = _MIN_CONFIDENCE,
        include_low_value: bool = False,
    ) -> None:
        self.min_confidence = min_confidence
        self.include_low_value = include_low_value

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def scan(
        self,
        snapshot: Any,                       # CompanySnapshot or CompanySnapshotV2
        programme_state: dict[str, Any] | None = None,
    ) -> list[Opportunity]:
        """Scan snapshot and return sorted opportunities. Empty = NO_ACTION."""
        opps: list[Opportunity] = []

        opps.extend(self._scan_blocked_tasks(snapshot))
        opps.extend(self._scan_failed_agent_runs(snapshot))
        opps.extend(self._scan_pending_approvals(snapshot))
        opps.extend(self._scan_programme_failures(programme_state or {}))

        # Filter by confidence threshold
        opps = [o for o in opps if o.confidence >= self.min_confidence]

        # Suppress low-value unless explicitly enabled
        if not self.include_low_value:
            opps = [
                o for o in opps
                if o.value_class != ValueClass.LOW_VALUE_CLEANUP
                   or o.priority_score < _LOW_VALUE_PRIORITY_FLOOR
            ]

        # Sort by priority_score ascending (0 = most urgent)
        return sorted(opps, key=lambda o: (o.priority_score, o.confidence * -1))

    # ------------------------------------------------------------------
    # Scanners — each produces opportunities from one evidence source
    # ------------------------------------------------------------------

    def _scan_blocked_tasks(self, snapshot: Any) -> list[Opportunity]:
        opps = []
        blocked_tasks = getattr(snapshot, "blocked_tasks", ()) or ()
        for task in blocked_tasks:
            task_id = getattr(task, "task_id", "unknown")
            title   = getattr(task, "title", "unknown task")
            project = getattr(task, "project_id", "unknown_project")
            blocked_by = getattr(task, "blocked_by", ())

            if not blocked_by:
                # Blocked without a known reason — defer
                continue

            evidence = (
                f"Task {task_id!r} ({title!r}) in project {project!r} "
                f"is BLOCKED_BY: {list(blocked_by)}"
            )
            opps.append(Opportunity(
                opportunity_id=f"opp-blocked-{task_id}",
                source_project=project,
                source_evidence=evidence,
                provenance_class=ProvenanceClass.KNOWN_BLOCKER,
                problem_statement=f"Task '{title}' is blocked on {list(blocked_by)}.",
                value_class=ValueClass.RELEASE_BLOCKER,
                risk_class=RiskClass.R1,
                priority_score=10,
                confidence=0.9,
                attention_level=AttentionLevel.ACTION_SOON,
                recommended_specialists=("engineering", "qa"),
                owner_approval_required=False,
                raw_evidence={"task_id": task_id, "blocked_by": list(blocked_by)},
            ))
        return opps

    def _scan_failed_agent_runs(self, snapshot: Any) -> list[Opportunity]:
        opps = []
        failed_runs = getattr(snapshot, "failed_agent_runs", ()) or ()
        for run in failed_runs:
            run_id   = getattr(run, "run_id", "unknown")
            agent_id = getattr(run, "agent_id", "unknown_agent")
            blocker  = getattr(run, "blocker", "")

            evidence = (
                f"Agent run {run_id!r} ({agent_id!r}) recorded as FAILED. "
                f"Blocker: {blocker or 'unspecified'}"
            )
            opps.append(Opportunity(
                opportunity_id=f"opp-failed-run-{run_id}",
                source_project=agent_id,
                source_evidence=evidence,
                provenance_class=ProvenanceClass.STALLED_RUN,
                problem_statement=f"Agent '{agent_id}' run failed. Blocker: {blocker or 'unknown'}.",
                value_class=ValueClass.REGRESSION_FIX,
                risk_class=RiskClass.R1,
                priority_score=20,
                confidence=0.85,
                attention_level=AttentionLevel.ACTION_SOON,
                recommended_specialists=("qa", "engineering"),
                owner_approval_required=False,
                raw_evidence={"run_id": run_id, "blocker": blocker},
            ))
        return opps

    def _scan_pending_approvals(self, snapshot: Any) -> list[Opportunity]:
        opps = []
        pending = getattr(snapshot, "pending_approvals", ()) or ()
        for approval in pending:
            a_id     = getattr(approval, "approval_id", "unknown")
            summary  = getattr(approval, "summary", "pending approval")
            cap_id   = getattr(approval, "capability_id", "unknown")

            evidence = (
                f"Pending approval {a_id!r} for capability {cap_id!r}: {summary!r}"
            )
            opps.append(Opportunity(
                opportunity_id=f"opp-pending-approval-{a_id}",
                source_project=cap_id,
                source_evidence=evidence,
                provenance_class=ProvenanceClass.CANDIDATE_PENDING,
                problem_statement=f"Integration candidate awaiting review: {summary}",
                value_class=ValueClass.PRODUCT_IMPROVEMENT,
                risk_class=RiskClass.R0,
                priority_score=30,
                confidence=1.0,
                attention_level=AttentionLevel.APPROVAL_REQUIRED,
                recommended_specialists=("product",),
                owner_approval_required=True,
                raw_evidence={"approval_id": a_id, "capability_id": cap_id},
            ))
        return opps

    def _scan_programme_failures(self, programme_state: dict[str, Any]) -> list[Opportunity]:
        """Scan V2-E CompanySnapshotV2-style programme dict for failures."""
        opps = []
        for p_id, p in programme_state.items():
            status = getattr(p, "status", None)
            if status is None:
                status = p.get("status", "") if isinstance(p, dict) else ""

            status_str = str(status).upper()

            if "FAIL" in status_str:
                display = getattr(p, "display_name", p_id)
                summary = getattr(p, "latest_report_summary", "")
                evidence = (
                    f"Programme {p_id!r} ({display!r}) status=FAIL. "
                    f"Summary: {summary or 'no summary available'}"
                )
                opps.append(Opportunity(
                    opportunity_id=f"opp-prog-fail-{p_id}",
                    source_project=p_id,
                    source_evidence=evidence,
                    provenance_class=ProvenanceClass.FAILING_TEST,
                    problem_statement=f"Programme '{display}' is in FAIL state.",
                    value_class=ValueClass.REGRESSION_FIX,
                    risk_class=RiskClass.R2,
                    priority_score=15,
                    confidence=0.95,
                    attention_level=AttentionLevel.ACTION_SOON,
                    recommended_specialists=("qa", "engineering"),
                    owner_approval_required=False,
                    raw_evidence={"programme_id": p_id, "summary": summary},
                ))
        return opps

    # ------------------------------------------------------------------
    # No-action decision
    # ------------------------------------------------------------------

    @staticmethod
    def decide(opportunities: list[Opportunity]) -> LoopDecision:
        """Convert opportunity list to a LoopDecision."""
        if not opportunities:
            return LoopDecision.NO_ACTION
        top = opportunities[0]
        if top.attention_level == AttentionLevel.CRITICAL:
            return LoopDecision.ESCALATE
        if top.attention_level == AttentionLevel.APPROVAL_REQUIRED:
            return LoopDecision.ESCALATE
        if top.owner_approval_required:
            return LoopDecision.ESCALATE
        return LoopDecision.EXECUTE


__all__ = [
    "ProvenanceClass",
    "Opportunity",
    "OpportunityDetector",
]
