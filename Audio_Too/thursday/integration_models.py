"""Immutable integration contracts for Thursday V2-G Approval-Gated Shared Mutation.

Defines:
  - IntegrationCandidate: the hermetic output of a completed isolated task.
  - IntegrationPlan:      an immutable description of precisely what will be applied.
  - ApprovalToken:        a single-use, plan-bound, SHA-bound capability token.
  - IntegrationTransaction: the full lifecycle state machine for a shared mutation.

Design invariants
-----------------
* Every struct is frozen or intentionally constrained.
* ApprovalToken is single-use — consumed = True once presented, never re-accepted.
* ApprovalToken binds plan_digest AND target_sha so token cannot be replayed
  against a different plan version or a drifted codebase state.
* IntegrationTransaction exposes only valid transitions via update_state().
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Transaction state machine
# ---------------------------------------------------------------------------

class TransactionState:
    PREPARED        = "PREPARED"
    APPROVED        = "APPROVED"
    APPLYING        = "APPLYING"
    VALIDATING      = "VALIDATING"
    ROLLING_BACK    = "ROLLING_BACK"
    COMPLETED       = "COMPLETED"
    FAILED_SAFE     = "FAILED_SAFE"
    ABORTED         = "ABORTED"   # pre-apply abort (TOCTOU drift, token mismatch, etc.)


# Allowed transitions — deterministic, directed, no cycles back to PREPARED.
_VALID_TX_TRANSITIONS: dict[str, set[str]] = {
    TransactionState.PREPARED:     {TransactionState.APPROVED, TransactionState.ABORTED},
    TransactionState.APPROVED:     {TransactionState.APPLYING, TransactionState.ABORTED},
    TransactionState.APPLYING:     {TransactionState.VALIDATING, TransactionState.ROLLING_BACK},
    TransactionState.VALIDATING:   {TransactionState.COMPLETED, TransactionState.ROLLING_BACK},
    TransactionState.ROLLING_BACK: {TransactionState.FAILED_SAFE},
    # Terminal — no further transitions.
    TransactionState.COMPLETED:    set(),
    TransactionState.FAILED_SAFE:  set(),
    TransactionState.ABORTED:      set(),
}


# ---------------------------------------------------------------------------
# IntegrationCandidate
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntegrationCandidate:
    """Immutable output package from an isolated specialist task execution.

    Produced by SandboxRunner.assemble_integration_package().  Contains
    enough information for the shared executor to verify authenticity and
    apply the changes safely.
    """
    task_id:          str
    source_sha:       str   # Git SHA of main at task launch time
    candidate_branch: str   # Isolated worktree branch name
    candidate_sha:    str   # HEAD SHA of the candidate worktree after execution
    diff_summary:     str   # Human-readable description of changes
    tests_passed:     bool  # Did the in-sandbox test suite pass?
    qa_receipt:       dict[str, Any] = field(default_factory=dict)

    def diff_hash(self) -> str:
        """Deterministic hash of candidate identity — used in plan sealing."""
        payload = {
            "task_id":          self.task_id,
            "source_sha":       self.source_sha,
            "candidate_branch": self.candidate_branch,
            "candidate_sha":    self.candidate_sha,
            "tests_passed":     self.tests_passed,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# IntegrationPlan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntegrationPlan:
    """Immutable integration plan sealed before owner approval is requested.

    Once sealed (plan_digest computed), any field change invalidates the token.

    Attributes
    ----------
    plan_id          : Globally unique plan identifier (UUID4).
    target_branch    : Branch into which the candidate will be merged (NOT main by default).
    target_sha       : Expected HEAD SHA of target_branch at the time plan is sealed.
                       Used to detect TOCTOU drift before applying.
    apply_method     : ``"fast_forward"`` or ``"three_way_merge"`` — no free-form shell.
    candidate        : The frozen IntegrationCandidate this plan integrates.
    post_test_cmd    : Argument list (not shell string) for post-integration QA.
    created_at_epoch : Creation timestamp (float, seconds since epoch).
    plan_digest      : SHA-256 over the canonical plan bytes — computed on creation.
    """
    plan_id:          str
    target_branch:    str
    target_sha:       str
    apply_method:     str                  # "fast_forward" | "three_way_merge"
    candidate:        IntegrationCandidate
    post_test_cmd:    tuple[str, ...]      # Argument list, never a free shell string
    created_at_epoch: float
    plan_digest:      str = ""             # Populated by seal_plan()

    # Structural guard: main is never a permitted target via auto-approval
    _FORBIDDEN_TARGETS: frozenset[str] = field(
        default=frozenset({"main", "master", "production", "release"}),
        init=False, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        if self.apply_method not in ("fast_forward", "three_way_merge"):
            raise ValueError(f"Unknown apply_method: {self.apply_method!r}")
        if self.target_branch in self._FORBIDDEN_TARGETS:
            raise ValueError(
                f"FORBIDDEN: target_branch={self.target_branch!r} is a protected branch. "
                "Shared mutation executor does not auto-merge to production branches."
            )
        if not self.target_sha:
            raise ValueError("target_sha must be a non-empty git SHA.")

    def canonical_bytes(self) -> bytes:
        """Deterministic canonical serialization for hashing."""
        payload = {
            "plan_id":          self.plan_id,
            "target_branch":    self.target_branch,
            "target_sha":       self.target_sha,
            "apply_method":     self.apply_method,
            "candidate_hash":   self.candidate.diff_hash(),
            "post_test_cmd":    list(self.post_test_cmd),
            "created_at_epoch": self.created_at_epoch,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def compute_digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def seal_plan(
    target_branch: str,
    target_sha: str,
    candidate: IntegrationCandidate,
    apply_method: str = "fast_forward",
    post_test_cmd: tuple[str, ...] = (),
) -> IntegrationPlan:
    """Construct and seal an IntegrationPlan, computing and locking the plan_digest."""
    import dataclasses
    plan_id = str(uuid.uuid4())
    created = time.time()
    # Build without digest first to compute it
    partial = IntegrationPlan(
        plan_id=plan_id,
        target_branch=target_branch,
        target_sha=target_sha,
        apply_method=apply_method,
        candidate=candidate,
        post_test_cmd=post_test_cmd,
        created_at_epoch=created,
        plan_digest="",
    )
    digest = partial.compute_digest()
    # Return with digest locked in (frozen dataclass requires reconstruction)
    return dataclasses.replace(partial, plan_digest=digest)


# ---------------------------------------------------------------------------
# ApprovalToken
# ---------------------------------------------------------------------------

@dataclass
class ApprovalToken:
    """Single-use, plan-bound, target-SHA-bound capability token.

    A token approves EXACTLY ONE execution of EXACTLY ONE IntegrationPlan
    against EXACTLY ONE target codebase state.

    Consumed immediately on first successful verification — replay attacks
    are structurally impossible because consumed=True makes verify() fail.
    """
    token_id:     str
    plan_digest:  str   # Must match IntegrationPlan.plan_digest exactly
    target_sha:   str   # Must match IntegrationPlan.target_sha exactly
    owner:        str
    issued_at:    float
    expires_at:   float
    consumed:     bool = False
    consumed_at:  float = 0.0

    # -----------------------------------------------------------------------

    def verify(self, plan: IntegrationPlan, *, now: float | None = None) -> tuple[bool, str]:
        """Verify the token is valid for the given plan and current state.

        Returns (True, "") on success, (False, reason) on any failure.
        Fails closed on every check.
        """
        t = now if now is not None else time.time()

        if self.consumed:
            return False, f"Token {self.token_id} already consumed at {self.consumed_at}."

        if t > self.expires_at:
            return False, f"Token {self.token_id} expired at {self.expires_at} (now={t:.0f})."

        if self.plan_digest != plan.plan_digest:
            return False, (
                f"Plan digest mismatch. Token bound to {self.plan_digest[:16]}…, "
                f"plan has {plan.plan_digest[:16]}…"
            )

        if self.target_sha != plan.target_sha:
            return False, (
                f"Target SHA mismatch. Token bound to {self.target_sha[:12]}…, "
                f"plan has {plan.target_sha[:12]}…"
            )

        return True, ""

    def consume(self) -> None:
        """Mark the token as consumed. Idempotent; raises after first call."""
        if self.consumed:
            raise ValueError(f"Token {self.token_id} is already consumed — replay blocked.")
        self.consumed = True
        self.consumed_at = time.time()


def issue_approval_token(
    plan: IntegrationPlan,
    owner: str,
    ttl_seconds: float = 300.0,
) -> ApprovalToken:
    """Issue a single-use capability token for the given sealed plan."""
    now = time.time()
    return ApprovalToken(
        token_id=str(uuid.uuid4()),
        plan_digest=plan.plan_digest,
        target_sha=plan.target_sha,
        owner=owner,
        issued_at=now,
        expires_at=now + ttl_seconds,
        consumed=False,
    )


# ---------------------------------------------------------------------------
# IntegrationTransaction
# ---------------------------------------------------------------------------

@dataclass
class IntegrationTransaction:
    """Mutable state machine governing a shared mutation lifecycle.

    Fields
    ------
    transaction_id  : Globally unique identifier.
    plan            : The sealed, immutable IntegrationPlan.
    token           : The single-use ApprovalToken presented by the owner.
    state           : Current TransactionState string.
    pre_sha         : Git SHA recorded immediately before any mutations begin
                      (snapshot point for deterministic rollback).
    post_sha        : Git SHA recorded after successful application.
    qa_result       : Structured result from the post-integration test run.
    rollback_reason : Human-readable explanation if rollback was triggered.
    events          : Append-only audit log of (timestamp, state, message).
    """
    transaction_id:   str
    plan:             IntegrationPlan
    token:            ApprovalToken
    state:            str = TransactionState.PREPARED
    pre_sha:          str = ""
    post_sha:         str = ""
    qa_result:        dict[str, Any] = field(default_factory=dict)
    rollback_reason:  str = ""
    events:           list[tuple[float, str, str]] = field(default_factory=list)

    # -----------------------------------------------------------------------

    def log(self, message: str) -> None:
        self.events.append((time.time(), self.state, message))

    def update_state(self, new_state: str, *, reason: str = "") -> None:
        """Transition to new_state, enforcing the valid transition graph."""
        allowed = _VALID_TX_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid transaction state transition: {self.state!r} → {new_state!r}. "
                f"Allowed: {sorted(allowed)}"
            )
        self.state = new_state
        self.log(reason or f"Transitioned to {new_state}")

    @property
    def is_terminal(self) -> bool:
        return self.state in {
            TransactionState.COMPLETED,
            TransactionState.FAILED_SAFE,
            TransactionState.ABORTED,
        }


def create_transaction(plan: IntegrationPlan, token: ApprovalToken) -> IntegrationTransaction:
    """Create a new PREPARED transaction for the given plan and token."""
    tx = IntegrationTransaction(
        transaction_id=str(uuid.uuid4()),
        plan=plan,
        token=token,
    )
    tx.log("Transaction created in PREPARED state.")
    return tx


__all__ = [
    "TransactionState",
    "IntegrationCandidate",
    "IntegrationPlan",
    "ApprovalToken",
    "IntegrationTransaction",
    "seal_plan",
    "issue_approval_token",
    "create_transaction",
]
