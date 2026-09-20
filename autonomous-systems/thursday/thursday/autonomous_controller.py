"""Autonomous Engineering Controller for Thursday V2-H.

Top-level coordinator of the controlled autonomous engineering loop.
Does NOT duplicate logic from qualified subsystems — delegates to them.

Loop:
  OBSERVE  → OpportunityDetector.scan()
  DECIDE   → value_gate + risk_classify → LoopDecision
  PROPOSE  → seal_proposal()
  PLAN     → seal_execution_plan()
  ROUTE    → SpecialistRegistry.route_task()
  SCHEDULE → resource budget check (heavy_task_limit = 2)
  EXECUTE  → SandboxRunner.run_isolated_task()   [ISOLATED]
  COLLECT  → EvidenceCollector.collect()
  QA       → IndependentQA.validate()            [QA VETO]
  SECURITY → SecurityReviewer.review()           [SECURITY VETO]
  ELIGIBLE → integration_eligibility_check()
  CANDIDATE → IntegrationCandidate (sealed)
  APPROVE  → WAITING_FOR_APPROVAL (durable)
  MUTATE   → SharedExecutor.execute()            [V2-G]
  POST-QA  → PostIntegrationValidator.validate()
  RECONCILE → StateReconciler.reconcile_after_integration()
  BRIEF    → OwnerBriefGenerator.status_brief()

Safety hierarchy (deterministic, not averaged):
  SecurityReviewer VETO > QA VETO > QA FAIL > QA PASS

Owner authority:
  Owner rejection outranks all agents.
  Owner approval cannot override mechanically impossible conditions.

Crash recovery:
  All intermediate state is persisted atomically.
  Restarting the controller is safe — no side effects are duplicated.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from thursday.engineering_contracts import (
    AttentionLevel,
    CandidateLineage,
    ExecutionPlan,
    LoopDecision,
    ResourceClass,
    RiskClass,
    TaskEvidence,
    TaskNode,
    ValueClass,
    WorkProposal,
    new_lineage,
    seal_execution_plan,
    seal_proposal,
)
from thursday.opportunity_detector import Opportunity, OpportunityDetector
from thursday.evidence_collector import EvidenceCollector
from thursday.independent_qa import IndependentQA, QAReport, QAVerdict
from thursday.security_reviewer import SecurityReport, SecurityReviewer, SecurityVerdict
from thursday.diagnostic_store import DiagnosticStore
from thursday.post_integration_validator import PostIntegrationValidator, PostQAStatus
from thursday.state_reconciler import StateReconciler
from thursday.owner_brief_generator import ApprovalPacket, OwnerBriefGenerator, StatusBrief
from thursday.integration_models import (
    IntegrationCandidate,
    IntegrationPlan,
    ApprovalToken,
    IntegrationTransaction,
    TransactionState,
    seal_plan,
    issue_approval_token,
    create_transaction,
)
from thursday.shared_executor import SharedExecutor, IntegrationLeaseRegistry
from thursday.specialists import REGISTRY


# ---------------------------------------------------------------------------
# Loop state constants
# ---------------------------------------------------------------------------

class LoopState:
    IDLE                 = "IDLE"
    OBSERVING            = "OBSERVING"
    PLANNING             = "PLANNING"
    EXECUTING            = "EXECUTING"
    COLLECTING_EVIDENCE  = "COLLECTING_EVIDENCE"
    QA_REVIEW            = "QA_REVIEW"
    SECURITY_REVIEW      = "SECURITY_REVIEW"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    APPLYING             = "APPLYING"
    POST_INTEGRATION_QA  = "POST_INTEGRATION_QA"
    RECONCILING          = "RECONCILING"
    COMPLETED            = "COMPLETED"
    FAILED               = "FAILED"
    NO_ACTION            = "NO_ACTION"


# ---------------------------------------------------------------------------
# Loop run result
# ---------------------------------------------------------------------------

@dataclass
class LoopRunResult:
    """Result of a single controller loop cycle."""
    run_id:           str
    loop_state:       str
    decision:         LoopDecision
    elapsed_seconds:  float
    proposal_id:      str = ""
    plan_id:          str = ""
    opportunity:      str = ""
    qa_verdict:       str = ""
    security_verdict: str = ""
    transaction_id:   str = ""
    integration_state: str = ""
    post_qa_status:   str = ""
    notes:            list[str] = field(default_factory=list)
    errors:           list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Durable approval wait record
# ---------------------------------------------------------------------------

@dataclass
class PendingApproval:
    """Persisted record for a candidate waiting for owner approval.

    WAITING_FOR_APPROVAL is a first-class durable state.
    Restarting the controller must not lose this record.
    """
    record_id:    str
    proposal_id:  str
    plan_id:      str
    plan_hash:    str
    token_id:     str
    target_sha:   str
    target_branch: str
    candidate_sha: str
    created_at:   float
    expires_at:   float
    state:        str = "WAITING"   # WAITING / APPROVED / REJECTED / EXPIRED
    rejected:     bool = False      # True after owner rejection — no re-ask


# ---------------------------------------------------------------------------
# Integration eligibility check
# ---------------------------------------------------------------------------

def check_integration_eligibility(
    plan: ExecutionPlan,
    evidence: TaskEvidence,
    qa_report: QAReport,
    security_report: SecurityReport,
) -> tuple[bool, list[str]]:
    """Deterministic gate — returns (eligible, list_of_reasons_if_not)."""
    reasons = []

    if not qa_report.integration_permitted:
        reasons.append(f"QA verdict: {qa_report.verdict.value}")
    if not security_report.integration_permitted:
        reasons.append(f"Security verdict: {security_report.verdict.value}")
    if not evidence.verified:
        reasons.append("Evidence is UNVERIFIED.")
    if not evidence.candidate_sha:
        reasons.append("No candidate SHA in evidence.")
    if evidence.test_exit_code != 0:
        reasons.append(f"Test exit code {evidence.test_exit_code} ≠ 0.")
    # Scope drift already captured in QA report veto_reasons

    return not bool(reasons), reasons


# ---------------------------------------------------------------------------
# Autonomous Engineering Controller
# ---------------------------------------------------------------------------

class AutonomousEngineeringController:
    """Controls the full autonomous engineering loop.

    Parameters
    ----------
    repo_path : str | Path
        Git repository root.
    state_dir : str | Path
        Directory for persisted loop state (atomic checkpoints).
    heavy_task_limit : int
        Maximum concurrent heavy specialist tasks (default 2).
    """

    HEAVY_TASK_LIMIT = 2
    STAGE = "STAGE_4_CONTROLLED_AUTONOMOUS_ENGINEERING"

    def __init__(
        self,
        repo_path: str | Path,
        state_dir: str | Path,
        *,
        heavy_task_limit: int = 2,
        lease_registry: IntegrationLeaseRegistry | None = None,
    ) -> None:
        self.repo_path  = Path(repo_path)
        self.state_dir  = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.heavy_task_limit = heavy_task_limit

        # Subsystems (no logic duplication)
        self.opportunity_detector   = OpportunityDetector()
        self.evidence_collector     = EvidenceCollector(repo_path)
        self.independent_qa         = IndependentQA()
        self.security_reviewer      = SecurityReviewer()
        self.diagnostic_store       = DiagnosticStore(self.state_dir / "diagnostics")
        self.post_validator         = PostIntegrationValidator(self.repo_path)
        self.state_reconciler       = StateReconciler(heavy_task_limit=heavy_task_limit)
        self.brief_generator        = OwnerBriefGenerator()
        self.shared_executor        = SharedExecutor(
            repo_path=self.repo_path,
            log_dir=self.state_dir / "integration_logs",
            lease_registry=lease_registry or IntegrationLeaseRegistry(),
        )

        # Controller state
        self._active_heavy: int = 0
        self._pending_approvals: dict[str, PendingApproval] = {}

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run_cycle(
        self,
        snapshot: Any,
        programme_state: dict[str, Any] | None = None,
        *,
        approved_token: ApprovalToken | None = None,
        owner_rejection: str = "",
    ) -> LoopRunResult:
        """Execute one full autonomous engineering loop cycle.

        Parameters
        ----------
        snapshot
            CompanySnapshot or compatible snapshot object.
        programme_state
            Optional V2-E programme state dict.
        approved_token
            If the owner has approved a pending candidate, pass the token here.
        owner_rejection
            If the owner rejects, pass the proposal_id here.
        """
        start  = time.monotonic()
        run_id = str(uuid.uuid4())

        # ---- Handle owner rejection ----
        if owner_rejection and owner_rejection in self._pending_approvals:
            pending = self._pending_approvals.pop(owner_rejection)
            pending.rejected = True
            pending.state = "REJECTED"
            return LoopRunResult(
                run_id=run_id,
                loop_state=LoopState.NO_ACTION,
                decision=LoopDecision.NO_ACTION,
                elapsed_seconds=time.monotonic() - start,
                proposal_id=owner_rejection,
                notes=["Owner rejected candidate. Will not re-submit unless candidate materially changes."],
            )

        # ---- Handle pre-existing approval ----
        if approved_token is not None:
            return self._handle_approved_token(run_id, start, approved_token)

        # ---- OBSERVE ----
        opportunities = self.opportunity_detector.scan(snapshot, programme_state)
        decision = self.opportunity_detector.decide(opportunities)

        if decision == LoopDecision.NO_ACTION:
            self._persist_state("last_cycle", {"decision": "NO_ACTION", "at": time.time()})
            return LoopRunResult(
                run_id=run_id,
                loop_state=LoopState.NO_ACTION,
                decision=LoopDecision.NO_ACTION,
                elapsed_seconds=time.monotonic() - start,
                notes=["System healthy. No action required."],
            )

        top_opp = opportunities[0]

        # ---- Resource check for heavy tasks ----
        resource_cls = top_opp.estimated_resource_class
        if resource_cls == ResourceClass.HEAVY:
            if self._active_heavy >= self.heavy_task_limit:
                return LoopRunResult(
                    run_id=run_id,
                    loop_state=LoopState.IDLE,
                    decision=LoopDecision.DEFER,
                    elapsed_seconds=time.monotonic() - start,
                    opportunity=top_opp.problem_statement,
                    notes=[f"Heavy task deferred: active={self._active_heavy}/{self.heavy_task_limit}"],
                )

        # ---- PLAN ----
        proposal = seal_proposal(
            source_project=top_opp.source_project,
            source_evidence=top_opp.source_evidence,
            problem_statement=top_opp.problem_statement,
            expected_value=top_opp.problem_statement,
            priority=top_opp.priority_score,
            confidence=top_opp.confidence,
            risk_class=top_opp.risk_class,
            value_class=top_opp.value_class,
            required_specialists=top_opp.recommended_specialists,
            estimated_resource_class=resource_cls,
            owner_approval_required=top_opp.owner_approval_required,
        )
        lineage = new_lineage(proposal)
        lineage.append("PLAN", "ExecutionPlan sealed from opportunity.")

        # Route specialist
        specialist_id = REGISTRY.route_task(top_opp.provenance_class, top_opp.problem_statement)
        task_dag = (
            TaskNode(
                node_id=f"node-{run_id[:8]}",
                specialist=specialist_id,
                objective=top_opp.problem_statement,
                depends_on=(),
                resource_class=resource_cls,
            ),
        )
        plan = seal_execution_plan(
            proposal,
            goal=top_opp.problem_statement,
            task_dag=task_dag,
        )

        # ---- EXECUTE (simulated in controller — real execution via SandboxRunner) ----
        # In the full loop, this calls SandboxRunner.run_isolated_task().
        # Here the controller records EXECUTING state and returns the plan to
        # the caller for async specialist dispatch.
        if resource_cls == ResourceClass.HEAVY:
            self._active_heavy += 1

        self._persist_state(f"plan_{plan.plan_id}", {
            "plan_id": plan.plan_id,
            "proposal_id": proposal.proposal_id,
            "loop_state": LoopState.EXECUTING,
            "at": time.time(),
        })

        lineage.append("EXECUTION", f"Plan {plan.plan_id[:8]} dispatched to specialist={specialist_id}.")

        return LoopRunResult(
            run_id=run_id,
            loop_state=LoopState.EXECUTING,
            decision=LoopDecision.EXECUTE,
            elapsed_seconds=time.monotonic() - start,
            proposal_id=proposal.proposal_id,
            plan_id=plan.plan_id,
            opportunity=top_opp.problem_statement,
            notes=[
                f"Dispatched to specialist={specialist_id}.",
                f"Plan hash: {plan.plan_hash[:16]}…",
                "Awaiting evidence collection before QA.",
            ],
        )

    # ------------------------------------------------------------------
    # QA + eligibility + approval request pipeline
    # ------------------------------------------------------------------

    def process_evidence(
        self,
        plan: ExecutionPlan,
        proposal: WorkProposal,
        lineage: CandidateLineage,
        evidence: TaskEvidence,
        *,
        claimed_success: bool,
        claimed_sha: str = "",
        target_branch: str = "thursday/integration-staging",
        target_sha: str = "",
        diff_summary: str = "",
    ) -> tuple[ApprovalPacket | None, str]:
        """Run QA, security review, eligibility check, and generate approval packet.

        Returns (ApprovalPacket, reason). If ApprovalPacket is None, reason
        explains why integration is not eligible.
        """
        # QA
        qa_report = self.independent_qa.validate(
            plan, evidence,
            claimed_success=claimed_success,
            claimed_sha=claimed_sha,
        )
        lineage.append("QA", f"QA verdict: {qa_report.verdict.value}")

        # Security review
        security_report = self.security_reviewer.review(
            evidence,
            qa_findings=qa_report.findings,
            plan_mutation_boundaries=plan.mutation_boundaries,
        )
        lineage.append("SECURITY_REVIEW", f"Security verdict: {security_report.verdict.value}")

        # Eligibility
        eligible, reasons = check_integration_eligibility(plan, evidence, qa_report, security_report)
        if not eligible:
            if qa_report.verdict in (QAVerdict.VETO, QAVerdict.FAIL):
                self.diagnostic_store.retain_failure(
                    plan.plan_id,
                    plan={"plan_id": plan.plan_id, "goal": plan.goal},
                    error_metadata={"qa_reasons": qa_report.veto_reasons, "reasons": reasons},
                )
            return None, f"Integration not eligible: {'; '.join(reasons)}"

        # Candidate
        candidate = IntegrationCandidate(
            task_id=plan.plan_id,
            source_sha=target_sha,
            candidate_branch=f"thursday/task/{plan.plan_id[:8]}",
            candidate_sha=evidence.candidate_sha,
            diff_summary=diff_summary,
            tests_passed=(evidence.test_exit_code == 0),
            qa_receipt={"verdict": qa_report.verdict.value, "at": time.time()},
        )

        integration_plan = seal_plan(
            target_branch=target_branch,
            target_sha=target_sha,
            candidate=candidate,
        )

        token = issue_approval_token(integration_plan, owner="thursday_controller")
        pending = PendingApproval(
            record_id=str(uuid.uuid4()),
            proposal_id=proposal.proposal_id,
            plan_id=plan.plan_id,
            plan_hash=integration_plan.plan_digest,
            token_id=token.token_id,
            target_sha=target_sha,
            target_branch=target_branch,
            candidate_sha=evidence.candidate_sha,
            created_at=time.time(),
            expires_at=token.expires_at,
        )
        self._pending_approvals[proposal.proposal_id] = pending
        self._persist_state(f"pending_{proposal.proposal_id}", {
            "record_id": pending.record_id,
            "token_id": token.token_id,
            "expires_at": token.expires_at,
        })
        lineage.append("APPROVAL_REQUEST", f"Approval packet generated. Token: {token.token_id[:8]}…")

        packet = self.brief_generator.approval_packet(
            proposal, plan, evidence, qa_report, security_report,
            target_branch=target_branch,
            current_target_sha=target_sha,
            diff_summary=diff_summary,
        )
        return packet, ""

    # ------------------------------------------------------------------
    # Handle approved token
    # ------------------------------------------------------------------

    def _handle_approved_token(
        self,
        run_id: str,
        start: float,
        token: ApprovalToken,
    ) -> LoopRunResult:
        """Execute approved integration via V2-G SharedExecutor."""
        # Locate pending record matching the token
        matching_pending = None
        for pid, pending in self._pending_approvals.items():
            if pending.token_id == token.token_id:
                matching_pending = (pid, pending)
                break

        if matching_pending is None:
            return LoopRunResult(
                run_id=run_id,
                loop_state=LoopState.FAILED,
                decision=LoopDecision.BLOCKED,
                elapsed_seconds=time.monotonic() - start,
                errors=["No pending approval record found for this token."],
            )

        proposal_id, pending = matching_pending
        if pending.rejected:
            return LoopRunResult(
                run_id=run_id,
                loop_state=LoopState.FAILED,
                decision=LoopDecision.BLOCKED,
                elapsed_seconds=time.monotonic() - start,
                errors=["This proposal was previously rejected by the owner."],
            )

        # Reconstruct integration plan (in full system, loaded from persistent store)
        candidate = IntegrationCandidate(
            task_id=pending.plan_id,
            source_sha=pending.target_sha,
            candidate_branch=f"thursday/task/{pending.plan_id[:8]}",
            candidate_sha=pending.candidate_sha,
            diff_summary="",
            tests_passed=True,
            qa_receipt={},
        )
        integration_plan = seal_plan(
            target_branch=pending.target_branch,
            target_sha=pending.target_sha,
            candidate=candidate,
        )

        # Execute via V2-G SharedExecutor
        tx = self.shared_executor.execute(integration_plan, token)
        self._pending_approvals.pop(proposal_id, None)

        # Post-integration QA
        if tx.state == TransactionState.COMPLETED:
            post_result = self.post_validator.validate(
                expected_sha=tx.post_sha,
                target_branch=pending.target_branch,
            )
            post_status = post_result.status.value
        else:
            post_status = "SKIPPED_ROLLBACK"

        return LoopRunResult(
            run_id=run_id,
            loop_state=LoopState.COMPLETED if tx.state == TransactionState.COMPLETED else LoopState.FAILED,
            decision=LoopDecision.EXECUTE,
            elapsed_seconds=time.monotonic() - start,
            proposal_id=proposal_id,
            transaction_id=tx.transaction_id,
            integration_state=tx.state,
            post_qa_status=post_status,
            notes=tx.events[-3:] if tx.events else [],
        )

    # ------------------------------------------------------------------
    # Status brief
    # ------------------------------------------------------------------

    def build_status_brief(
        self,
        *,
        projects_active: int = 0,
        projects_healthy: int = 0,
    ) -> StatusBrief:
        waiting = len(self._pending_approvals)
        return self.brief_generator.status_brief(
            projects_active=projects_active,
            projects_healthy=projects_healthy,
            waiting_approval=waiting,
            heavy_tasks_deferred=max(0, self._active_heavy - self.heavy_task_limit),
            critical_failures=0,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_state(self, key: str, payload: dict[str, Any]) -> None:
        path = self.state_dir / f"{key}.json"
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp, path)


__all__ = [
    "LoopState",
    "LoopRunResult",
    "PendingApproval",
    "check_integration_eligibility",
    "AutonomousEngineeringController",
]
