"""Approval-Gated Shared Mutation Executor for Thursday V2-G.

SharedExecutor is responsible for:
1. Verifying the approval token (single-use, plan-bound, SHA-bound).
2. Performing a TOCTOU check — aborting if the target branch has drifted
   since the plan was sealed.
3. Acquiring an exclusive integration lease so concurrent writers cannot
   race against the same target branch.
4. Recording the pre-mutation snapshot SHA (rollback anchor).
5. Applying the integration candidate via safe argument-array git operations
   (never free-form shell strings).
6. Running the post-integration QA test suite.
7. Committing the transaction as COMPLETED on full success.
8. Executing a deterministic rollback (git reset --hard <pre_sha>) on any
   failure and completing in FAILED_SAFE state.
9. Releasing the exclusive lease regardless of outcome.
10. Retaining a bounded diagnostic log on disk.

Authority Level
---------------
STAGE 3 — APPROVAL-GATED SHARED MUTATION.
* No autonomous merges to main/master/production/release.
* No free-form shell access from specialists.
* Token is consumed on first successful verification — replay is blocked.
* All git operations use subprocess with argument arrays and no shell=True.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from thursday.integration_models import (
    ApprovalToken,
    IntegrationPlan,
    IntegrationTransaction,
    TransactionState,
    create_transaction,
)


# ---------------------------------------------------------------------------
# Exclusive Integration Lease
# ---------------------------------------------------------------------------

@dataclass
class IntegrationLease:
    """Exclusive lock on a target branch for the duration of one transaction."""
    lease_id:      str
    target_branch: str
    transaction_id: str
    acquired_at:   float
    released:      bool = False

    def release(self) -> None:
        self.released = True


class IntegrationLeaseRegistry:
    """Thread-safe registry of exclusive integration leases per target branch.

    At most one active lease per (target_branch) at any moment. A second
    attempt blocks until the holder releases or the timeout expires.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._leases: dict[str, IntegrationLease] = {}

    def acquire(self, target_branch: str, transaction_id: str, timeout: float = 30.0) -> IntegrationLease:
        """Acquire exclusive lease for target_branch. Raises on timeout."""
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                existing = self._leases.get(target_branch)
                if existing is None or existing.released:
                    lease = IntegrationLease(
                        lease_id=str(uuid.uuid4()),
                        target_branch=target_branch,
                        transaction_id=transaction_id,
                        acquired_at=time.time(),
                    )
                    self._leases[target_branch] = lease
                    return lease
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Could not acquire integration lease for branch {target_branch!r} "
                    f"within {timeout}s. Concurrent writer may be active."
                )
            time.sleep(0.05)

    def release(self, lease: IntegrationLease) -> None:
        with self._lock:
            lease.release()
            if self._leases.get(lease.target_branch) is lease:
                del self._leases[lease.target_branch]


# ---------------------------------------------------------------------------
# Shared Executor
# ---------------------------------------------------------------------------

class SharedMutationError(RuntimeError):
    """Raised when a mutation is rejected before any shared state is touched."""


class SharedExecutor:
    """Executes approval-gated integrations onto shared (non-sandbox) branches.

    Parameters
    ----------
    repo_path : str | Path
        Absolute path to the git repository root.
    log_dir : str | Path
        Directory for per-transaction diagnostic logs. Bounded to 50 files.
    max_log_files : int
        Maximum number of diagnostic log files to retain.
    lease_registry : IntegrationLeaseRegistry
        Shared lease registry (pass the same instance to all executors in
        a process to guarantee mutual exclusion).
    """

    STAGE = "STAGE_3_APPROVAL_GATED_SHARED_MUTATION"

    def __init__(
        self,
        repo_path: str | Path,
        log_dir: str | Path,
        *,
        lease_registry: Optional[IntegrationLeaseRegistry] = None,
        max_log_files: int = 50,
    ) -> None:
        self.repo_path = Path(repo_path)
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.lease_registry = lease_registry or IntegrationLeaseRegistry()
        self.max_log_files = max_log_files

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(self, plan: IntegrationPlan, token: ApprovalToken) -> IntegrationTransaction:
        """Attempt an approval-gated integration. Returns the final transaction.

        The transaction reaches COMPLETED on full success, ABORTED if any
        pre-flight check fails (no shared state touched), or FAILED_SAFE if
        the integration partially executed but was rolled back cleanly.
        """
        tx = create_transaction(plan, token)
        lease: Optional[IntegrationLease] = None

        try:
            # ---- Step 1: Verify and consume approval token ----
            self._verify_token(tx)

            # ---- Step 2: TOCTOU — check target branch has not drifted ----
            actual_sha = self._resolve_branch_sha(plan.target_branch)
            self._check_toctou(tx, plan.target_sha, actual_sha)

            # ---- Step 3: Acquire exclusive integration lease ----
            lease = self.lease_registry.acquire(plan.target_branch, tx.transaction_id)
            tx.log(f"Exclusive lease {lease.lease_id} acquired for branch {plan.target_branch!r}.")

            # ---- Step 4: Re-verify SHA under lease (double-check after lock) ----
            actual_sha_locked = self._resolve_branch_sha(plan.target_branch)
            if actual_sha_locked != plan.target_sha:
                tx.update_state(TransactionState.ABORTED, reason=(
                    f"TOCTOU: Branch drifted between lease acquire and post-lock check. "
                    f"Expected {plan.target_sha[:12]}, found {actual_sha_locked[:12]}."
                ))
                return tx

            # ---- Step 5: Snapshot pre-mutation SHA ----
            tx.pre_sha = actual_sha_locked
            tx.log(f"Pre-mutation snapshot SHA recorded: {tx.pre_sha[:12]}…")

            # ---- Step 6: Transition APPROVED → APPLYING ----
            tx.update_state(TransactionState.APPLYING, reason="Token verified, TOCTOU clear, applying.")

            # ---- Step 7: Apply the candidate ----
            self._apply_candidate(tx, plan)

            # ---- Step 8: Record post-apply SHA ----
            tx.post_sha = self._resolve_branch_sha(plan.target_branch)
            tx.log(f"Post-apply SHA: {tx.post_sha[:12]}…")

            # ---- Step 9: Run post-integration QA ----
            tx.update_state(TransactionState.VALIDATING, reason="Application complete, running QA.")
            qa_ok, qa_result = self._run_post_qa(plan)
            tx.qa_result = qa_result

            if qa_ok:
                tx.update_state(TransactionState.COMPLETED, reason="QA passed — transaction complete.")
            else:
                tx.rollback_reason = f"Post-QA failed: {qa_result.get('summary', 'unknown')}"
                self._rollback(tx, plan)

        except SharedMutationError as exc:
            # Pre-flight rejection — no shared state was modified.
            if not tx.is_terminal:
                tx.update_state(TransactionState.ABORTED, reason=str(exc))
        except Exception as exc:  # noqa: BLE001 — safety catch; never silently succeed
            tx.log(f"Unexpected error: {exc}")
            if tx.state == TransactionState.APPLYING:
                tx.rollback_reason = f"Unexpected error during apply: {exc}"
                try:
                    self._rollback(tx, plan)
                except Exception as rb_exc:
                    tx.log(f"CRITICAL: Rollback also failed: {rb_exc}")
                    if not tx.is_terminal:
                        tx.update_state(TransactionState.FAILED_SAFE, reason="Rollback failed; manual recovery required.")
            elif not tx.is_terminal:
                tx.update_state(TransactionState.ABORTED, reason=str(exc))
        finally:
            if lease is not None:
                self.lease_registry.release(lease)
                tx.log(f"Integration lease {lease.lease_id} released.")
            self._write_diagnostic_log(tx)
            self._prune_old_logs()

        return tx

    # ------------------------------------------------------------------
    # Internal steps
    # ------------------------------------------------------------------

    def _verify_token(self, tx: IntegrationTransaction) -> None:
        """Verify and immediately consume the approval token."""
        ok, reason = tx.token.verify(tx.plan)
        if not ok:
            raise SharedMutationError(f"Approval token rejected: {reason}")
        tx.token.consume()
        tx.update_state(TransactionState.APPROVED, reason=f"Token {tx.token.token_id} verified and consumed.")

    def _resolve_branch_sha(self, branch: str) -> str:
        """Return the current HEAD SHA of the branch (local git reference)."""
        result = self._git(["rev-parse", f"refs/heads/{branch}"])
        return result.strip()

    def _check_toctou(self, tx: IntegrationTransaction, expected_sha: str, actual_sha: str) -> None:
        """Abort if the target branch has drifted since plan was sealed."""
        if actual_sha != expected_sha:
            raise SharedMutationError(
                f"TOCTOU abort: target branch {tx.plan.target_branch!r} has drifted. "
                f"Plan sealed at {expected_sha[:12]}…, current HEAD is {actual_sha[:12]}…. "
                "Re-seal the plan against the current SHA and re-request approval."
            )
        tx.log(f"TOCTOU check passed: SHA {actual_sha[:12]}… matches plan.")

    def _apply_candidate(self, tx: IntegrationTransaction, plan: IntegrationPlan) -> None:
        """Apply the integration candidate using safe git argument arrays."""
        if plan.apply_method == "fast_forward":
            self._git(["merge", "--ff-only", plan.candidate.candidate_sha])
        elif plan.apply_method == "three_way_merge":
            self._git([
                "merge",
                "--no-ff",
                "-m", f"thursday/v2g: integrate task {plan.candidate.task_id} [{plan.plan_id[:8]}]",
                plan.candidate.candidate_sha,
            ])
        else:
            raise SharedMutationError(f"Unknown apply_method: {plan.apply_method!r}")
        tx.log(f"Candidate {plan.candidate.candidate_sha[:12]}… applied via {plan.apply_method}.")

    def _run_post_qa(self, plan: IntegrationPlan) -> tuple[bool, dict[str, Any]]:
        """Run the plan's post_test_cmd and return (passed, result_dict)."""
        if not plan.post_test_cmd:
            return True, {"summary": "No post-QA command specified — skipped.", "returncode": 0}

        try:
            proc = subprocess.run(
                list(plan.post_test_cmd),
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=120,
            )
            passed = proc.returncode == 0
            return passed, {
                "returncode": proc.returncode,
                "stdout":     proc.stdout[-4096:],
                "stderr":     proc.stderr[-4096:],
                "summary":    "QA passed." if passed else f"QA failed (exit {proc.returncode}).",
            }
        except subprocess.TimeoutExpired:
            return False, {"summary": "QA timed out after 120s.", "returncode": -1}
        except Exception as exc:
            return False, {"summary": f"QA launch failed: {exc}", "returncode": -2}

    def _rollback(self, tx: IntegrationTransaction, plan: IntegrationPlan) -> None:
        """Deterministic rollback: git reset --hard to the pre-mutation snapshot."""
        tx.update_state(TransactionState.ROLLING_BACK, reason=tx.rollback_reason or "Rolling back.")
        if not tx.pre_sha:
            tx.log("CRITICAL: No pre_sha snapshot recorded — cannot rollback deterministically.")
            tx.update_state(TransactionState.FAILED_SAFE, reason="No rollback anchor available.")
            return
        try:
            self._git(["reset", "--hard", tx.pre_sha])
            tx.log(f"Rollback complete: branch reset to {tx.pre_sha[:12]}…")
            tx.update_state(TransactionState.FAILED_SAFE, reason="Rolled back safely to pre-mutation snapshot.")
        except Exception as exc:
            tx.log(f"CRITICAL: git reset --hard failed: {exc}")
            tx.update_state(TransactionState.FAILED_SAFE, reason=f"Rollback git error: {exc}")

    def _git(self, args: list[str]) -> str:
        """Execute a git command with an argument array. Never shell=True."""
        cmd = ["git"] + args
        result = subprocess.run(
            cmd,
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout

    # ------------------------------------------------------------------
    # Diagnostic log management
    # ------------------------------------------------------------------

    def _write_diagnostic_log(self, tx: IntegrationTransaction) -> None:
        log_file = self.log_dir / f"tx_{tx.transaction_id}.json"
        payload = {
            "transaction_id":  tx.transaction_id,
            "plan_id":         tx.plan.plan_id,
            "target_branch":   tx.plan.target_branch,
            "plan_digest":     tx.plan.plan_digest,
            "token_id":        tx.token.token_id,
            "final_state":     tx.state,
            "pre_sha":         tx.pre_sha,
            "post_sha":        tx.post_sha,
            "rollback_reason": tx.rollback_reason,
            "qa_result":       tx.qa_result,
            "events":          tx.events,
        }
        tmp = str(log_file) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp, log_file)

    def _prune_old_logs(self) -> None:
        """Remove oldest diagnostic logs beyond the max_log_files bound."""
        logs = sorted(self.log_dir.glob("tx_*.json"), key=lambda p: p.stat().st_mtime)
        excess = len(logs) - self.max_log_files
        for old in logs[:excess]:
            try:
                old.unlink()
            except OSError:
                pass


__all__ = [
    "IntegrationLease",
    "IntegrationLeaseRegistry",
    "SharedMutationError",
    "SharedExecutor",
]
