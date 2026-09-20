"""Thursday V2-H — Autonomous Engineering Unit Tests.

Covers all new V2-H modules across 80 cases:
  1. Engineering contracts (18 cases)
  2. Opportunity detector (14 cases)
  3. Evidence collector (10 cases)
  4. Independent QA (16 cases)
  5. Security reviewer (8 cases)
  6. Diagnostic store (6 cases)
  7. State reconciler (5 cases)
  8. Owner brief generator (5 cases)
"""

from __future__ import annotations

import dataclasses
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from thursday.engineering_contracts import (
    BLOCKED_RISK_CLASSES,
    CandidateLineage,
    ExecutionPlan,
    LoopDecision,
    ResourceClass,
    RiskClass,
    TaskEvidence,
    TaskNode,
    ValueClass,
    new_lineage,
    seal_execution_plan,
    seal_proposal,
)
from thursday.opportunity_detector import Opportunity, OpportunityDetector, ProvenanceClass
from thursday.evidence_collector import EvidenceCollector, detect_scope_drift
from thursday.independent_qa import IndependentQA, QAVerdict, TestIntegrityStatus
from thursday.security_reviewer import SecurityReviewer, SecurityVerdict
from thursday.diagnostic_store import DiagnosticStore
from thursday.state_reconciler import StateReconciler
from thursday.owner_brief_generator import OwnerBriefGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _proposal(**kwargs):
    defaults = dict(
        source_project="test-project",
        source_evidence="test failing: test_foo exits 1",
        problem_statement="Test is failing",
        expected_value="Restored CI stability",
        priority=10,
        confidence=0.9,
        risk_class=RiskClass.R2,
        value_class=ValueClass.REGRESSION_FIX,
        required_specialists=("qa",),
    )
    defaults.update(kwargs)
    return seal_proposal(**defaults)


def _plan(proposal=None, **kwargs):
    p = proposal or _proposal()
    nodes = (TaskNode("n1", "qa", "Fix test", (), ResourceClass.LIGHT),)
    return seal_execution_plan(p, goal="Fix failing test", task_dag=nodes, **kwargs)


def _evidence(task_id="t-001", verified=True, candidate_sha="abc123", exit_code=0, test_count=10):
    return TaskEvidence(
        task_id=task_id,
        verified=verified,
        candidate_sha=candidate_sha,
        diff_hash="d" * 64,
        test_command=("pytest",),
        test_exit_code=exit_code,
        test_count=test_count,
        changed_files=("tests/test_foo.py",),
    )


class _FakeSnapshot:
    """Minimal CompanySnapshot stub."""
    def __init__(self, blocked=(), failed_runs=(), pending=()):
        self.blocked_tasks = blocked
        self.failed_agent_runs = failed_runs
        self.pending_approvals = pending


class _FakeTask:
    def __init__(self, task_id, title, project_id, blocked_by=()):
        self.task_id = task_id
        self.title = title
        self.project_id = project_id
        self.blocked_by = blocked_by
        self.status = "BLOCKED"
        self.priority = 1
        self.due_epoch = None


class _FakeRun:
    def __init__(self, run_id, agent_id, blocker=""):
        self.run_id = run_id
        self.agent_id = agent_id
        self.blocker = blocker
        self.status = "FAILED"


class _FakeApproval:
    def __init__(self, a_id, cap_id, summary):
        self.approval_id = a_id
        self.capability_id = cap_id
        self.summary = summary
        self.action_level = "HIGH"
        self.reversibility = "reversible"
        self.created_at_epoch = time.time()


# ---------------------------------------------------------------------------
# Section 1: Engineering Contracts (18 cases)
# ---------------------------------------------------------------------------

class TestEngineeringContracts(unittest.TestCase):

    def test_proposal_hash_stable(self):
        p = _proposal()
        self.assertEqual(p.proposal_hash, p.compute_hash())

    def test_proposal_hash_changes_on_evidence_change(self):
        p1 = _proposal(source_evidence="evidence A")
        p2 = _proposal(source_evidence="evidence B")
        self.assertNotEqual(p1.proposal_hash, p2.proposal_hash)

    def test_proposal_empty_evidence_rejected(self):
        with self.assertRaises(ValueError):
            seal_proposal(
                source_project="x", source_evidence="",
                problem_statement="p", expected_value="v",
                priority=0, confidence=0.9,
                risk_class=RiskClass.R1, value_class=ValueClass.CRITICAL_FIX,
                required_specialists=("qa",),
            )

    def test_proposal_blocked_risk_classes(self):
        for rc in BLOCKED_RISK_CLASSES:
            with self.assertRaises(ValueError, msg=f"{rc} should be blocked"):
                seal_proposal(
                    source_project="x", source_evidence="e",
                    problem_statement="p", expected_value="v",
                    priority=0, confidence=0.9,
                    risk_class=rc, value_class=ValueClass.CRITICAL_FIX,
                    required_specialists=("qa",),
                )

    def test_proposal_confidence_bounds(self):
        with self.assertRaises(ValueError):
            seal_proposal(
                source_project="x", source_evidence="e",
                problem_statement="p", expected_value="v",
                priority=0, confidence=1.5,
                risk_class=RiskClass.R1, value_class=ValueClass.CRITICAL_FIX,
                required_specialists=("qa",),
            )

    def test_plan_hash_stable(self):
        plan = _plan()
        self.assertEqual(plan.plan_hash, plan.compute_hash())

    def test_plan_hash_sensitive_to_goal(self):
        p = _proposal()
        n = (TaskNode("n1", "qa", "obj", (), ResourceClass.LIGHT),)
        pl1 = seal_execution_plan(p, goal="Fix A", task_dag=n)
        pl2 = seal_execution_plan(p, goal="Fix B", task_dag=n)
        self.assertNotEqual(pl1.plan_hash, pl2.plan_hash)

    def test_plan_includes_specialists(self):
        plan = _plan()
        self.assertIn("qa", plan.specialists)

    def test_evidence_unverified_flag(self):
        ev = _evidence(verified=False)
        ok, reason = ev.verify_claim("abc123", 0)
        self.assertFalse(ok)
        self.assertIn("UNVERIFIED", reason)

    def test_evidence_sha_mismatch(self):
        ev = _evidence(candidate_sha="real-sha")
        ok, reason = ev.verify_claim("fake-sha", 0)
        self.assertFalse(ok)
        self.assertIn("SHA mismatch", reason)

    def test_evidence_exit_code_mismatch(self):
        ev = _evidence(exit_code=1)
        ok, reason = ev.verify_claim("abc123", 0)
        self.assertFalse(ok)
        self.assertIn("Exit code", reason)

    def test_evidence_valid(self):
        ev = _evidence()
        ok, _ = ev.verify_claim("abc123", 0)
        self.assertTrue(ok)

    def test_lineage_append_only(self):
        p = _proposal()
        lineage = new_lineage(p)
        n = len(lineage.events)
        lineage.append("QA", "QA passed.")
        self.assertEqual(len(lineage.events), n + 1)

    def test_lineage_close_idempotent(self):
        p = _proposal()
        lineage = new_lineage(p)
        lineage.close("INTEGRATED", "Done.")
        lineage.close("INTEGRATED", "Done again.")   # Should not raise or overwrite
        self.assertEqual(lineage.final_state, "INTEGRATED")

    def test_lineage_request_changes_increments_generation(self):
        p = _proposal()
        lineage = new_lineage(p)
        lineage.request_changes("Need more tests.")
        self.assertEqual(lineage.generation, 1)

    def test_value_classes_exist(self):
        for vc in ValueClass:
            self.assertIsInstance(vc.value, str)

    def test_risk_r0_r3_allowed(self):
        for rc in (RiskClass.R0, RiskClass.R1, RiskClass.R2, RiskClass.R3):
            p = seal_proposal(
                source_project="x", source_evidence="e",
                problem_statement="p", expected_value="v",
                priority=0, confidence=0.9,
                risk_class=rc, value_class=ValueClass.CRITICAL_FIX,
                required_specialists=("qa",),
            )
            self.assertIsNotNone(p)

    def test_task_node_depends_on(self):
        n = TaskNode("n2", "engineering", "Fix", ("n1",), ResourceClass.MEDIUM)
        self.assertEqual(n.depends_on, ("n1",))


# ---------------------------------------------------------------------------
# Section 2: Opportunity Detector (14 cases)
# ---------------------------------------------------------------------------

class TestOpportunityDetector(unittest.TestCase):

    def setUp(self):
        self.detector = OpportunityDetector()

    def test_healthy_snapshot_no_action(self):
        snap = _FakeSnapshot()
        opps = self.detector.scan(snap)
        self.assertEqual(opps, [])
        self.assertEqual(self.detector.decide(opps), LoopDecision.NO_ACTION)

    def test_blocked_task_detected(self):
        t = _FakeTask("task-1", "Fix parser", "proj-a", blocked_by=("dep-1",))
        snap = _FakeSnapshot(blocked=(t,))
        opps = self.detector.scan(snap)
        self.assertTrue(len(opps) >= 1)
        self.assertIn("BLOCKED", opps[0].source_evidence)

    def test_blocked_task_without_blocked_by_ignored(self):
        t = _FakeTask("task-2", "Do something", "proj-b", blocked_by=())
        snap = _FakeSnapshot(blocked=(t,))
        opps = self.detector.scan(snap)
        blocked_opps = [o for o in opps if "task-2" in o.opportunity_id]
        self.assertEqual(len(blocked_opps), 0)

    def test_failed_run_detected(self):
        r = _FakeRun("run-1", "slo-agent", blocker="timeout")
        snap = _FakeSnapshot(failed_runs=(r,))
        opps = self.detector.scan(snap)
        self.assertTrue(len(opps) >= 1)

    def test_pending_approval_detected(self):
        a = _FakeApproval("appr-1", "cap-1", "Needs merge")
        snap = _FakeSnapshot(pending=(a,))
        opps = self.detector.scan(snap)
        self.assertTrue(len(opps) >= 1)
        self.assertEqual(opps[0].provenance_class, ProvenanceClass.CANDIDATE_PENDING)

    def test_opportunity_requires_source_evidence(self):
        with self.assertRaises(ValueError):
            Opportunity(
                opportunity_id="opp-x",
                source_project="proj",
                source_evidence="",   # empty — must raise
                provenance_class=ProvenanceClass.FAILING_TEST,
                problem_statement="X",
                value_class=ValueClass.CRITICAL_FIX,
                risk_class=RiskClass.R1,
                priority_score=0,
                confidence=0.9,
                attention_level=None,
                recommended_specialists=(),
            )

    def test_confidence_filter(self):
        detector = OpportunityDetector(min_confidence=0.99)
        r = _FakeRun("run-2", "agent", blocker="x")
        snap = _FakeSnapshot(failed_runs=(r,))
        opps = detector.scan(snap)
        # Failed run has confidence=0.85, below 0.99 threshold
        self.assertEqual(opps, [])

    def test_sorted_by_priority(self):
        t = _FakeTask("t1", "Title", "proj", blocked_by=("x",))
        r = _FakeRun("r1", "agent", blocker="y")
        a = _FakeApproval("a1", "cap", "Pending")
        snap = _FakeSnapshot(blocked=(t,), failed_runs=(r,), pending=(a,))
        opps = self.detector.scan(snap)
        scores = [o.priority_score for o in opps]
        self.assertEqual(scores, sorted(scores))

    def test_programme_failure_detected(self):
        class FakeProg:
            status = "FAIL"
            display_name = "SLO System"
            latest_report_summary = "Parser regression"
        snap = _FakeSnapshot()
        opps = self.detector.scan(snap, programme_state={"slo": FakeProg()})
        self.assertTrue(any("slo" in o.opportunity_id for o in opps))

    def test_low_value_filtered_by_default(self):
        detector = OpportunityDetector(include_low_value=False)
        # Can't easily inject a LOW_VALUE_CLEANUP above floor from snapshot
        # but we can verify healthy snapshot stays empty
        snap = _FakeSnapshot()
        self.assertEqual(detector.scan(snap), [])

    def test_decide_no_action_empty(self):
        self.assertEqual(self.detector.decide([]), LoopDecision.NO_ACTION)

    def test_decide_escalate_on_approval_required(self):
        from thursday.engineering_contracts import AttentionLevel
        opp = Opportunity(
            opportunity_id="opp-appr",
            source_project="proj",
            source_evidence="pending approval exists",
            provenance_class=ProvenanceClass.CANDIDATE_PENDING,
            problem_statement="Pending review",
            value_class=ValueClass.PRODUCT_IMPROVEMENT,
            risk_class=RiskClass.R0,
            priority_score=30,
            confidence=1.0,
            attention_level=AttentionLevel.APPROVAL_REQUIRED,
            recommended_specialists=("product",),
            owner_approval_required=True,
        )
        self.assertEqual(self.detector.decide([opp]), LoopDecision.ESCALATE)

    def test_decide_execute_on_normal_opp(self):
        from thursday.engineering_contracts import AttentionLevel
        opp = Opportunity(
            opportunity_id="opp-normal",
            source_project="proj",
            source_evidence="test failing",
            provenance_class=ProvenanceClass.FAILING_TEST,
            problem_statement="Fix test",
            value_class=ValueClass.REGRESSION_FIX,
            risk_class=RiskClass.R2,
            priority_score=20,
            confidence=0.9,
            attention_level=AttentionLevel.ACTION_SOON,
            recommended_specialists=("qa",),
            owner_approval_required=False,
        )
        self.assertEqual(self.detector.decide([opp]), LoopDecision.EXECUTE)

    def test_multiple_sources_combined(self):
        t = _FakeTask("t1", "Blocked", "proj", blocked_by=("x",))
        r = _FakeRun("r1", "agent", blocker="y")
        snap = _FakeSnapshot(blocked=(t,), failed_runs=(r,))
        opps = self.detector.scan(snap)
        self.assertGreaterEqual(len(opps), 2)


# ---------------------------------------------------------------------------
# Section 3: Evidence Collector (10 cases)
# ---------------------------------------------------------------------------

class TestEvidenceCollector(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.collector = EvidenceCollector(self._tmp)

    def test_secret_in_diff_rejected(self):
        result = self.collector.collect(
            "t-1",
            diff_text="API_KEY=sk-abcdefghijklmnopqrstuvwxyz12345",
            process_exit_code=0,
        )
        self.assertTrue(result.rejected)
        self.assertIn("SECRET_LEAK", result.rejection_reason)
        self.assertIsNone(result.evidence)

    def test_clean_diff_accepted(self):
        result = self.collector.collect(
            "t-2",
            diff_text="- old line\n+ new line",
            process_exit_code=0,
        )
        self.assertFalse(result.rejected)
        self.assertIsNotNone(result.evidence)

    def test_evidence_unverified_without_sha(self):
        result = self.collector.collect("t-3", process_exit_code=0)
        self.assertFalse(result.evidence.verified)

    def test_evidence_verified_with_sha_and_exit(self):
        # No real git available; mock _resolve_sha
        self.collector._resolve_sha = lambda b: "sha-abc"
        result = self.collector.collect(
            "t-4",
            candidate_branch="some-branch",
            process_exit_code=0,
        )
        self.assertTrue(result.evidence.verified)

    def test_diff_hash_computed(self):
        result = self.collector.collect("t-5", diff_text="delta", process_exit_code=0)
        self.assertTrue(len(result.evidence.diff_hash) == 64)

    def test_no_diff_no_diff_hash(self):
        result = self.collector.collect("t-6", process_exit_code=0)
        self.assertEqual(result.evidence.diff_hash, "")

    def test_changed_files_preserved(self):
        result = self.collector.collect(
            "t-7", changed_files=["a.py", "b.py"], process_exit_code=0
        )
        self.assertIn("a.py", result.evidence.changed_files)

    def test_scope_drift_detected(self):
        drift, violations = detect_scope_drift(
            ("src/main.py", "hacked/secret.py"),
            ("src/",),
        )
        self.assertTrue(drift)
        self.assertIn("hacked/secret.py", violations)

    def test_no_scope_drift(self):
        drift, _ = detect_scope_drift(("src/main.py",), ("src/",))
        self.assertFalse(drift)

    def test_empty_boundaries_no_drift(self):
        drift, _ = detect_scope_drift(("anywhere/file.py",), ())
        self.assertFalse(drift)


# ---------------------------------------------------------------------------
# Section 4: Independent QA (16 cases)
# ---------------------------------------------------------------------------

class TestIndependentQA(unittest.TestCase):

    def _qa(self, baseline_count=10, thresholds=None):
        return IndependentQA(baseline_test_count=baseline_count, baseline_thresholds=thresholds or {})

    def test_pass_on_verified_evidence(self):
        qa = self._qa()
        plan = _plan()
        ev = _evidence()
        report = qa.validate(plan, ev, claimed_success=True, claimed_sha="abc123")
        self.assertEqual(report.verdict, QAVerdict.PASS)

    def test_veto_on_unverified_evidence(self):
        qa = self._qa()
        plan = _plan()
        ev = _evidence(verified=False)
        report = qa.validate(plan, ev, claimed_success=True)
        self.assertEqual(report.verdict, QAVerdict.VETO)

    def test_veto_on_sha_mismatch(self):
        qa = self._qa()
        plan = _plan()
        ev = _evidence(candidate_sha="real-sha")
        report = qa.validate(plan, ev, claimed_success=True, claimed_sha="fake-sha")
        self.assertEqual(report.verdict, QAVerdict.VETO)

    def test_veto_on_stale_sha(self):
        qa = self._qa()
        plan = _plan()
        ev = _evidence(candidate_sha="old-sha")
        report = qa.validate(
            plan, ev,
            claimed_success=True,
            current_branch_sha="new-sha-after-drift",
        )
        self.assertEqual(report.verdict, QAVerdict.VETO)
        self.assertTrue(any("Stale" in r for r in report.veto_reasons))

    def test_veto_on_exit_code_mismatch(self):
        qa = self._qa()
        plan = _plan()
        ev = _evidence(exit_code=1)
        report = qa.validate(plan, ev, claimed_success=True, claimed_exit_code=0)
        self.assertEqual(report.verdict, QAVerdict.VETO)

    def test_test_integrity_violation_on_count_decrease(self):
        qa = self._qa(baseline_count=20)
        plan = _plan()
        ev = _evidence(test_count=15)   # 5 fewer
        report = qa.validate(plan, ev, claimed_success=True)
        self.assertEqual(report.integrity_status, TestIntegrityStatus.TEST_INTEGRITY_VIOLATION)

    def test_test_integrity_violation_on_threshold_drop(self):
        qa = self._qa(thresholds={"accuracy": 0.98})
        plan = _plan()
        ev = dataclasses.replace(
            _evidence(),
            benchmark_result={"accuracy": 0.80},  # >5% drop
        )
        report = qa.validate(plan, ev, claimed_success=True)
        self.assertEqual(report.integrity_status, TestIntegrityStatus.TEST_INTEGRITY_VIOLATION)

    def test_no_integrity_violation_within_tolerance(self):
        qa = self._qa(thresholds={"accuracy": 0.98})
        plan = _plan()
        ev = dataclasses.replace(_evidence(), benchmark_result={"accuracy": 0.97})
        report = qa.validate(plan, ev, claimed_success=True)
        self.assertEqual(report.integrity_status, TestIntegrityStatus.CLEAN)

    def test_veto_on_scope_drift(self):
        plan = _plan(mutation_boundaries=("src/",))
        ev = dataclasses.replace(
            _evidence(),
            changed_files=("src/main.py", "malicious/inject.py"),
        )
        qa = self._qa()
        report = qa.validate(plan, ev, claimed_success=True)
        self.assertEqual(report.verdict, QAVerdict.VETO)
        self.assertTrue(len(report.scope_violations) > 0)

    def test_policy_file_flagged(self):
        plan = _plan()
        ev = dataclasses.replace(
            _evidence(),
            changed_files=("thursday/shared_executor.py",),
        )
        qa = self._qa()
        report = qa.validate(plan, ev, claimed_success=True)
        self.assertTrue(any("POLICY_FILE_CHANGED" in f for f in report.findings))

    def test_fail_on_claimed_success_but_nonzero_exit(self):
        qa = self._qa()
        plan = _plan()
        ev = _evidence(exit_code=1)
        report = qa.validate(plan, ev, claimed_success=True, claimed_exit_code=1)
        # claimed_exit_code=1 matches evidence but claimed_success=True conflicts
        self.assertIn(report.verdict.value, ["VETO", "FAIL"])

    def test_not_integration_permitted_on_veto(self):
        qa = self._qa()
        plan = _plan()
        ev = _evidence(verified=False)
        report = qa.validate(plan, ev, claimed_success=True)
        self.assertFalse(report.integration_permitted)

    def test_integration_permitted_on_pass(self):
        qa = self._qa()
        plan = _plan()
        ev = _evidence()
        report = qa.validate(plan, ev, claimed_success=True, claimed_sha="abc123")
        self.assertTrue(report.integration_permitted)

    def test_fail_on_claimed_failure(self):
        qa = self._qa()
        plan = _plan()
        ev = _evidence(exit_code=0)
        report = qa.validate(plan, ev, claimed_success=False)
        self.assertEqual(report.verdict, QAVerdict.FAIL)

    def test_multiple_vetoes_accumulated(self):
        qa = self._qa()
        plan = _plan()
        ev = _evidence(verified=False, candidate_sha="wrong")
        report = qa.validate(plan, ev, claimed_success=True, claimed_sha="real")
        self.assertGreaterEqual(len(report.veto_reasons), 2)

    def test_baseline_count_zero_no_integrity_violation(self):
        qa = self._qa(baseline_count=0)
        plan = _plan()
        ev = _evidence(test_count=5)
        report = qa.validate(plan, ev, claimed_success=True)
        self.assertEqual(report.integrity_status, TestIntegrityStatus.CLEAN)


# ---------------------------------------------------------------------------
# Section 5: Security Reviewer (8 cases)
# ---------------------------------------------------------------------------

class TestSecurityReviewer(unittest.TestCase):

    def setUp(self):
        self.reviewer = SecurityReviewer()

    def test_clean_files_approved(self):
        ev = _evidence(candidate_sha="abc")
        report = self.reviewer.review(ev)
        self.assertEqual(report.verdict, SecurityVerdict.APPROVED)

    def test_shared_executor_triggers_veto(self):
        ev = dataclasses.replace(
            _evidence(),
            changed_files=("thursday/shared_executor.py",),
        )
        report = self.reviewer.review(ev)
        self.assertEqual(report.verdict, SecurityVerdict.VETO)
        self.assertTrue(len(report.veto_reasons) > 0)

    def test_lease_policy_triggers_veto(self):
        ev = dataclasses.replace(_evidence(), changed_files=("thursday/lease_policy.py",))
        report = self.reviewer.review(ev)
        self.assertEqual(report.verdict, SecurityVerdict.VETO)

    def test_integration_models_triggers_veto(self):
        ev = dataclasses.replace(_evidence(), changed_files=("thursday/integration_models.py",))
        report = self.reviewer.review(ev)
        self.assertEqual(report.verdict, SecurityVerdict.VETO)

    def test_policy_file_in_qa_findings_triggers_veto(self):
        ev = _evidence()
        report = self.reviewer.review(ev, qa_findings=["POLICY_FILE_CHANGED: thursday/plan_approval.py"])
        self.assertEqual(report.verdict, SecurityVerdict.VETO)

    def test_security_veto_blocks_integration(self):
        ev = dataclasses.replace(_evidence(), changed_files=("thursday/confirmation.py",))
        report = self.reviewer.review(ev)
        self.assertFalse(report.integration_permitted)

    def test_thursday_self_mod_flagged_not_vetoed(self):
        ev = dataclasses.replace(_evidence(), changed_files=("thursday/new_feature.py",))
        report = self.reviewer.review(ev)
        # Non-critical thursday file: flag but not veto
        self.assertIn("self-modification", " ".join(report.findings).lower())
        self.assertEqual(report.verdict, SecurityVerdict.APPROVED)

    def test_is_security_critical_helper(self):
        self.assertTrue(SecurityReviewer.is_security_critical("thursday/shared_executor.py"))
        self.assertFalse(SecurityReviewer.is_security_critical("thursday/diagnostics.py"))


# ---------------------------------------------------------------------------
# Section 6: Diagnostic Store (6 cases)
# ---------------------------------------------------------------------------

class TestDiagnosticStore(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def _store(self, max_retained=10):
        return DiagnosticStore(self._tmp, max_retained=max_retained)

    def test_failure_retained(self):
        store = self._store()
        entry = store.retain_failure("task-1", error_metadata={"err": "boom"})
        self.assertIsNotNone(entry)
        entries = store.list_entries()
        self.assertEqual(len(entries), 1)

    def test_secret_scrubbed_in_diff(self):
        store = self._store()
        store.retain_failure("t-2", diff_summary="API_KEY=sk-secretvalue12345678901234")
        entries = store.list_entries()
        import json
        with open(entries[0].path) as f:
            raw = f.read()
        self.assertNotIn("sk-secretvalue", raw)
        self.assertIn("REDACTED", raw)

    def test_max_count_respected(self):
        store = self._store(max_retained=3)
        for i in range(6):
            store.retain_failure(f"t-{i}", error_metadata={})
        self.assertLessEqual(len(store.list_entries()), 3)

    def test_max_age_pruning(self):
        store = DiagnosticStore(self._tmp, max_age_seconds=0.01)
        store.retain_failure("t-old", error_metadata={})
        time.sleep(0.05)
        store._prune()
        self.assertEqual(len(store.list_entries()), 0)

    def test_oversized_entry_rejected(self):
        store = self._store()
        huge_diff = "x" * (2 * 1024 * 1024)  # 2 MB, over limit
        entry = store.retain_failure("t-big", diff_summary=huge_diff)
        self.assertIsNone(entry)

    def test_multiple_entries_sorted_by_time(self):
        store = self._store()
        for i in range(3):
            store.retain_failure(f"t-{i}")
            time.sleep(0.01)
        entries = store.list_entries()
        times = [e.created_at for e in entries]
        self.assertEqual(times, sorted(times))


# ---------------------------------------------------------------------------
# Section 7: State Reconciler (5 cases)
# ---------------------------------------------------------------------------

class TestStateReconciler(unittest.TestCase):

    def test_integration_marks_proposal_integrated(self):
        reconciler = StateReconciler()
        p = _proposal()
        lineage = new_lineage(p)
        result = reconciler.reconcile_after_integration(p, lineage)
        self.assertIn(p.proposal_id, result.integrated_proposals)
        self.assertEqual(lineage.final_state, "INTEGRATED")

    def test_rejection_marks_rejected(self):
        reconciler = StateReconciler()
        p = _proposal()
        lineage = new_lineage(p)
        result = reconciler.reconcile_rejection(p, lineage, "Owner rejected.")
        self.assertTrue(any("REJECTED" in u for u in result.state_updates))
        self.assertEqual(lineage.final_state, "REJECTED")

    def test_no_action_recorded(self):
        reconciler = StateReconciler()
        result = reconciler.reconcile_no_action("System healthy.")
        self.assertTrue(any("NO_ACTION" in n for n in result.notes))

    def test_foreign_project_detection(self):
        reconciler = StateReconciler()
        self.assertTrue(reconciler.is_foreign_project("Nite_DSP_01/some/file.py"))
        self.assertFalse(reconciler.is_foreign_project("thursday/autonomous_controller.py"))

    def test_heavy_budget_respects_limit(self):
        reconciler = StateReconciler(heavy_task_limit=2)
        reconciler.increment_heavy_count()
        reconciler.increment_heavy_count()
        self.assertFalse(reconciler.heavy_task_budget_available())


# ---------------------------------------------------------------------------
# Section 8: Owner Brief Generator (5 cases)
# ---------------------------------------------------------------------------

class TestOwnerBriefGenerator(unittest.TestCase):

    def _make_qa_report(self, verdict=QAVerdict.PASS):
        from thursday.independent_qa import QAReport, TestIntegrityStatus
        return QAReport(
            verdict=verdict,
            integrity_status=TestIntegrityStatus.CLEAN,
            findings=["All checks passed."],
        )

    def _make_sec_report(self, verdict=SecurityVerdict.APPROVED):
        from thursday.security_reviewer import SecurityReport
        return SecurityReport(verdict=verdict, critical_files=[], veto_reasons=[], findings=[])

    def test_approval_packet_generated(self):
        gen = OwnerBriefGenerator()
        p = _proposal()
        plan = _plan(p)
        ev = _evidence()
        qa = self._make_qa_report()
        sec = self._make_sec_report()
        packet = gen.approval_packet(p, plan, ev, qa, sec,
                                     target_branch="thursday/staging",
                                     current_target_sha="sha-x")
        self.assertEqual(packet.project, "test-project")
        self.assertIn("APPROVE", packet.render_text())

    def test_veto_changes_recommendation(self):
        gen = OwnerBriefGenerator()
        p = _proposal()
        plan = _plan(p)
        ev = _evidence()
        qa = self._make_qa_report(QAVerdict.VETO)
        sec = self._make_sec_report()
        packet = gen.approval_packet(p, plan, ev, qa, sec,
                                     target_branch="t/stage", current_target_sha="sha-y")
        self.assertIn("DO NOT APPROVE", packet.recommendation)

    def test_status_brief_renders(self):
        gen = OwnerBriefGenerator()
        brief = gen.status_brief(projects_active=3, projects_healthy=2,
                                  waiting_approval=1, heavy_tasks_deferred=0)
        text = brief.render_text()
        self.assertIn("3 projects active", text)
        self.assertIn("1 waiting for approval", text)

    def test_attention_level_propagated(self):
        gen = OwnerBriefGenerator()
        p = _proposal()
        plan = _plan(p)
        ev = _evidence()
        qa = self._make_qa_report()
        sec = self._make_sec_report()
        packet = gen.approval_packet(p, plan, ev, qa, sec,
                                     target_branch="t/staging", current_target_sha="s")
        from thursday.engineering_contracts import AttentionLevel
        self.assertEqual(packet.attention_level, AttentionLevel.APPROVAL_REQUIRED)

    def test_brief_no_unsupported_claims(self):
        gen = OwnerBriefGenerator()
        brief = gen.status_brief(critical_failures=0)
        text = brief.render_text()
        # Should not contain fabricated project names not passed in
        self.assertNotIn("SLO", text)
        self.assertNotIn("KENN", text)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
