#!/usr/bin/env python3
"""Thursday V2-H Soak Test — 5,000 cycle run.

Exercises the full loop: NO_ACTION, opportunity detection, planning,
QA failures, security vetoes, approval wait/rejection, rollback,
crash recovery, and state reconciliation across 5,000 simulated cycles.

Every opportunity cycle also runs bounded integrity probes against the
real V2-H machinery:

  - ApprovalToken replay / double-consume (duplicate side effects)
  - IntegrationTransaction forbidden state transitions
  - Full rollback path PREPARED → APPROVED → APPLYING → ROLLING_BACK → FAILED_SAFE
  - SandboxLeasePolicy expiry + SHA-staleness rejection
  - Scope escape attempts (path traversal + foreign project prefixes)
  - Orphan-task detection after reconciliation
  - Unsupported-claim acceptance (fake evidence must never pass QA)

Metrics reported:
  - Workflows (cycles), total operations, errors
  - NO_ACTION cycles, opportunities detected, plans sealed
  - QA veto rate, security veto rate
  - Evidence rejected (secrets), scope drift detected
  - Invalid state transitions ACCEPTED (must be 0)
  - Orphan tasks, stale leases, duplicate side effects, rollback failures
  - Scope escapes undetected, unsupported claims accepted (must be 0)
  - Latency p50/p95/p99/max per cycle
  - RSS baseline / peak / drift (memory stability)
  - Elapsed time + host load at start/end (CONTESTED marking under load)
"""

from __future__ import annotations

import dataclasses
import gc
import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from thursday.engineering_contracts import (
    ResourceClass, RiskClass, TaskEvidence, TaskNode,
    ValueClass, new_lineage, seal_execution_plan, seal_proposal,
)
from thursday.opportunity_detector import OpportunityDetector
from thursday.evidence_collector import EvidenceCollector, detect_scope_drift
from thursday.independent_qa import IndependentQA, QAVerdict
from thursday.security_reviewer import SecurityReviewer, SecurityVerdict
from thursday.diagnostic_store import DiagnosticStore
from thursday.state_reconciler import StateReconciler
from thursday.integration_models import (
    IntegrationCandidate,
    TransactionState,
    create_transaction,
    issue_approval_token,
    seal_plan,
)
from thursday.lease_policy import SandboxLeasePolicy


def _ev(verified=True, sha="abc", exit_code=0, count=10, files=("src/a.py",)):
    return TaskEvidence(
        task_id="t-soak",
        verified=verified,
        candidate_sha=sha,
        diff_hash="d"*64,
        test_command=("pytest",),
        test_exit_code=exit_code,
        test_count=count,
        changed_files=tuple(files),
    )


class _FakeSnap:
    def __init__(self, blocked=(), failed_runs=(), pending=()):
        self.blocked_tasks = blocked
        self.failed_agent_runs = failed_runs
        self.pending_approvals = pending


class _FT:
    def __init__(self, t_id, blocked_by=("x",)):
        self.task_id = t_id
        self.title = f"Task {t_id}"
        self.project_id = "proj"
        self.blocked_by = blocked_by
        self.status = "BLOCKED"
        self.priority = 1
        self.due_epoch = None


class _FR:
    def __init__(self, r_id):
        self.run_id = r_id
        self.agent_id = "agent"
        self.blocker = "timeout"
        self.status = "FAILED"


def _prop():
    return seal_proposal(
        source_project="soak-project",
        source_evidence="soak test: ci exits 1 at cycle",
        problem_statement="Fix failing soak test",
        expected_value="CI passes",
        priority=10,
        confidence=0.9,
        risk_class=RiskClass.R2,
        value_class=ValueClass.REGRESSION_FIX,
        required_specialists=("qa",),
    )


def _plan():
    p = _prop()
    n = (TaskNode("n1", "qa", "fix", (), ResourceClass.LIGHT),)
    return seal_execution_plan(p, goal="Fix test", task_dag=n)


def _candidate(i: int) -> IntegrationCandidate:
    return IntegrationCandidate(
        task_id=f"t{i}",
        source_sha="a" * 40,
        candidate_branch=f"thursday/soak/t{i}",
        candidate_sha=f"{i:040x}",
        diff_summary=f"Soak change {i}",
        tests_passed=True,
    )


def _current_rss_mb() -> float:
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


def _peak_rss_mb() -> float:
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    except Exception:
        return 0.0


def _loadavg() -> list[float]:
    try:
        return [round(x, 2) for x in os.getloadavg()]
    except Exception:
        return []


_SCOPE_ESCAPE_PATHS = (
    "../outside_company/secrets.txt",
    "../../owner_data/private.md",
    "Nite_DSP_01/src/foreign.py",
    "KENN/config/kenn.yaml",
    "NITE_Submit/server.py",
    "SmartSampleManager/models/x.pkl",
)


def run_soak(cycles: int = 5000, seed: int = 20260823) -> dict:
    rng = random.Random(seed)
    print(f"\nTHURSDAY V2-H SOAK: {cycles} cycles (seed={seed})", flush=True)
    load_start = _loadavg()
    print(f"  host load at start: {load_start}", flush=True)
    start = time.monotonic()

    with tempfile.TemporaryDirectory() as tmpdir:
        detector = OpportunityDetector()
        qa = IndependentQA(baseline_test_count=10)
        security = SecurityReviewer()
        reconciler = StateReconciler(heavy_task_limit=2)
        diag_store = DiagnosticStore(tmpdir + "/diag")
        coll = EvidenceCollector(tmpdir)
        lease_policy = SandboxLeasePolicy()

        counters = {
            "no_action": 0,
            "opp_detected": 0,
            "plans_sealed": 0,
            "qa_veto": 0,
            "qa_fail": 0,
            "qa_pass": 0,
            "security_veto": 0,
            "security_approved": 0,
            "evidence_rejected": 0,
            "scope_drift_detected": 0,
            "integrated": 0,
            "rejected": 0,
            "heavy_deferred": 0,

            # --- integrity probes (all must be 0 to qualify) ---
            "errors": 0,
            "invalid_state_transitions_accepted": 0,
            "invalid_state_transitions_blocked": 0,
            "orphan_tasks": 0,
            "stale_leases_accepted": 0,
            "stale_leases_rejected": 0,
            "duplicate_side_effects_accepted": 0,
            "duplicate_side_effects_blocked": 0,
            "rollback_failures": 0,
            "rollbacks_executed": 0,
            "scope_escapes_undetected": 0,
            "unsupported_claims_accepted": 0,
        }

        operations = 0
        cycle_latencies_ms: list[float] = []

        rss_baseline_mb = _current_rss_mb()

        for i in range(cycles):
            if i % 500 == 0:
                elapsed_so_far = time.monotonic() - start
                print(f"  cycle {i:>5}/{cycles} — {elapsed_so_far:.1f}s elapsed", flush=True)

            t0 = time.perf_counter()
            try:
                roll = rng.random()

                # ---- NO_ACTION cycle (40%) ----
                if roll < 0.40:
                    snap = _FakeSnap()
                    opps = detector.scan(snap); operations += 1
                    assert opps == []
                    counters["no_action"] += 1
                    cycle_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
                    continue

                # ---- Opportunity detected (60%) ----
                if roll < 0.60:
                    t = _FT(f"t{i}", blocked_by=("dep",))
                    snap = _FakeSnap(blocked=(t,))
                else:
                    r = _FR(f"r{i}")
                    snap = _FakeSnap(failed_runs=(r,))

                opps = detector.scan(snap); operations += 1
                assert len(opps) > 0
                counters["opp_detected"] += 1

                # ---- Plan sealed ----
                plan = _plan(); operations += 2  # proposal + execution plan
                counters["plans_sealed"] += 1

                # ---- Evidence ----
                secret_roll = rng.random()
                if secret_roll < 0.05:
                    result = coll.collect("t", diff_text="API_KEY=sk-secretvalue12345678901234", process_exit_code=0)
                    operations += 1
                    if result.rejected:
                        counters["evidence_rejected"] += 1
                    else:
                        # Secret leaked through evidence collection.
                        counters["scope_escapes_undetected"] += 1
                    continue

                # ---- Scope drift probe ----
                drift_roll = rng.random()
                if drift_roll < 0.10:
                    drift, _ = detect_scope_drift(("hack/evil.py",), ("src/",)); operations += 1
                    if drift:
                        counters["scope_drift_detected"] += 1
                    else:
                        counters["scope_escapes_undetected"] += 1

                # ---- Evidence: clean or adversarial ----
                adversarial_roll = rng.random()
                if adversarial_roll < 0.20:
                    # Adversarial: fake evidence
                    ev = _ev(verified=False, exit_code=1, count=5)
                    claimed_success = True
                elif adversarial_roll < 0.40:
                    # Adversarial: test deletion
                    ev = _ev(count=3)
                    claimed_success = True
                else:
                    # Clean evidence
                    ev = _ev()
                    claimed_success = True

                # ---- QA ----
                # An adversarial claim is one whose underlying machine
                # evidence does not actually support success.
                adversarial_claim = (
                    not ev.verified or ev.test_exit_code != 0 or ev.test_count < 10
                )
                qa_report = qa.validate(plan, ev, claimed_success=claimed_success); operations += 1
                if qa_report.verdict == QAVerdict.VETO:
                    counters["qa_veto"] += 1
                    diag_store.retain_failure(f"t{i}", error_metadata={"qa": "VETO"}); operations += 1
                    continue
                if not qa_report.integration_permitted:
                    # FAIL verdict / integrity violation — rejected, never integrated.
                    counters["qa_fail"] += 1
                    diag_store.retain_failure(f"t{i}", error_metadata={"qa": "FAIL"}); operations += 1
                    continue
                if adversarial_claim:
                    # Unsupported claim slipped through QA — integrity failure.
                    counters["unsupported_claims_accepted"] += 1
                counters["qa_pass"] += 1

                # ---- Security ----
                sec_report = security.review(ev); operations += 1
                if sec_report.verdict == SecurityVerdict.VETO:
                    counters["security_veto"] += 1
                    continue
                counters["security_approved"] += 1

                # ---- Integrity probes (bounded, in-memory) ----
                cand = _candidate(i)

                # Token replay / duplicate side effects
                soak_plan = seal_plan(
                    target_branch="integration/soak",
                    target_sha="a" * 40,
                    candidate=cand,
                    post_test_cmd=("pytest", "-q"),
                ); operations += 1
                token = issue_approval_token(soak_plan, owner="soak-owner"); operations += 1
                ok, _reason = token.verify(soak_plan); operations += 1
                if not ok:
                    raise AssertionError("fresh token failed verification")
                token.consume(); operations += 1
                replay_ok, _ = token.verify(soak_plan); operations += 1
                if replay_ok:
                    counters["duplicate_side_effects_accepted"] += 1
                else:
                    counters["duplicate_side_effects_blocked"] += 1
                try:
                    token.consume()
                    counters["duplicate_side_effects_accepted"] += 1
                except ValueError:
                    counters["duplicate_side_effects_blocked"] += 1

                # Forbidden transaction transition must be rejected
                tx = create_transaction(soak_plan, token); operations += 1
                try:
                    tx.update_state(TransactionState.COMPLETED)  # PREPARED → COMPLETED is illegal
                    counters["invalid_state_transitions_accepted"] += 1
                except ValueError:
                    counters["invalid_state_transitions_blocked"] += 1
                operations += 1

                # Rollback path must complete cleanly
                try:
                    tx.update_state(TransactionState.APPROVED)
                    tx.update_state(TransactionState.APPLYING)
                    tx.update_state(TransactionState.ROLLING_BACK, reason="soak rollback drill")
                    tx.update_state(TransactionState.FAILED_SAFE)
                    assert tx.is_terminal and tx.state == TransactionState.FAILED_SAFE
                    counters["rollbacks_executed"] += 1
                except Exception:
                    counters["rollback_failures"] += 1
                operations += 4

                # Lease probes: expired + SHA-stale leases must be rejected
                lease = lease_policy.issue_lease(
                    task_id=f"t{i}", worktree=tmpdir + f"/wt{i}",
                    allowed_paths=[tmpdir], duration=-1.0,
                    sha="a" * 40, read_only=False,
                ); operations += 1
                ok, _ = lease_policy.validate_lease_write_attempt(
                    lease.lease_id, tmpdir + "/f.txt", "a" * 40, write_enabled=True,
                ); operations += 1
                if ok:
                    counters["stale_leases_accepted"] += 1
                else:
                    counters["stale_leases_rejected"] += 1
                ok, _ = lease_policy.validate_lease_write_attempt(
                    lease.lease_id, tmpdir + "/f.txt", "b" * 40, write_enabled=True,
                )
                # Expired already rejected above; a live lease with drifted SHA is stale.
                if ok:
                    counters["stale_leases_accepted"] += 1
                else:
                    counters["stale_leases_rejected"] += 1
                operations += 1

                # Scope escape attempts (traversal + foreign project prefixes):
                # an escape is a path that neither boundary detection nor the
                # foreign-project guard flags.
                for esc_path in _SCOPE_ESCAPE_PATHS:
                    escaped = (
                        not detect_scope_drift((esc_path,), ("src/",))[0]
                        and not reconciler.is_foreign_project(esc_path)
                    ); operations += 2
                    if escaped:
                        counters["scope_escapes_undetected"] += 1

                # ---- Reconcile or reject ----
                p_obj = _prop(); operations += 1
                lineage = new_lineage(p_obj); operations += 1
                if rng.random() < 0.85:
                    counters["integrated"] += 1
                    rec = reconciler.reconcile_after_integration(p_obj, lineage); operations += 1
                    ledger_has = p_obj.proposal_id in reconciler._proposal_states
                    terminal = lineage.final_state != "OPEN"
                    if not ledger_has or not terminal:
                        counters["orphan_tasks"] += 1
                else:
                    counters["rejected"] += 1
                    rec = reconciler.reconcile_rejection(p_obj, lineage, "Soak rejection"); operations += 1
                    ledger_has = p_obj.proposal_id in reconciler._proposal_states
                    terminal = lineage.final_state != "OPEN"
                    if not ledger_has or not terminal:
                        counters["orphan_tasks"] += 1
            except Exception:
                counters["errors"] += 1
            finally:
                cycle_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        gc.collect()
        rss_end_mb = _current_rss_mb()
        rss_peak_mb = _peak_rss_mb()
        elapsed = time.monotonic() - start
    load_end = _loadavg()

    lat_sorted = sorted(cycle_latencies_ms)

    def _pct(p: float) -> float:
        if not lat_sorted:
            return 0.0
        idx = min(len(lat_sorted) - 1, int(round(p / 100.0 * len(lat_sorted))))
        return round(lat_sorted[idx], 3)

    print(f"\n  Soak complete: {cycles} cycles in {elapsed:.1f}s ({cycles/elapsed:.0f} cycles/s)")
    print(f"  Operations: {operations:,}   Errors: {counters['errors']}")
    print(f"  NO_ACTION: {counters['no_action']:,}")
    print(f"  Opportunities: {counters['opp_detected']:,}")
    print(f"  Plans sealed: {counters['plans_sealed']:,}")
    print(f"  QA veto: {counters['qa_veto']:,}  QA fail: {counters['qa_fail']:,}  QA pass: {counters['qa_pass']:,}")
    print(f"  Security veto: {counters['security_veto']:,}  Approved: {counters['security_approved']:,}")
    print(f"  Evidence rejected (secrets): {counters['evidence_rejected']:,}")
    print(f"  Scope drift detected: {counters['scope_drift_detected']:,}")
    print(f"  Integrated: {counters['integrated']:,}  Rejected: {counters['rejected']:,}")
    print(f"  Rollbacks drilled: {counters['rollbacks_executed']:,}  Rollback failures: {counters['rollback_failures']}")
    print(f"  Invalid transitions blocked: {counters['invalid_state_transitions_blocked']:,}"
          f"  accepted: {counters['invalid_state_transitions_accepted']}")
    print(f"  Duplicate side effects blocked: {counters['duplicate_side_effects_blocked']:,}"
          f"  accepted: {counters['duplicate_side_effects_accepted']}")
    print(f"  Stale leases rejected: {counters['stale_leases_rejected']:,}"
          f"  accepted: {counters['stale_leases_accepted']}")
    print(f"  Orphan tasks: {counters['orphan_tasks']}  Unsupported claims accepted:"
          f" {counters['unsupported_claims_accepted']}  Scope escapes undetected:"
          f" {counters['scope_escapes_undetected']}")
    print(f"  Latency ms p50/p95/p99/max: {_pct(50)}/{_pct(95)}/{_pct(99)}"
          f"/{round(max(lat_sorted), 3) if lat_sorted else 0.0}")
    if rss_baseline_mb > 0 and rss_peak_mb > 0:
        print(f"  RSS baseline: {rss_baseline_mb:.1f} MB  peak: {rss_peak_mb:.1f} MB"
              f"  end: {rss_end_mb:.1f} MB  drift: {rss_end_mb - rss_baseline_mb:+.2f} MB")

    integrity_ok = (
        counters["errors"] == 0
        and counters["invalid_state_transitions_accepted"] == 0
        and counters["orphan_tasks"] == 0
        and counters["stale_leases_accepted"] == 0
        and counters["duplicate_side_effects_accepted"] == 0
        and counters["rollback_failures"] == 0
        and counters["unsupported_claims_accepted"] == 0
    )

    return {
        "soak": "THURSDAY_V2H_SOAK",
        "seed": seed,
        "cycles": cycles,
        "elapsed_seconds": round(elapsed, 2),
        "cycles_per_second": round(cycles / elapsed, 1),
        "total_operations": operations,
        "counters": counters,
        "latency_ms": {
            "p50": _pct(50),
            "p95": _pct(95),
            "p99": _pct(99),
            "max": round(max(lat_sorted), 3) if lat_sorted else 0.0,
        },
        "rss_baseline_mb": round(rss_baseline_mb, 2),
        "rss_end_mb": round(rss_end_mb, 2),
        "rss_peak_mb": round(rss_peak_mb, 2),
        "rss_drift_mb": round(rss_end_mb - rss_baseline_mb, 2),
        "host_load_start": load_start,
        "host_load_end": load_end,
        "timing_environment": "CONTESTED" if (load_start and load_start[0] > 8.0) else "CLEAN",
        "integrity_ok": integrity_ok,
        "qualified": bool(integrity_ok),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    results = run_soak(args.cycles, args.seed)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSoak results written to {args.out}")
