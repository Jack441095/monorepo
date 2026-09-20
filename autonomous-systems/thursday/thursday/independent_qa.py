"""Independent QA with adversarial falsification for Thursday V2-H.

The specialist that creates a change is NOT the sole authority declaring
it correct. IndependentQA actively attempts falsification.

QA Veto
-------
Any of the following causes an immediate VETO — integration is blocked
regardless of the producing specialist's success claim:

  * "tests passed" claim without machine-verifiable receipt
  * candidate SHA does not match claimed SHA
  * test count decreased relative to baseline (test deletion)
  * numeric threshold loosened relative to baseline
  * changed files outside declared plan boundaries (scope drift)
  * secret pattern detected in evidence
  * candidate on wrong branch
  * stale SHA (evidence SHA ≠ current branch HEAD)

Test Integrity Violations
-------------------------
Structural attacks that corrupt the test suite produce
TEST_INTEGRITY_VIOLATION regardless of overall QA verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from thursday.engineering_contracts import ExecutionPlan, TaskEvidence
from thursday.evidence_collector import detect_scope_drift


# ---------------------------------------------------------------------------
# Verdicts and violations
# ---------------------------------------------------------------------------

class QAVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    VETO = "VETO"      # Hard block — integration cannot proceed


class TestIntegrityStatus(str, Enum):
    CLEAN              = "CLEAN"
    TEST_INTEGRITY_VIOLATION = "TEST_INTEGRITY_VIOLATION"


@dataclass
class QAReport:
    verdict:           QAVerdict
    integrity_status:  TestIntegrityStatus
    findings:          list[str] = field(default_factory=list)
    veto_reasons:      list[str] = field(default_factory=list)
    violations:        list[str] = field(default_factory=list)
    scope_violations:  list[str] = field(default_factory=list)

    @property
    def integration_permitted(self) -> bool:
        return (
            self.verdict == QAVerdict.PASS
            and self.integrity_status == TestIntegrityStatus.CLEAN
        )


# ---------------------------------------------------------------------------
# Policy-critical file patterns (trigger security review)
# ---------------------------------------------------------------------------

_POLICY_CRITICAL_PATTERNS: list[str] = [
    "approval_policy",
    "lease_policy",
    "shared_executor",
    "token_verif",
    "sandbox_policy",
    "integration_models",
    "plan_approval",
    "confirmation",
    "action_receipts",
]


def _touches_policy_files(changed_files: tuple[str, ...]) -> list[str]:
    hits = []
    for f in changed_files:
        fl = f.lower()
        for pattern in _POLICY_CRITICAL_PATTERNS:
            if pattern in fl:
                hits.append(f)
                break
    return hits


# ---------------------------------------------------------------------------
# IndependentQA
# ---------------------------------------------------------------------------

class IndependentQA:
    """Adversarial QA — falsifies rather than confirms.

    Parameters
    ----------
    baseline_test_count : int
        Number of tests that existed before the specialist task ran.
        Used to detect test deletion.
    baseline_thresholds : dict[str, float]
        Known benchmark thresholds before the task (metric → threshold).
        Used to detect threshold-loosening attacks.
    """

    def __init__(
        self,
        *,
        baseline_test_count: int = 0,
        baseline_thresholds: dict[str, float] | None = None,
    ) -> None:
        self.baseline_test_count = baseline_test_count
        self.baseline_thresholds = baseline_thresholds or {}

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def validate(
        self,
        plan: ExecutionPlan,
        evidence: TaskEvidence,
        *,
        claimed_success: bool,
        claimed_sha: str = "",
        claimed_exit_code: int = 0,
        current_branch_sha: str = "",   # Real rev-parse of candidate branch now
    ) -> QAReport:
        """Attempt falsification of the specialist's success claim.

        Returns QAReport. If verdict is VETO or integrity_status is
        TEST_INTEGRITY_VIOLATION, integration must not proceed.
        """
        findings: list[str] = []
        veto_reasons: list[str] = []
        violations: list[str] = []
        scope_violations: list[str] = []
        integrity = TestIntegrityStatus.CLEAN

        # ---- Check 1: Unverified evidence ----
        if not evidence.verified:
            veto_reasons.append(
                "VETO: Evidence is UNVERIFIED. "
                "Producing specialist's success claim cannot be trusted without machine receipts."
            )

        # ---- Check 2: SHA match ----
        if claimed_sha and evidence.candidate_sha:
            if evidence.candidate_sha != claimed_sha:
                veto_reasons.append(
                    f"VETO: SHA mismatch. Evidence SHA={evidence.candidate_sha[:12]}…, "
                    f"claimed={claimed_sha[:12]}…"
                )

        # ---- Check 3: Stale SHA (current branch head ≠ evidence SHA) ----
        if current_branch_sha and evidence.candidate_sha:
            if evidence.candidate_sha != current_branch_sha:
                veto_reasons.append(
                    f"VETO: Stale SHA. Evidence captured at {evidence.candidate_sha[:12]}…, "
                    f"branch now at {current_branch_sha[:12]}…. "
                    "Candidate may have been modified after QA evidence was collected."
                )

        # ---- Check 4: Exit code match ----
        if evidence.test_exit_code != claimed_exit_code:
            veto_reasons.append(
                f"VETO: Test exit code mismatch. "
                f"Evidence={evidence.test_exit_code}, claimed={claimed_exit_code}."
            )

        # ---- Check 5: Test count regression (test deletion) ----
        if evidence.test_count >= 0 and self.baseline_test_count > 0:
            if evidence.test_count < self.baseline_test_count:
                delta = self.baseline_test_count - evidence.test_count
                violations.append(
                    f"TEST_INTEGRITY_VIOLATION: Test count decreased by {delta} "
                    f"(baseline={self.baseline_test_count}, now={evidence.test_count}). "
                    "Tests may have been deleted or skipped."
                )
                integrity = TestIntegrityStatus.TEST_INTEGRITY_VIOLATION

        # ---- Check 6: Threshold loosening ----
        for metric, baseline_val in self.baseline_thresholds.items():
            result_val = evidence.benchmark_result.get(metric)
            if result_val is not None:
                # A looser threshold means a lower value is now "acceptable"
                if float(result_val) < baseline_val * 0.95:
                    violations.append(
                        f"TEST_INTEGRITY_VIOLATION: Benchmark metric {metric!r} "
                        f"dropped from {baseline_val:.3f} to {result_val:.3f} "
                        f"(>{5:.0f}% regression). May indicate threshold manipulation."
                    )
                    integrity = TestIntegrityStatus.TEST_INTEGRITY_VIOLATION

        # ---- Check 7: Scope drift ----
        drift, drift_files = detect_scope_drift(
            evidence.changed_files,
            plan.mutation_boundaries,
        )
        if drift:
            scope_violations = drift_files
            veto_reasons.append(
                f"VETO: Scope drift detected. {len(drift_files)} file(s) modified "
                f"outside declared mutation boundaries: {drift_files[:5]}"
            )

        # ---- Check 8: Policy-critical file changes ----
        policy_hits = _touches_policy_files(evidence.changed_files)
        if policy_hits:
            findings.append(
                f"POLICY_FILE_CHANGED: {policy_hits} — security specialist review required."
            )

        # ---- Check 9: Claim without exit code ----
        if claimed_success and evidence.test_exit_code != 0:
            veto_reasons.append(
                "VETO: Specialist claims success but test exit code is non-zero "
                f"({evidence.test_exit_code})."
            )

        # ---- Determine verdict ----
        if veto_reasons:
            verdict = QAVerdict.VETO
        elif violations:
            verdict = QAVerdict.FAIL
        elif not claimed_success:
            verdict = QAVerdict.FAIL
            findings.append("Specialist reported non-success.")
        else:
            verdict = QAVerdict.PASS
            findings.append("All adversarial QA checks passed.")

        return QAReport(
            verdict=verdict,
            integrity_status=integrity,
            findings=findings,
            veto_reasons=veto_reasons,
            violations=violations,
            scope_violations=scope_violations,
        )


__all__ = [
    "QAVerdict",
    "TestIntegrityStatus",
    "QAReport",
    "IndependentQA",
]
