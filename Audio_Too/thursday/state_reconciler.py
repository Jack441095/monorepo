"""Company state reconciler for Thursday V2-H.

Updates Thursday-owned derived state after successful integration.
Never mutates foreign project files. Performs closed-loop dependency
reasoning: if Task A resolves blocker X, Task B (blocked on X) may
become eligible — but does NOT automatically execute B if policy,
approval, ownership, risk, or resource limits prevent it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from thursday.engineering_contracts import (
    CandidateLineage,
    LoopDecision,
    ResourceClass,
    WorkProposal,
)


# ---------------------------------------------------------------------------
# Reconciliation result
# ---------------------------------------------------------------------------

@dataclass
class ReconciliationResult:
    """Summary of what changed in Thursday-owned derived state."""
    reconciled_at:          float
    resolved_blockers:      list[str] = field(default_factory=list)
    newly_eligible_tasks:   list[str] = field(default_factory=list)
    integrated_proposals:   list[str] = field(default_factory=list)
    state_updates:          list[str] = field(default_factory=list)
    deferred_tasks:         list[str] = field(default_factory=list)
    notes:                  list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# State Reconciler
# ---------------------------------------------------------------------------

class StateReconciler:
    """Reconciles Thursday-owned state after integration or status change.

    Parameters
    ----------
    heavy_task_limit : int
        Maximum concurrent heavy tasks (from V2-D; default 2).
    """

    FOREIGN_PROJECT_PREFIXES: tuple[str, ...] = (
        "Nite_DSP_01",
        "Nite_DSP_01-slo-ux-v3",
        "KENN",
        "NITE_Submit",
        "Layer_Alignment",
        "website",
        "SmartSampleManager",
    )

    def __init__(self, heavy_task_limit: int = 2) -> None:
        self.heavy_task_limit = heavy_task_limit
        # Thursday-owned ledger of proposal states
        self._proposal_states: dict[str, str] = {}      # proposal_id → state
        self._blocker_index: dict[str, list[str]] = {}  # blocker_id → [proposal_ids]
        self._active_heavy_count: int = 0

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def reconcile_after_integration(
        self,
        proposal: WorkProposal,
        lineage: CandidateLineage,
        *,
        snapshot: Any = None,
    ) -> ReconciliationResult:
        """Update derived state after a successful integration.

        Returns a ReconciliationResult describing what changed.
        Does NOT touch foreign project files.
        """
        result = ReconciliationResult(reconciled_at=time.time())

        # 1. Mark proposal integrated
        self._proposal_states[proposal.proposal_id] = "INTEGRATED"
        lineage.close("INTEGRATED", f"Proposal {proposal.proposal_id[:8]} integrated.")
        result.integrated_proposals.append(proposal.proposal_id)
        result.state_updates.append(
            f"Proposal {proposal.proposal_id[:8]} → INTEGRATED"
        )

        # 2. Resolve blockers this proposal addressed
        for blocker_id in self._find_resolved_blockers(proposal, snapshot):
            result.resolved_blockers.append(blocker_id)
            result.state_updates.append(f"Blocker {blocker_id!r} resolved.")

            # 3. Check which proposals become eligible
            for newly_eligible in self._find_newly_eligible(blocker_id):
                if self._is_execution_permitted(newly_eligible):
                    result.newly_eligible_tasks.append(newly_eligible)
                    result.state_updates.append(
                        f"Proposal {newly_eligible[:8]} unblocked by {blocker_id!r} — now eligible."
                    )
                else:
                    result.deferred_tasks.append(newly_eligible)
                    result.notes.append(
                        f"Proposal {newly_eligible[:8]} unblocked but deferred — "
                        "policy/resource/approval prevents auto-execution."
                    )

        # 4. Resource count adjustment
        resource_class = proposal.estimated_resource_class
        if resource_class == ResourceClass.HEAVY and self._active_heavy_count > 0:
            self._active_heavy_count = max(0, self._active_heavy_count - 1)

        return result

    def reconcile_no_action(self, reason: str) -> ReconciliationResult:
        """Record a NO_ACTION cycle (healthy state)."""
        result = ReconciliationResult(reconciled_at=time.time())
        result.notes.append(f"NO_ACTION: {reason}")
        return result

    def reconcile_rejection(
        self,
        proposal: WorkProposal,
        lineage: CandidateLineage,
        reason: str,
    ) -> ReconciliationResult:
        """Mark a proposal as rejected, preserve audit trail."""
        result = ReconciliationResult(reconciled_at=time.time())
        self._proposal_states[proposal.proposal_id] = "REJECTED"
        lineage.close("REJECTED", reason)
        result.state_updates.append(
            f"Proposal {proposal.proposal_id[:8]} → REJECTED: {reason}"
        )
        result.notes.append(
            "Rejected proposals will not be resubmitted unless candidate materially changes "
            "or owner explicitly reopens."
        )
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def register_blocker_dependency(self, blocker_id: str, proposal_id: str) -> None:
        """Register that proposal_id is blocked by blocker_id."""
        self._blocker_index.setdefault(blocker_id, []).append(proposal_id)

    def _find_resolved_blockers(
        self,
        proposal: WorkProposal,
        snapshot: Any,
    ) -> list[str]:
        """Identify blockers that the integrated proposal resolves."""
        resolved = []
        # Use the proposal's source_evidence as a clue to which blockers it addressed
        # In production: this would cross-reference company snapshot task blocker lists
        if snapshot is not None:
            blocked_tasks = getattr(snapshot, "blocked_tasks", ()) or ()
            for task in blocked_tasks:
                task_id = getattr(task, "task_id", "")
                # Heuristic: proposal's scope mentions this task_id
                if task_id and any(task_id in s for s in proposal.mutation_scope):
                    resolved.append(task_id)
        return resolved

    def _find_newly_eligible(self, resolved_blocker_id: str) -> list[str]:
        """Find proposals that were blocked by this blocker and are now free."""
        return list(self._blocker_index.get(resolved_blocker_id, []))

    def _is_execution_permitted(self, proposal_id: str) -> bool:
        """Check whether policy allows auto-queuing this newly eligible proposal.

        Conservative: by default, newly unblocked proposals are DEFERRED
        and require a new loop cycle for deliberate scheduling.
        """
        # V2-H policy: do not auto-execute even when unblocked —
        # each cycle is deliberate. Eligibility is surfaced to the owner.
        return False

    def is_foreign_project(self, path: str) -> bool:
        """True if path belongs to a foreign (non-Thursday-owned) project."""
        for prefix in self.FOREIGN_PROJECT_PREFIXES:
            if prefix in path:
                return True
        return False

    def heavy_task_budget_available(self) -> bool:
        return self._active_heavy_count < self.heavy_task_limit

    def increment_heavy_count(self) -> None:
        self._active_heavy_count = min(
            self._active_heavy_count + 1, self.heavy_task_limit
        )

    @property
    def _active_heavy(self) -> int:
        """Public alias for test introspection (maps to _active_heavy_count)."""
        return self._active_heavy_count

    @_active_heavy.setter
    def _active_heavy(self, value: int) -> None:
        self._active_heavy_count = value


__all__ = [
    "ReconciliationResult",
    "StateReconciler",
]
