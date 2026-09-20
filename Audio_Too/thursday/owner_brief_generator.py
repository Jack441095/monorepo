"""Owner brief generator for Thursday V2-H.

Produces two types of output:

1. approval_packet() — structured dict for a specific integration candidate.
   Contains exactly what the owner needs to make an informed approval decision.
   No unsupported claims. All facts sourced from verified evidence.

2. status_brief() — concise operational summary with AttentionLevel tags.
   Suitable for a daily briefing or dashboard. Never fabricates company state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from thursday.engineering_contracts import (
    AttentionLevel,
    CandidateLineage,
    ExecutionPlan,
    TaskEvidence,
    WorkProposal,
)
from thursday.independent_qa import QAReport, QAVerdict
from thursday.security_reviewer import SecurityReport, SecurityVerdict


# ---------------------------------------------------------------------------
# Approval packet
# ---------------------------------------------------------------------------

@dataclass
class ApprovalPacket:
    """Structured owner approval packet for a single integration candidate.

    The owner should NOT need to read hundreds of lines.
    All fields must be evidence-backed.
    """
    project:          str
    problem:          str
    why_it_matters:   str
    what_changed:     str
    files_changed:    list[str]
    tests_summary:    str
    qa_result:        str
    security_result:  str
    risks:            list[str]
    rollback_plan:    str
    target_branch:    str
    current_target_sha: str
    candidate_sha:    str
    diff_summary:     str
    recommendation:   str
    attention_level:  AttentionLevel
    proposal_id:      str
    plan_id:          str
    plan_hash:        str
    generated_at:     float

    def render_text(self) -> str:
        """Compact human-readable text rendition of the packet."""
        lines = [
            "══════════════════════════════════════════",
            "THURSDAY — INTEGRATION APPROVAL REQUIRED",
            "══════════════════════════════════════════",
            f"PROJECT         : {self.project}",
            f"PROBLEM         : {self.problem}",
            f"WHY IT MATTERS  : {self.why_it_matters}",
            f"WHAT CHANGED    : {self.what_changed}",
            f"FILES CHANGED   : {', '.join(self.files_changed[:10]) or '(none)'}",
            f"TESTS           : {self.tests_summary}",
            f"QA RESULT       : {self.qa_result}",
            f"SECURITY        : {self.security_result}",
            f"RISKS           : {'; '.join(self.risks) or 'none identified'}",
            f"ROLLBACK        : {self.rollback_plan}",
            f"TARGET BRANCH   : {self.target_branch}",
            f"CURRENT SHA     : {self.current_target_sha[:16]}…",
            f"CANDIDATE SHA   : {self.candidate_sha[:16]}…",
            f"DIFF SUMMARY    : {self.diff_summary}",
            "──────────────────────────────────────────",
            f"RECOMMENDATION  : {self.recommendation}",
            f"ATTENTION       : {self.attention_level.value}",
            "",
            "  [ APPROVE ]   [ REJECT ]   [ REQUEST CHANGES ]",
            "",
            f"Plan ID: {self.plan_id}   Plan hash: {self.plan_hash[:16]}…",
            "══════════════════════════════════════════",
        ]
        return "\n".join(lines)


@dataclass
class StatusBrief:
    """Concise operational brief for the owner."""
    generated_at:        float
    projects_active:     int
    projects_healthy:    int
    waiting_approval:    int
    heavy_tasks_deferred: int
    critical_failures:   int
    attention_items:     list[tuple[AttentionLevel, str]] = field(default_factory=list)
    next_auto_action:    str = ""
    notes:               list[str] = field(default_factory=list)

    def render_text(self) -> str:
        lines = [
            "══════════════════════════════════════════",
            "THURSDAY — STATUS BRIEF",
            "══════════════════════════════════════════",
            f"{self.projects_active} projects active",
            f"{self.projects_healthy} healthy",
            f"{self.waiting_approval} waiting for approval",
            f"{self.heavy_tasks_deferred} heavy task(s) deferred (resource limit)",
            f"{self.critical_failures} critical failures",
            "",
        ]
        if self.attention_items:
            lines.append("OWNER ACTION")
            for level, text in self.attention_items:
                lines.append(f"  [{level.value}] {text}")
            lines.append("")
        if self.next_auto_action:
            lines.append(f"NEXT AUTO ACTION: {self.next_auto_action}")
        if self.notes:
            lines.append("")
            for note in self.notes:
                lines.append(f"  • {note}")
        lines.append("══════════════════════════════════════════")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# OwnerBriefGenerator
# ---------------------------------------------------------------------------

class OwnerBriefGenerator:
    """Generates approval packets and status briefs from verified evidence."""

    def approval_packet(
        self,
        proposal: WorkProposal,
        plan: ExecutionPlan,
        evidence: TaskEvidence,
        qa_report: QAReport,
        security_report: SecurityReport,
        *,
        target_branch: str,
        current_target_sha: str,
        diff_summary: str = "",
    ) -> ApprovalPacket:
        """Generate a structured approval packet.

        All facts drawn from verified evidence and plan contracts.
        No unsupported claims.
        """
        # QA result string
        qa_result = f"{qa_report.verdict.value}"
        if qa_report.veto_reasons:
            qa_result += f" — VETO: {qa_report.veto_reasons[0]}"
        elif qa_report.findings:
            qa_result += f" — {qa_report.findings[0]}"

        # Security result string
        sec_result = f"{security_report.verdict.value}"
        if security_report.veto_reasons:
            sec_result += f" — VETO: {security_report.veto_reasons[0]}"
        elif security_report.findings:
            sec_result += f" — {security_report.findings[0]}"

        # Risks
        risks = list(qa_report.veto_reasons) + list(security_report.veto_reasons)
        if not risks and plan.risk_class_str if hasattr(plan, "risk_class_str") else False:
            risks = [f"Risk class: {plan.risk_class_str}"]

        # Recommendation
        if qa_report.verdict == QAVerdict.VETO or security_report.verdict == SecurityVerdict.VETO:
            recommendation = "DO NOT APPROVE — QA or security veto is active."
            attention = AttentionLevel.CRITICAL
        elif qa_report.verdict == QAVerdict.PASS and security_report.verdict == SecurityVerdict.APPROVED:
            recommendation = "Approve to integrate this candidate."
            attention = AttentionLevel.APPROVAL_REQUIRED
        else:
            recommendation = "Review required before approval."
            attention = AttentionLevel.ACTION_SOON

        # Tests summary
        if evidence.test_count >= 0:
            tests_summary = (
                f"{evidence.test_count} tests, exit code {evidence.test_exit_code}. "
                f"Command: {' '.join(evidence.test_command)}"
            )
        else:
            tests_summary = "Test count not measured."

        return ApprovalPacket(
            project=proposal.source_project,
            problem=proposal.problem_statement,
            why_it_matters=proposal.expected_value,
            what_changed=diff_summary or "See diff_summary field.",
            files_changed=list(evidence.changed_files),
            tests_summary=tests_summary,
            qa_result=qa_result,
            security_result=sec_result,
            risks=risks or ["None identified by automated review."],
            rollback_plan=(
                f"V2-G SharedExecutor will git reset --hard to {current_target_sha[:12]}… "
                "if post-integration QA fails. FAILED_SAFE state guaranteed."
            ),
            target_branch=target_branch,
            current_target_sha=current_target_sha,
            candidate_sha=evidence.candidate_sha,
            diff_summary=diff_summary or "(no diff summary provided)",
            recommendation=recommendation,
            attention_level=attention,
            proposal_id=proposal.proposal_id,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            generated_at=time.time(),
        )

    def status_brief(
        self,
        *,
        projects_active: int = 0,
        projects_healthy: int = 0,
        waiting_approval: int = 0,
        heavy_tasks_deferred: int = 0,
        critical_failures: int = 0,
        attention_items: list[tuple[AttentionLevel, str]] | None = None,
        next_auto_action: str = "",
        notes: list[str] | None = None,
    ) -> StatusBrief:
        """Compose a concise status brief from verified inputs only."""
        return StatusBrief(
            generated_at=time.time(),
            projects_active=projects_active,
            projects_healthy=projects_healthy,
            waiting_approval=waiting_approval,
            heavy_tasks_deferred=heavy_tasks_deferred,
            critical_failures=critical_failures,
            attention_items=attention_items or [],
            next_auto_action=next_auto_action,
            notes=notes or [],
        )


__all__ = [
    "ApprovalPacket",
    "StatusBrief",
    "OwnerBriefGenerator",
]
