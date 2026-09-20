"""Engineering loop contracts for Thursday V2-H.

Defines all immutable data types used across the controlled autonomous
engineering loop: value classes, risk classes, attention levels, work
proposals, execution plans, task evidence, loop decisions, and candidate
lineage.

Design principles
-----------------
* Every struct exposed to the approval boundary is frozen and hashed.
* No LLM output is trusted for permissions, ownership, SHA, eligibility,
  or company truth — those are deterministic fields computed here.
* Candidate lineage is append-only; history is never overwritten.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ValueClass(str, Enum):
    CRITICAL_FIX            = "CRITICAL_FIX"
    RELEASE_BLOCKER         = "RELEASE_BLOCKER"
    REGRESSION_FIX          = "REGRESSION_FIX"
    SAFETY_FIX              = "SAFETY_FIX"
    PERFORMANCE_FIX         = "PERFORMANCE_FIX"
    QUALIFICATION_GAP       = "QUALIFICATION_GAP"
    PRODUCT_IMPROVEMENT     = "PRODUCT_IMPROVEMENT"
    DOCUMENTATION_CORRECTION = "DOCUMENTATION_CORRECTION"
    RESEARCH                = "RESEARCH"
    LOW_VALUE_CLEANUP       = "LOW_VALUE_CLEANUP"


class RiskClass(str, Enum):
    R0 = "R0"   # read-only
    R1 = "R1"   # isolated temporary artifact
    R2 = "R2"   # isolated code modification
    R3 = "R3"   # shared development branch mutation
    R4 = "R4"   # protected/release mutation — blocked unless explicitly authorised
    R5 = "R5"   # external/customer/business action — blocked in V2-H


# R4/R5 are structurally blocked in V2-H
BLOCKED_RISK_CLASSES: frozenset[RiskClass] = frozenset({RiskClass.R4, RiskClass.R5})


class AttentionLevel(str, Enum):
    FYI              = "FYI"
    ACTION_SOON      = "ACTION_SOON"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    BLOCKED          = "BLOCKED"
    CRITICAL         = "CRITICAL"


class LoopDecision(str, Enum):
    EXECUTE    = "EXECUTE"
    DEFER      = "DEFER"
    BLOCKED    = "BLOCKED"
    NO_ACTION  = "NO_ACTION"
    ESCALATE   = "ESCALATE"


class ResourceClass(str, Enum):
    LIGHT  = "LIGHT"
    MEDIUM = "MEDIUM"
    HEAVY  = "HEAVY"


# ---------------------------------------------------------------------------
# WorkProposal
# ---------------------------------------------------------------------------

def _canonical_json(obj: Any) -> bytes:
    """Deterministic canonical JSON serialisation (sorted keys, compact)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


@dataclass(frozen=True)
class WorkProposal:
    """Immutable, hashed work proposal.

    Every proposal must answer WHY THIS WORK SHOULD EXIST via
    ``source_evidence`` (provenance is mandatory — no evidence → proposal
    is invalid).

    ``proposal_hash`` is computed over all semantic fields so any post-
    creation modification is detectable.
    """
    proposal_id:            str
    created_at:             float
    source_project:         str
    source_evidence:        str           # Non-empty provenance required
    problem_statement:      str
    expected_value:         str
    priority:               int           # 0 = highest
    confidence:             float         # 0.0–1.0
    risk_class:             RiskClass
    value_class:            ValueClass
    required_specialists:   tuple[str, ...]
    estimated_resource_class: ResourceClass
    mutation_scope:         tuple[str, ...]   # Allowed path prefixes
    protected_targets:      tuple[str, ...]   # Never-touch paths
    acceptance_criteria:    tuple[str, ...]
    stop_conditions:        tuple[str, ...]
    owner_approval_required: bool
    proposal_hash:          str = ""

    def __post_init__(self) -> None:
        if not self.source_evidence.strip():
            raise ValueError(
                f"WorkProposal {self.proposal_id!r} has empty source_evidence. "
                "Every proposal must have deterministic provenance."
            )
        if self.risk_class in BLOCKED_RISK_CLASSES:
            raise ValueError(
                f"WorkProposal {self.proposal_id!r} has risk_class={self.risk_class!r} "
                "which is structurally blocked in V2-H."
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be 0.0–1.0, got {self.confidence}")

    def _semantic_payload(self) -> dict[str, Any]:
        return {
            "proposal_id":           self.proposal_id,
            "source_project":        self.source_project,
            "source_evidence":       self.source_evidence,
            "problem_statement":     self.problem_statement,
            "expected_value":        self.expected_value,
            "priority":              self.priority,
            "confidence":            self.confidence,
            "risk_class":            self.risk_class.value,
            "value_class":           self.value_class.value,
            "required_specialists":  sorted(self.required_specialists),
            "estimated_resource_class": self.estimated_resource_class.value,
            "mutation_scope":        sorted(self.mutation_scope),
            "protected_targets":     sorted(self.protected_targets),
            "acceptance_criteria":   list(self.acceptance_criteria),
            "stop_conditions":       list(self.stop_conditions),
            "owner_approval_required": self.owner_approval_required,
        }

    def compute_hash(self) -> str:
        return hashlib.sha256(_canonical_json(self._semantic_payload())).hexdigest()


def seal_proposal(
    *,
    source_project: str,
    source_evidence: str,
    problem_statement: str,
    expected_value: str,
    priority: int,
    confidence: float,
    risk_class: RiskClass,
    value_class: ValueClass,
    required_specialists: tuple[str, ...],
    estimated_resource_class: ResourceClass = ResourceClass.MEDIUM,
    mutation_scope: tuple[str, ...] = (),
    protected_targets: tuple[str, ...] = (),
    acceptance_criteria: tuple[str, ...] = (),
    stop_conditions: tuple[str, ...] = (),
    owner_approval_required: bool = True,
) -> WorkProposal:
    """Construct a sealed, hashed WorkProposal."""
    import dataclasses
    proposal_id = str(uuid.uuid4())
    partial = WorkProposal(
        proposal_id=proposal_id,
        created_at=time.time(),
        source_project=source_project,
        source_evidence=source_evidence,
        problem_statement=problem_statement,
        expected_value=expected_value,
        priority=priority,
        confidence=confidence,
        risk_class=risk_class,
        value_class=value_class,
        required_specialists=required_specialists,
        estimated_resource_class=estimated_resource_class,
        mutation_scope=mutation_scope,
        protected_targets=protected_targets,
        acceptance_criteria=acceptance_criteria,
        stop_conditions=stop_conditions,
        owner_approval_required=owner_approval_required,
        proposal_hash="",
    )
    return dataclasses.replace(partial, proposal_hash=partial.compute_hash())


# ---------------------------------------------------------------------------
# ExecutionPlan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskNode:
    """Single node in the specialist task DAG."""
    node_id:     str
    specialist:  str
    objective:   str
    depends_on:  tuple[str, ...]   # node_ids this node waits for
    resource_class: ResourceClass = ResourceClass.LIGHT


@dataclass(frozen=True)
class ExecutionPlan:
    """Frozen, hashed execution plan bound to a WorkProposal.

    Execution must bind to ``plan_hash`` — any modification detected via
    hash comparison aborts the run.
    """
    plan_id:             str
    proposal_id:         str
    goal:                str
    source_evidence:     str
    task_dag:            tuple[TaskNode, ...]
    specialists:         tuple[str, ...]
    resource_budgets:    dict[str, int]        # specialist → max concurrent
    expected_outputs:    tuple[str, ...]
    tests:               tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    rollback_cleanup:    tuple[str, ...]
    mutation_boundaries: tuple[str, ...]       # Allowed path prefixes
    approval_boundaries: tuple[str, ...]       # Paths needing token
    created_at:          float
    plan_hash:           str = ""

    def _semantic_payload(self) -> dict[str, Any]:
        return {
            "plan_id":           self.plan_id,
            "proposal_id":       self.proposal_id,
            "goal":              self.goal,
            "source_evidence":   self.source_evidence,
            "task_dag":          [
                {"node_id": n.node_id, "specialist": n.specialist,
                 "objective": n.objective, "depends_on": sorted(n.depends_on),
                 "resource_class": n.resource_class.value}
                for n in self.task_dag
            ],
            "specialists":       sorted(self.specialists),
            "resource_budgets":  {k: v for k, v in sorted(self.resource_budgets.items())},
            "expected_outputs":  list(self.expected_outputs),
            "tests":             list(self.tests),
            "acceptance_criteria": list(self.acceptance_criteria),
            "rollback_cleanup":  list(self.rollback_cleanup),
            "mutation_boundaries": sorted(self.mutation_boundaries),
            "approval_boundaries": sorted(self.approval_boundaries),
        }

    def compute_hash(self) -> str:
        return hashlib.sha256(_canonical_json(self._semantic_payload())).hexdigest()


def seal_execution_plan(
    proposal: WorkProposal,
    goal: str,
    task_dag: tuple[TaskNode, ...],
    *,
    expected_outputs: tuple[str, ...] = (),
    tests: tuple[str, ...] = (),
    acceptance_criteria: tuple[str, ...] = (),
    rollback_cleanup: tuple[str, ...] = (),
    mutation_boundaries: tuple[str, ...] = (),
    approval_boundaries: tuple[str, ...] = (),
    resource_budgets: dict[str, int] | None = None,
) -> ExecutionPlan:
    """Construct and seal an ExecutionPlan from a WorkProposal."""
    import dataclasses
    specialists = tuple(sorted({n.specialist for n in task_dag}))
    plan_id = str(uuid.uuid4())
    partial = ExecutionPlan(
        plan_id=plan_id,
        proposal_id=proposal.proposal_id,
        goal=goal,
        source_evidence=proposal.source_evidence,
        task_dag=task_dag,
        specialists=specialists,
        resource_budgets=resource_budgets or {},
        expected_outputs=expected_outputs,
        tests=tests,
        acceptance_criteria=acceptance_criteria or proposal.acceptance_criteria,
        rollback_cleanup=rollback_cleanup,
        mutation_boundaries=mutation_boundaries or proposal.mutation_scope,
        approval_boundaries=approval_boundaries,
        created_at=time.time(),
        plan_hash="",
    )
    return dataclasses.replace(partial, plan_hash=partial.compute_hash())


# ---------------------------------------------------------------------------
# TaskEvidence
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskEvidence:
    """Machine-verifiable evidence for a completed specialist task.

    Claims without corresponding evidence remain UNVERIFIED.
    """
    task_id:          str
    verified:         bool            # True only when all required fields present
    candidate_sha:    str = ""
    diff_hash:        str = ""
    test_command:     tuple[str, ...] = ()
    test_exit_code:   int = -1
    test_count:       int = -1        # -1 = not measured
    benchmark_result: dict[str, Any] = field(default_factory=dict)
    artifact_hash:    str = ""
    source_provenance: str = ""
    resource_usage:   dict[str, Any] = field(default_factory=dict)
    changed_files:    tuple[str, ...] = ()

    def verify_claim(self, claimed_sha: str, claimed_exit_code: int) -> tuple[bool, str]:
        """Check that evidence matches the producing specialist's claims."""
        if not self.verified:
            return False, "Evidence is marked UNVERIFIED — claims cannot be trusted."
        if self.candidate_sha != claimed_sha:
            return False, (
                f"SHA mismatch: evidence has {self.candidate_sha[:12]}…, "
                f"claimed {claimed_sha[:12]}…"
            )
        if self.test_exit_code != claimed_exit_code:
            return False, (
                f"Exit code mismatch: evidence {self.test_exit_code}, "
                f"claimed {claimed_exit_code}"
            )
        return True, ""


# ---------------------------------------------------------------------------
# CandidateLineage
# ---------------------------------------------------------------------------

@dataclass
class LineageEvent:
    """Single append-only event in a candidate's lifecycle."""
    event_id:    str
    timestamp:   float
    event_type:  str   # PROPOSAL, PLAN, EXECUTION, QA, SECURITY_REVIEW,
                       # CANDIDATE, APPROVAL_REQUEST, APPROVAL, REJECTION,
                       # REQUEST_CHANGES, INTEGRATION, ROLLBACK, COMPLETED
    summary:     str
    payload:     dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateLineage:
    """Append-only audit chain from proposal to final state.

    History is never overwritten; each generation (request-changes →
    new plan/candidate) appends rather than replaces.
    """
    lineage_id:     str
    proposal_id:    str
    events:         list[LineageEvent] = field(default_factory=list)
    generation:     int = 0           # increments on REQUEST_CHANGES
    final_state:    str = "OPEN"      # OPEN, INTEGRATED, REJECTED, ABANDONED

    def append(self, event_type: str, summary: str, payload: dict[str, Any] | None = None) -> None:
        self.events.append(LineageEvent(
            event_id=str(uuid.uuid4()),
            timestamp=time.time(),
            event_type=event_type,
            summary=summary,
            payload=payload or {},
        ))

    def request_changes(self, reason: str) -> None:
        self.generation += 1
        self.append("REQUEST_CHANGES", reason, {"generation": self.generation})

    def close(self, final_state: str, reason: str) -> None:
        if self.final_state != "OPEN":
            return  # Already closed — no double-closing
        self.final_state = final_state
        self.append(final_state, reason)


def new_lineage(proposal: WorkProposal) -> CandidateLineage:
    lineage = CandidateLineage(
        lineage_id=str(uuid.uuid4()),
        proposal_id=proposal.proposal_id,
    )
    lineage.append("PROPOSAL", f"Proposal {proposal.proposal_id[:8]} created.",
                   {"proposal_hash": proposal.proposal_hash, "value_class": proposal.value_class.value})
    return lineage


__all__ = [
    "ValueClass", "RiskClass", "AttentionLevel", "LoopDecision", "ResourceClass",
    "BLOCKED_RISK_CLASSES",
    "WorkProposal", "seal_proposal",
    "TaskNode", "ExecutionPlan", "seal_execution_plan",
    "TaskEvidence",
    "LineageEvent", "CandidateLineage", "new_lineage",
]
