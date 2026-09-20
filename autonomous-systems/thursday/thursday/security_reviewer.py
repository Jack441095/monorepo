"""Security specialist with hard veto authority for Thursday V2-H.

The security specialist is invoked whenever:
  - A changed file matches a policy-critical pattern
  - The plan's mutation boundaries include security-sensitive paths
  - The QA report flags POLICY_FILE_CHANGED

A security VETO blocks integration unconditionally — it overrides any
QA PASS and cannot be averaged or overruled by the producing specialist.

Security-critical paths
-----------------------
Any change to the following modules triggers mandatory security review:

  thursday/approval_policy.py       approval semantics
  thursday/lease_policy.py          lease authority
  thursday/shared_executor.py       shared mutation execution
  thursday/integration_models.py    token/plan contracts
  thursday/plan_approval.py         batch approval machinery
  thursday/confirmation.py          HMAC confirmation tokens
  thursday/action_receipts.py       exactly-once receipt store
  thursday/sandbox.py               process isolation
  thursday/sandbox_runner.py        command safety filter
  thursday/independent_qa.py        QA authority (this file)
  thursday/security_reviewer.py     security authority (self-protection)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from thursday.engineering_contracts import TaskEvidence


# ---------------------------------------------------------------------------
# Security-critical file patterns
# ---------------------------------------------------------------------------

# Any path matching one of these patterns triggers mandatory review.
_SECURITY_CRITICAL_PATTERNS: list[str] = [
    r"thursday/approval_policy",
    r"thursday/lease_policy",
    r"thursday/shared_executor",
    r"thursday/integration_models",
    r"thursday/plan_approval",
    r"thursday/confirmation",
    r"thursday/action_receipts",
    r"thursday/sandbox\.py",
    r"thursday/sandbox_runner",
    r"thursday/independent_qa",
    r"thursday/security_reviewer",
    r"thursday/engineering_contracts",   # changes to core contracts need review
]

_COMPILED: list[re.Pattern[str]] = [re.compile(p) for p in _SECURITY_CRITICAL_PATTERNS]


def _is_security_critical(path: str) -> bool:
    for pat in _COMPILED:
        if pat.search(path.replace("\\", "/")):
            return True
    return False


# ---------------------------------------------------------------------------
# Security verdict
# ---------------------------------------------------------------------------

class SecurityVerdict(str, Enum):
    APPROVED = "APPROVED"
    VETO     = "VETO"


@dataclass
class SecurityReport:
    verdict:           SecurityVerdict
    critical_files:    list[str] = field(default_factory=list)
    veto_reasons:      list[str] = field(default_factory=list)
    findings:          list[str] = field(default_factory=list)

    @property
    def integration_permitted(self) -> bool:
        return self.verdict == SecurityVerdict.APPROVED


# ---------------------------------------------------------------------------
# SecurityReviewer
# ---------------------------------------------------------------------------

class SecurityReviewer:
    """Deterministic security authority.

    Inspects changed files and evidence for policy-critical mutations.
    Emits VETO when any security-critical invariant is threatened.

    A security VETO cannot be overridden by the producing specialist,
    cannot be averaged with a QA PASS, and cannot be bypassed by
    elevated urgency claims.
    """

    def review(
        self,
        evidence: TaskEvidence,
        *,
        qa_findings: list[str] | None = None,
        plan_mutation_boundaries: tuple[str, ...] = (),
    ) -> SecurityReport:
        """Review evidence for security-critical violations.

        Returns SecurityReport. If verdict is VETO, integration is blocked.
        """
        veto_reasons: list[str] = []
        findings: list[str] = []
        critical_files: list[str] = []

        # ---- Check 1: Security-critical file changes ----
        for f in evidence.changed_files:
            if _is_security_critical(f):
                critical_files.append(f)

        if critical_files:
            veto_reasons.append(
                f"SECURITY_VETO: {len(critical_files)} security-critical file(s) modified: "
                f"{critical_files}. These changes require explicit security specialist approval "
                "before integration can proceed."
            )

        # ---- Check 2: Policy-critical files in mutation boundaries ----
        for boundary in plan_mutation_boundaries:
            if _is_security_critical(boundary):
                findings.append(
                    f"SECURITY_NOTE: Mutation boundary {boundary!r} covers "
                    "security-critical paths. Elevated scrutiny applied."
                )

        # ---- Check 3: Secret leakage in evidence ----
        if not evidence.verified and evidence.candidate_sha == "":
            findings.append(
                "SECURITY_NOTE: Evidence is UNVERIFIED with no candidate SHA. "
                "Possible fake receipt attack."
            )

        # ---- Check 4: QA findings referencing policy files ----
        for finding in (qa_findings or []):
            if "POLICY_FILE_CHANGED" in finding:
                veto_reasons.append(
                    f"SECURITY_VETO: QA flagged policy file change: {finding}"
                )

        # ---- Check 5: Self-modification path ----
        thursday_changes = [f for f in evidence.changed_files if "thursday/" in f.lower()]
        if thursday_changes and not critical_files:
            findings.append(
                f"SECURITY_NOTE: Thursday self-modification detected ({len(thursday_changes)} file(s)). "
                "Elevated review applied. Isolated development only — shared Thursday mutation "
                "requires owner approval via V2-G."
            )

        verdict = SecurityVerdict.VETO if veto_reasons else SecurityVerdict.APPROVED
        return SecurityReport(
            verdict=verdict,
            critical_files=critical_files,
            veto_reasons=veto_reasons,
            findings=findings,
        )

    @staticmethod
    def is_security_critical(path: str) -> bool:
        """Public helper — True if path matches any security-critical pattern."""
        return _is_security_critical(path)


__all__ = [
    "SecurityVerdict",
    "SecurityReport",
    "SecurityReviewer",
]
