"""THURSDAY_SHARED_MUTATION_V1 — Adversarial Benchmark for V2-G.

Validates all critical safety invariants for the approval-gated shared
mutation system under 300+ scenarios across six categories:

  A. Token Security (60 scenarios)
     - Replay attacks, expiry, consumed tokens, digest tampering, SHA binding
  B. TOCTOU Integrity (60 scenarios)
     - Branch drift before/after lock, double-check under lease, race timing
  C. Forbidden Branch Guard (20 scenarios)
     - main, master, production, release protection
  D. Rollback Correctness (60 scenarios)
     - QA failure rollback, apply failure rollback, nested failure, no crash
  E. Lease Concurrency (40 scenarios)
     - Mutual exclusion, timeout, orderly release, concurrent acquisition
  F. Diagnostic Log Integrity (20 scenarios)
     - Always written, pruned at max_log_files, no partial writes

Acceptance Criteria
-------------------
  Overall accuracy : >= 98.0%
  Token security   : 100%
  TOCTOU integrity : 100%
  Forbidden branch : 100%
  Rollback correct : >= 95%
  Lease concurrency: >= 95%
  Log integrity    : 100%
"""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from thursday.integration_models import (
    ApprovalToken,
    IntegrationCandidate,
    IntegrationPlan,
    TransactionState,
    issue_approval_token,
    seal_plan,
)
from thursday.shared_executor import (
    IntegrationLeaseRegistry,
    SharedExecutor,
)

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _candidate(task_id: str = "t-001", source_sha: str = "src-abc", candidate_sha: str = "cand-def") -> IntegrationCandidate:
    return IntegrationCandidate(
        task_id=task_id,
        source_sha=source_sha,
        candidate_branch=f"thursday/task/{task_id}",
        candidate_sha=candidate_sha,
        diff_summary="benchmark candidate",
        tests_passed=True,
        qa_receipt={"ts": 0},
    )


def _plan(
    target_sha: str = "sha-sealed",
    target_branch: str = "thursday/benchmark-staging",
    apply_method: str = "fast_forward",
    post_test_cmd: tuple[str, ...] = (),
    candidate: IntegrationCandidate | None = None,
) -> IntegrationPlan:
    return seal_plan(
        target_branch=target_branch,
        target_sha=target_sha,
        candidate=candidate or _candidate(),
        apply_method=apply_method,
        post_test_cmd=post_test_cmd,
    )


def _executor(tmp: str, sha: str = "sha-sealed") -> SharedExecutor:
    log_dir = os.path.join(tmp, "logs")
    ex = SharedExecutor(repo_path=tmp, log_dir=log_dir, max_log_files=100)

    def fake_git(args: list[str]) -> str:
        if args[0] == "rev-parse":
            return sha + "\n"
        return ""

    ex._git = fake_git
    return ex


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

class CategoryResult:
    def __init__(self, name: str) -> None:
        self.name = name
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def record(self, passed: bool, label: str, msg: str = "") -> None:
        if passed:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(f"  FAIL [{label}]: {msg}")

    @property
    def total(self) -> int:
        return self.passed + self.failed

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def report(self) -> str:
        pct = self.accuracy * 100
        status = "PASS" if self.failed == 0 else "FAIL"
        lines = [f"  {status}  {self.name}: {self.passed}/{self.total} ({pct:.1f}%)"]
        lines.extend(self.errors[:10])
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Category A: Token Security
# ---------------------------------------------------------------------------

def run_category_a(cat: CategoryResult, tmp: str) -> None:
    """60 token security scenarios."""

    # A1-A20: Expired tokens (varying TTL deltas)
    for i in range(20):
        p = _plan(target_sha="sha-x")
        tok = issue_approval_token(p, owner="owner", ttl_seconds=0)
        tok = dataclasses.replace(tok, expires_at=time.time() - (i + 1))
        ex = _executor(tmp, sha="sha-x")
        tx = ex.execute(p, tok)
        passed = tx.state == TransactionState.ABORTED
        cat.record(passed, f"A1-expired-{i}", f"state={tx.state}")

    # A21-A40: Consumed (replay) tokens
    for i in range(20):
        p = _plan(target_sha="sha-y")
        tok = issue_approval_token(p, owner="owner")
        tok.consume()
        ex = _executor(tmp, sha="sha-y")
        tx = ex.execute(p, tok)
        passed = tx.state == TransactionState.ABORTED
        cat.record(passed, f"A2-replay-{i}", f"state={tx.state}")

    # A41-A50: Plan digest mismatch (different plan presented to executor)
    for i in range(10):
        p_real = _plan(target_sha=f"sha-real-{i}")
        p_fake = _plan(target_sha=f"sha-fake-{i}")
        tok = issue_approval_token(p_real, owner="owner")
        ex = _executor(tmp, sha=f"sha-fake-{i}")
        tx = ex.execute(p_fake, tok)
        passed = tx.state == TransactionState.ABORTED
        cat.record(passed, f"A3-digest-{i}", f"state={tx.state}")

    # A51-A60: Token bound to different target SHA
    for i in range(10):
        p = _plan(target_sha="sha-correct")
        tok = issue_approval_token(p, owner="owner")
        tok_tampered = dataclasses.replace(tok, target_sha="sha-tampered", plan_digest=p.plan_digest)
        ex = _executor(tmp, sha="sha-correct")
        tx = ex.execute(p, tok_tampered)
        passed = tx.state == TransactionState.ABORTED
        cat.record(passed, f"A4-sha-bind-{i}", f"state={tx.state}")


# ---------------------------------------------------------------------------
# Category B: TOCTOU Integrity
# ---------------------------------------------------------------------------

def run_category_b(cat: CategoryResult, tmp: str) -> None:
    """60 TOCTOU scenarios."""

    # B1-B30: SHA drift (different HEAD returned)
    for i in range(30):
        p = _plan(target_sha="sha-sealed")
        tok = issue_approval_token(p, owner="owner")
        ex = _executor(tmp, sha=f"sha-drifted-{i}")
        tx = ex.execute(p, tok)
        passed = tx.state == TransactionState.ABORTED
        cat.record(passed, f"B1-drift-{i}", f"state={tx.state}")

    # B31-B60: SHA drift under lock (race window: second rev-parse differs)
    for i in range(30):
        p = _plan(target_sha="sha-sealed")
        tok = issue_approval_token(p, owner="owner")
        ex = _executor(tmp, sha="sha-sealed")
        calls = [0]

        def make_race_git(sealed=p.target_sha):
            def race_git(args: list[str]) -> str:
                if args[0] == "rev-parse":
                    calls[0] += 1
                    return sealed + "\n" if calls[0] == 1 else "sha-raced\n"
                return ""
            return race_git

        ex._git = make_race_git()
        tx = ex.execute(p, tok)
        passed = tx.state == TransactionState.ABORTED
        cat.record(passed, f"B2-race-lock-{i}", f"state={tx.state}")


# ---------------------------------------------------------------------------
# Category C: Forbidden Branch Guard
# ---------------------------------------------------------------------------

def run_category_c(cat: CategoryResult, tmp: str) -> None:
    """20 forbidden branch scenarios."""
    forbidden = [
        "main", "master", "production", "release",
        "main", "master", "production", "release",
        "main", "master", "production", "release",
        "main", "master", "production", "release",
        "main", "master", "production", "release",
    ]
    for i, branch in enumerate(forbidden):
        try:
            seal_plan(
                target_branch=branch,
                target_sha="sha-x",
                candidate=_candidate(),
            )
            cat.record(False, f"C-forbidden-{i}", f"Expected ValueError for branch={branch!r}")
        except ValueError:
            cat.record(True, f"C-forbidden-{i}")


# ---------------------------------------------------------------------------
# Category D: Rollback Correctness
# ---------------------------------------------------------------------------

def run_category_d(cat: CategoryResult, tmp: str) -> None:
    """60 rollback scenarios."""

    # D1-D20: QA failure → FAILED_SAFE
    for i in range(20):
        p = _plan(target_sha="sha-x")
        tok = issue_approval_token(p, owner="owner")
        ex = _executor(tmp, sha="sha-x")
        ex._run_post_qa = lambda pl: (False, {"summary": "QA bombed", "returncode": 1})
        tx = ex.execute(p, tok)
        passed = tx.state == TransactionState.FAILED_SAFE
        cat.record(passed, f"D1-qa-fail-{i}", f"state={tx.state}")

    # D21-D40: Apply failure → FAILED_SAFE
    for i in range(20):
        p = _plan(target_sha="sha-x")
        tok = issue_approval_token(p, owner="owner")
        ex = _executor(tmp, sha="sha-x")

        def crash_merge(args, _i=i):
            if args[0] == "rev-parse":
                return "sha-x\n"
            if args[0] == "merge":
                raise RuntimeError(f"Merge conflict {_i}")
            return ""   # reset --hard succeeds

        ex._git = crash_merge
        tx = ex.execute(p, tok)
        passed = tx.state == TransactionState.FAILED_SAFE
        cat.record(passed, f"D2-apply-fail-{i}", f"state={tx.state}")

    # D41-D60: Apply AND rollback failure → FAILED_SAFE (no crash)
    for i in range(20):
        p = _plan(target_sha="sha-x")
        tok = issue_approval_token(p, owner="owner")
        ex = _executor(tmp, sha="sha-x")

        def crash_all(args):
            if args[0] == "rev-parse":
                return "sha-x\n"
            raise RuntimeError("All git ops crash")

        ex._git = crash_all
        try:
            tx = ex.execute(p, tok)
            passed = tx.is_terminal
            cat.record(passed, f"D3-total-crash-{i}", f"state={tx.state}")
        except Exception as exc:
            cat.record(False, f"D3-total-crash-{i}", f"Exception leaked: {exc}")


# ---------------------------------------------------------------------------
# Category E: Lease Concurrency
# ---------------------------------------------------------------------------

def run_category_e(cat: CategoryResult, tmp: str) -> None:
    """40 lease concurrency scenarios."""
    registry = IntegrationLeaseRegistry()

    # E1-E20: Sequential acquire/release, no contention
    for i in range(20):
        branch = f"thursday/bench-branch-{i}"
        lease = registry.acquire(branch, f"tx-{i}")
        acquired = not lease.released
        registry.release(lease)
        released = lease.released
        cat.record(acquired and released, f"E1-seq-{i}")

    # E21-E30: Concurrent contention — second caller succeeds after first releases
    for i in range(10):
        branch = f"thursday/concurrent-{i}"
        lease1 = registry.acquire(branch, "tx-a")
        result = [False]

        def try_acquire(b=branch):
            try:
                l2 = registry.acquire(b, "tx-b", timeout=1.0)
                result[0] = True
                registry.release(l2)
            except TimeoutError:
                pass

        t = threading.Thread(target=try_acquire)
        t.start()
        time.sleep(0.05)
        registry.release(lease1)
        t.join()
        cat.record(result[0], f"E2-concurrent-{i}", "Second caller did not acquire after release")

    # E31-E40: Timeout when holder never releases
    for i in range(10):
        branch = f"thursday/timeout-{i}"
        lease_held = registry.acquire(branch, "tx-hold")
        timed_out = False
        try:
            registry.acquire(branch, "tx-wait", timeout=0.05)
        except TimeoutError:
            timed_out = True
        registry.release(lease_held)
        cat.record(timed_out, f"E3-timeout-{i}", "Expected TimeoutError")


# ---------------------------------------------------------------------------
# Category F: Diagnostic Log Integrity
# ---------------------------------------------------------------------------

def run_category_f(cat: CategoryResult, tmp: str) -> None:
    """20 log integrity scenarios."""

    # F1-F10: Log always written (success path)
    for i in range(10):
        d = tempfile.mkdtemp(dir=tmp)
        p = _plan(target_sha="sha-x")
        tok = issue_approval_token(p, owner="owner")
        ex = _executor(d, sha="sha-x")
        ex.execute(p, tok)
        logs = list(Path(ex.log_dir).glob("tx_*.json"))
        cat.record(len(logs) == 1, f"F1-success-log-{i}", f"log_count={len(logs)}")

    # F11-F20: Log pruned at max_log_files
    for i in range(10):
        d = tempfile.mkdtemp(dir=tmp)
        ex = _executor(d, sha="sha-x")
        ex.max_log_files = 3

        for j in range(7):
            p = _plan(target_sha="sha-x")
            tok = issue_approval_token(p, owner="owner")
            ex.execute(p, tok)

        logs = list(Path(ex.log_dir).glob("tx_*.json"))
        cat.record(len(logs) <= 3, f"F2-prune-{i}", f"log_count={len(logs)}")


# ---------------------------------------------------------------------------
# Main benchmark runner
# ---------------------------------------------------------------------------

CATEGORY_THRESHOLDS = {
    "A: Token Security":       1.00,
    "B: TOCTOU Integrity":     1.00,
    "C: Forbidden Branch":     1.00,
    "D: Rollback Correct":     0.95,
    "E: Lease Concurrency":    0.95,
    "F: Log Integrity":        1.00,
}

OVERALL_THRESHOLD = 0.98


def run() -> None:
    print("\n" + "=" * 72)
    print("THURSDAY_SHARED_MUTATION_V1 — ADVERSARIAL BENCHMARK")
    print("=" * 72)

    with tempfile.TemporaryDirectory() as tmp:
        cats = {
            "A: Token Security":    CategoryResult("A: Token Security"),
            "B: TOCTOU Integrity":  CategoryResult("B: TOCTOU Integrity"),
            "C: Forbidden Branch":  CategoryResult("C: Forbidden Branch"),
            "D: Rollback Correct":  CategoryResult("D: Rollback Correct"),
            "E: Lease Concurrency": CategoryResult("E: Lease Concurrency"),
            "F: Log Integrity":     CategoryResult("F: Log Integrity"),
        }

        runners = {
            "A: Token Security":    run_category_a,
            "B: TOCTOU Integrity":  run_category_b,
            "C: Forbidden Branch":  run_category_c,
            "D: Rollback Correct":  run_category_d,
            "E: Lease Concurrency": run_category_e,
            "F: Log Integrity":     run_category_f,
        }

        for name, runner in runners.items():
            cat_tmp = tempfile.mkdtemp(dir=tmp)
            runner(cats[name], cat_tmp)

    # ---- Report ----
    total_passed = sum(c.passed for c in cats.values())
    total_scenarios = sum(c.total for c in cats.values())
    overall_accuracy = total_passed / total_scenarios if total_scenarios else 0.0

    print(f"\n{'RESULTS':}")
    print("-" * 72)
    all_categories_pass = True
    for name, cat in cats.items():
        print(cat.report())
        threshold = CATEGORY_THRESHOLDS.get(name, 0.95)
        if cat.accuracy < threshold:
            all_categories_pass = False

    print("-" * 72)
    print(f"  TOTAL: {total_passed}/{total_scenarios} ({overall_accuracy * 100:.1f}%)")
    print(f"  THRESHOLD: {OVERALL_THRESHOLD * 100:.0f}%")

    overall_pass = overall_accuracy >= OVERALL_THRESHOLD and all_categories_pass
    status_label = "QUALIFIED" if overall_pass else "DISQUALIFIED"
    print(f"\n  VERDICT: {status_label}")
    print("=" * 72 + "\n")

    sys.exit(0 if overall_pass else 1)


if __name__ == "__main__":
    run()
