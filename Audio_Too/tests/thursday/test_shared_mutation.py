"""Thursday V2-G — Approval-Gated Shared Mutation Tests.

Coverage
--------
1. Integration contract correctness (models)
   1a. Sealed plan digest is stable and changes on any field mutation
   1b. ApprovalToken verify() fails on: expired, consumed, plan-digest mismatch, SHA mismatch
   1c. Token.consume() is idempotent-safe (raises on second call)
   1d. IntegrationPlan rejects forbidden branches (main, master, production)
   1e. IntegrationTransaction enforces valid state transitions only
   1f. candidate_substitution_attack: different candidate produces different digest

2. SharedExecutor pre-flight guards (no git needed)
   2a. Expired token aborts before acquiring lease
   2b. Consumed token replay is rejected
   2c. Candidate/plan substitution attack rejected (digest mismatch)

3. SharedExecutor TOCTOU + lease
   3a. SHA drift detected before lease acquisition → ABORTED
   3b. SHA drift detected after lease acquisition (double-check) → ABORTED
   3c. Concurrent lease acquisition blocks second caller
   3d. Lease is always released (even on exception)

4. SharedExecutor apply + QA + rollback (mocked git)
   4a. Successful fast-forward → COMPLETED
   4b. Successful three-way-merge → COMPLETED
   4c. QA failure triggers rollback → FAILED_SAFE
   4d. Apply failure triggers rollback → FAILED_SAFE
   4e. Rollback failure records FAILED_SAFE with critical note (no crash)

5. Diagnostic log integrity
   5a. Log is always written (success and failure paths)
   5b. Old logs are pruned beyond max_log_files
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from thursday.integration_models import (
    ApprovalToken,
    IntegrationCandidate,
    IntegrationPlan,
    IntegrationTransaction,
    TransactionState,
    create_transaction,
    issue_approval_token,
    seal_plan,
)
from thursday.shared_executor import (
    IntegrationLeaseRegistry,
    SharedExecutor,
    SharedMutationError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate(
    task_id: str = "task-001",
    source_sha: str = "abc123",
    candidate_sha: str = "def456",
    tests_passed: bool = True,
) -> IntegrationCandidate:
    return IntegrationCandidate(
        task_id=task_id,
        source_sha=source_sha,
        candidate_branch=f"thursday/task/{task_id}",
        candidate_sha=candidate_sha,
        diff_summary="Minor doc update.",
        tests_passed=tests_passed,
        qa_receipt={"timestamp": 0.0},
    )


def _make_plan(
    candidate: IntegrationCandidate | None = None,
    target_branch: str = "thursday/integration-staging",
    target_sha: str = "abc123",
    apply_method: str = "fast_forward",
    post_test_cmd: tuple[str, ...] = (),
) -> IntegrationPlan:
    cand = candidate or _make_candidate()
    return seal_plan(
        target_branch=target_branch,
        target_sha=target_sha,
        candidate=cand,
        apply_method=apply_method,
        post_test_cmd=post_test_cmd,
    )


def _make_executor(tmp_dir: str) -> SharedExecutor:
    log_dir = os.path.join(tmp_dir, "logs")
    return SharedExecutor(repo_path=tmp_dir, log_dir=log_dir)


def _mock_executor_git(executor: SharedExecutor, sha: str = "abc123"):
    """Patch _git to return sha for rev-parse and succeed for merge/reset."""
    def fake_git(args: list[str]) -> str:
        if args[0] == "rev-parse":
            return sha + "\n"
        if args[0] in ("merge", "reset"):
            return ""
        return ""
    executor._git = fake_git


# ---------------------------------------------------------------------------
# Section 1: Integration contract correctness
# ---------------------------------------------------------------------------

class TestIntegrationModels(unittest.TestCase):

    # 1a — Plan digest stability and sensitivity
    def test_plan_digest_is_stable(self):
        plan = _make_plan()
        d1 = plan.compute_digest()
        d2 = plan.compute_digest()
        self.assertEqual(d1, d2)
        self.assertEqual(d1, plan.plan_digest)

    def test_plan_digest_changes_on_field_mutation(self):
        plan = _make_plan(target_sha="aaabbb")
        plan_different_sha = _make_plan(target_sha="cccddd")
        self.assertNotEqual(plan.plan_digest, plan_different_sha.plan_digest)

    def test_plan_digest_changes_on_candidate_change(self):
        cand_a = _make_candidate(candidate_sha="sha-a")
        cand_b = _make_candidate(candidate_sha="sha-b")
        plan_a = _make_plan(candidate=cand_a)
        plan_b = _make_plan(candidate=cand_b)
        self.assertNotEqual(plan_a.plan_digest, plan_b.plan_digest)

    # 1b — Token verify
    def test_token_valid(self):
        plan = _make_plan()
        token = issue_approval_token(plan, owner="owner")
        ok, reason = token.verify(plan)
        self.assertTrue(ok, reason)

    def test_token_expired(self):
        plan = _make_plan()
        token = issue_approval_token(plan, owner="owner", ttl_seconds=0)
        ok, reason = token.verify(plan, now=time.time() + 10)
        self.assertFalse(ok)
        self.assertIn("expired", reason.lower())

    def test_token_plan_digest_mismatch(self):
        plan_a = _make_plan(target_sha="sha-a")
        plan_b = _make_plan(target_sha="sha-b")
        token = issue_approval_token(plan_a, owner="owner")
        ok, reason = token.verify(plan_b)
        self.assertFalse(ok)
        self.assertIn("digest mismatch", reason.lower())

    def test_token_target_sha_mismatch(self):
        plan = _make_plan(target_sha="sha-real")
        token = issue_approval_token(plan, owner="owner")
        plan_drifted = _make_plan(target_sha="sha-different")
        # Manually align digest to isolate SHA check
        token_drifted = dataclasses.replace(
            token,
            plan_digest=plan_drifted.plan_digest,
            target_sha="sha-real",  # token bound to old SHA
        )
        ok, reason = token_drifted.verify(plan_drifted)
        self.assertFalse(ok)
        self.assertIn("sha mismatch", reason.lower())

    def test_token_consumed_rejected(self):
        plan = _make_plan()
        token = issue_approval_token(plan, owner="owner")
        token.consume()
        ok, reason = token.verify(plan)
        self.assertFalse(ok)
        self.assertIn("consumed", reason.lower())

    # 1c — Token.consume() idempotent safety
    def test_token_consume_idempotent_raises(self):
        plan = _make_plan()
        token = issue_approval_token(plan, owner="owner")
        token.consume()
        with self.assertRaises(ValueError):
            token.consume()

    # 1d — Forbidden branch guard
    def test_plan_rejects_main(self):
        with self.assertRaises(ValueError):
            _make_plan(target_branch="main")

    def test_plan_rejects_master(self):
        with self.assertRaises(ValueError):
            _make_plan(target_branch="master")

    def test_plan_rejects_production(self):
        with self.assertRaises(ValueError):
            _make_plan(target_branch="production")

    def test_plan_accepts_staging(self):
        plan = _make_plan(target_branch="thursday/integration-staging")
        self.assertIsNotNone(plan.plan_id)

    # 1e — Transaction state machine
    def test_valid_transitions(self):
        plan = _make_plan()
        token = issue_approval_token(plan, owner="owner")
        tx = create_transaction(plan, token)
        self.assertEqual(tx.state, TransactionState.PREPARED)
        tx.update_state(TransactionState.APPROVED)
        tx.update_state(TransactionState.APPLYING)
        tx.update_state(TransactionState.VALIDATING)
        tx.update_state(TransactionState.COMPLETED)
        self.assertTrue(tx.is_terminal)

    def test_invalid_transition_raises(self):
        plan = _make_plan()
        token = issue_approval_token(plan, owner="owner")
        tx = create_transaction(plan, token)
        with self.assertRaises(ValueError):
            tx.update_state(TransactionState.COMPLETED)  # skip steps

    def test_terminal_state_no_further_transitions(self):
        plan = _make_plan()
        token = issue_approval_token(plan, owner="owner")
        tx = create_transaction(plan, token)
        tx.update_state(TransactionState.ABORTED)
        with self.assertRaises(ValueError):
            tx.update_state(TransactionState.APPROVED)

    # 1f — Candidate substitution attack
    def test_candidate_substitution_changes_plan_digest(self):
        legit = _make_candidate(task_id="real", candidate_sha="sha-legit")
        attack = _make_candidate(task_id="real", candidate_sha="sha-malicious")
        plan_legit = _make_plan(candidate=legit)
        plan_attack = _make_plan(candidate=attack)
        self.assertNotEqual(plan_legit.plan_digest, plan_attack.plan_digest)

    def test_candidate_diff_hash_sensitive_to_sha(self):
        c1 = _make_candidate(candidate_sha="aaa")
        c2 = _make_candidate(candidate_sha="bbb")
        self.assertNotEqual(c1.diff_hash(), c2.diff_hash())


# ---------------------------------------------------------------------------
# Section 2: SharedExecutor pre-flight guards (no git needed)
# ---------------------------------------------------------------------------

class TestSharedExecutorPreflightGuards(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def _exec_with_fake_sha(self, sha: str) -> SharedExecutor:
        ex = _make_executor(self._tmp)
        _mock_executor_git(ex, sha=sha)
        return ex

    def test_expired_token_aborts_before_lease(self):
        plan = _make_plan(target_sha="sha-x")
        token = issue_approval_token(plan, owner="owner", ttl_seconds=0)
        ex = self._exec_with_fake_sha("sha-x")
        # Expire the token
        token = dataclasses.replace(token, expires_at=time.time() - 1)
        tx = ex.execute(plan, token)
        self.assertEqual(tx.state, TransactionState.ABORTED)
        self.assertIn("expired", tx.events[-1][2].lower())

    def test_consumed_token_replay_rejected(self):
        plan = _make_plan(target_sha="sha-x")
        token = issue_approval_token(plan, owner="owner")
        token.consume()
        ex = self._exec_with_fake_sha("sha-x")
        tx = ex.execute(plan, token)
        self.assertEqual(tx.state, TransactionState.ABORTED)
        self.assertIn("consumed", tx.events[-1][2].lower())

    def test_plan_substitution_attack_rejected(self):
        """Token issued for plan_a cannot be replayed for plan_b."""
        plan_a = _make_plan(target_sha="sha-a")
        plan_b = _make_plan(target_sha="sha-b")
        token_for_a = issue_approval_token(plan_a, owner="owner")
        ex = self._exec_with_fake_sha("sha-b")
        tx = ex.execute(plan_b, token_for_a)
        self.assertEqual(tx.state, TransactionState.ABORTED)
        self.assertIn("mismatch", tx.events[-1][2].lower())


# ---------------------------------------------------------------------------
# Section 3: TOCTOU + lease
# ---------------------------------------------------------------------------

class TestTOCTOUAndLease(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def test_sha_drift_before_lease_causes_abort(self):
        plan = _make_plan(target_sha="sha-sealed")
        token = issue_approval_token(plan, owner="owner")
        ex = _make_executor(self._tmp)
        _mock_executor_git(ex, sha="sha-drifted")   # HEAD has moved
        tx = ex.execute(plan, token)
        self.assertEqual(tx.state, TransactionState.ABORTED)
        self.assertIn("drifted", tx.events[-1][2].lower())

    def test_sha_drift_after_lock_causes_abort(self):
        """Simulate race: initial rev-parse matches, second (post-lock) does not."""
        plan = _make_plan(target_sha="sha-sealed")
        token = issue_approval_token(plan, owner="owner")
        ex = _make_executor(self._tmp)
        call_count = [0]

        def fake_git_race(args: list[str]) -> str:
            if args[0] == "rev-parse":
                call_count[0] += 1
                # First call matches, second call returns drifted SHA
                return "sha-sealed\n" if call_count[0] == 1 else "sha-drifted\n"
            return ""

        ex._git = fake_git_race
        tx = ex.execute(plan, token)
        self.assertEqual(tx.state, TransactionState.ABORTED)

    def test_concurrent_lease_acquisition_blocked(self):
        """Second executor blocks until first releases."""
        registry = IntegrationLeaseRegistry()
        branch = "thursday/integration-staging"
        lease1 = registry.acquire(branch, "tx-001")

        result: list[bool] = []

        def try_acquire():
            try:
                registry.acquire(branch, "tx-002", timeout=0.5)
                result.append(True)
            except TimeoutError:
                result.append(False)

        t = threading.Thread(target=try_acquire)
        t.start()
        time.sleep(0.1)
        registry.release(lease1)
        t.join()
        # After release, second caller should succeed
        self.assertTrue(result[0])

    def test_lease_always_released_on_exception(self):
        plan = _make_plan(target_sha="sha-x")
        token = issue_approval_token(plan, owner="owner")
        ex = _make_executor(self._tmp)

        def crash_git(args: list[str]) -> str:
            if args[0] == "rev-parse":
                return "sha-x\n"
            raise RuntimeError("simulated git crash")

        ex._git = crash_git
        tx = ex.execute(plan, token)
        # Regardless of crash, the lease registry should be empty
        self.assertNotIn("thursday/integration-staging", ex.lease_registry._leases)
        self.assertTrue(tx.is_terminal)


# ---------------------------------------------------------------------------
# Section 4: Apply + QA + rollback
# ---------------------------------------------------------------------------

class TestApplyQARollback(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def _make_ex_sha(self, sha: str = "sha-x") -> tuple[SharedExecutor, IntegrationPlan, ApprovalToken]:
        plan = _make_plan(target_sha=sha)
        token = issue_approval_token(plan, owner="owner")
        ex = _make_executor(self._tmp)
        _mock_executor_git(ex, sha=sha)
        return ex, plan, token

    def test_fast_forward_success_completed(self):
        ex, plan, token = self._make_ex_sha()
        tx = ex.execute(plan, token)
        self.assertEqual(tx.state, TransactionState.COMPLETED)

    def test_three_way_merge_success_completed(self):
        plan = _make_plan(target_sha="sha-x", apply_method="three_way_merge")
        token = issue_approval_token(plan, owner="owner")
        ex = _make_executor(self._tmp)
        _mock_executor_git(ex, sha="sha-x")
        tx = ex.execute(plan, token)
        self.assertEqual(tx.state, TransactionState.COMPLETED)

    def test_qa_failure_triggers_rollback_failed_safe(self):
        # post_test_cmd that always exits non-zero
        plan = _make_plan(target_sha="sha-x", post_test_cmd=("false",))
        token = issue_approval_token(plan, owner="owner")
        ex = _make_executor(self._tmp)
        _mock_executor_git(ex, sha="sha-x")

        # patch _run_post_qa to return failure
        ex._run_post_qa = lambda p: (False, {"summary": "QA test failed", "returncode": 1})
        tx = ex.execute(plan, token)
        self.assertEqual(tx.state, TransactionState.FAILED_SAFE)
        self.assertIn("QA", tx.rollback_reason)

    def test_apply_failure_triggers_rollback_failed_safe(self):
        plan = _make_plan(target_sha="sha-x")
        token = issue_approval_token(plan, owner="owner")
        ex = _make_executor(self._tmp)

        call_count = [0]
        def crash_on_merge(args: list[str]) -> str:
            if args[0] == "rev-parse":
                return "sha-x\n"
            if args[0] == "merge":
                raise RuntimeError("Simulated merge conflict")
            return ""   # reset --hard succeeds

        ex._git = crash_on_merge
        tx = ex.execute(plan, token)
        self.assertEqual(tx.state, TransactionState.FAILED_SAFE)

    def test_rollback_failure_records_failed_safe_without_crash(self):
        plan = _make_plan(target_sha="sha-x")
        token = issue_approval_token(plan, owner="owner")
        ex = _make_executor(self._tmp)

        def crash_all_writes(args: list[str]) -> str:
            if args[0] == "rev-parse":
                return "sha-x\n"
            raise RuntimeError("All git ops fail")

        ex._git = crash_all_writes
        # This should not propagate — FAILED_SAFE must be reached
        tx = ex.execute(plan, token)
        self.assertTrue(tx.is_terminal)
        self.assertEqual(tx.state, TransactionState.FAILED_SAFE)


# ---------------------------------------------------------------------------
# Section 5: Diagnostic log integrity
# ---------------------------------------------------------------------------

class TestDiagnosticLogs(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def test_log_written_on_success(self):
        plan = _make_plan(target_sha="sha-x")
        token = issue_approval_token(plan, owner="owner")
        ex = _make_executor(self._tmp)
        _mock_executor_git(ex, sha="sha-x")
        tx = ex.execute(plan, token)
        logs = list(Path(ex.log_dir).glob("tx_*.json"))
        self.assertEqual(len(logs), 1)

    def test_log_written_on_abort(self):
        plan = _make_plan(target_sha="sha-x")
        token = issue_approval_token(plan, owner="owner")
        token.consume()
        ex = _make_executor(self._tmp)
        _mock_executor_git(ex, sha="sha-x")
        ex.execute(plan, token)
        logs = list(Path(ex.log_dir).glob("tx_*.json"))
        self.assertEqual(len(logs), 1)

    def test_log_pruned_beyond_max(self):
        ex = _make_executor(self._tmp)
        ex.max_log_files = 3
        _mock_executor_git(ex, sha="sha-x")

        for _ in range(5):
            plan = _make_plan(target_sha="sha-x")
            token = issue_approval_token(plan, owner="owner")
            ex.execute(plan, token)

        logs = list(Path(ex.log_dir).glob("tx_*.json"))
        self.assertLessEqual(len(logs), 3)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
