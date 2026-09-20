"""Approval ergonomics for Thursday V2-I — owner attention economics.

A technically safe autonomous system that asks for approval constantly
is not operationally autonomous. This module treats owner attention as
a constrained resource and measures how well Thursday spends it.

What it does (legitimate fatigue protection)
--------------------------------------------
* Suppresses a duplicate approval request while an OPEN request for the
  same candidate identity already exists.
* Never re-asks for REJECTED work unless candidate_history signals
  materially new evidence.
* Batches independent pending requests into single owner interactions.
* Tracks the full request lifecycle and computes Owner Intervention
  Efficiency = useful outcomes / owner attention events.

What it must NEVER do (hard guard)
----------------------------------
* Probabilistic approval inference ("owner usually approves these").
* Skipping or downgrading any required V2-G/V2-H gate. Safety gates are
  mandatory regardless of efficiency; this module observes the approval
  flow, it never authorises anything.

Efficiency is reported, never used to bypass gates.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from thursday.simulated_clock import ClockProtocol


class RequestOutcome(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    WITHDRAWN_SUPERSEDED = "WITHDRAWN_SUPERSEDED"


@dataclass
class ApprovalRequest:
    request_id: str
    candidate_id: str
    requested_at_epoch: float
    batch_id: str
    value_score: float            # 0..1 significance used only for ordering
    outcome: str = RequestOutcome.PENDING.value
    resolved_at_epoch: float | None = None
    suppressed_duplicate_of: str = ""


@dataclass
class ApprovalRequestTracker:
    """Observes and shapes the approval interaction stream."""

    clock: ClockProtocol
    request_ttl_seconds: float = 3 * 86400.0   # un-answered requests expire

    _requests: list[ApprovalRequest] = field(default_factory=list)
    _rejected_without_new_evidence: set[str] = field(default_factory=set)

    # ------------------------------------------------------------------
    # Requesting attention
    # ------------------------------------------------------------------

    def request_approval(self, candidate_id: str,
                         *, has_new_evidence: bool = True,
                         value_score: float = 0.5) -> ApprovalRequest | None:
        """Ask the owner to approve a candidate.

        Returns None when the request is legitimately suppressed:
          * an identical OPEN request already exists (duplicate), or
          * the same candidate was rejected and no new evidence exists.
        """
        now = self.clock.now()

        if candidate_id in self._rejected_without_new_evidence and not has_new_evidence:
            return None   # Do not re-ask rejected work without new evidence.

        open_req = self._open_request_for(candidate_id)
        if open_req is not None:
            return None   # Already waiting on the owner; do not nag.

        req = ApprovalRequest(
            request_id=uuid.uuid4().hex,
            candidate_id=candidate_id,
            requested_at_epoch=now,
            batch_id="",                # assigned at batching time
            value_score=max(0.0, min(1.0, value_score)),
        )
        self._requests.append(req)
        return req

    def note_rejection(self, candidate_id: str) -> None:
        self._rejected_without_new_evidence.add(candidate_id)
        req = self._open_request_for(candidate_id)
        if req is not None:
            req.outcome = RequestOutcome.REJECTED.value
            req.resolved_at_epoch = self.clock.now()

    def note_new_evidence(self, candidate_id: str) -> None:
        """Materially new evidence re-enables asking about this candidate."""
        self._rejected_without_new_evidence.discard(candidate_id)

    # ------------------------------------------------------------------
    # Expiry (fail closed — expired ≠ approved)
    # ------------------------------------------------------------------

    def expire_stale_requests(self) -> list[ApprovalRequest]:
        """Expire un-answered requests past TTL; returns expired list.

        Expiry is fail-closed: an expired request is NOT an approval.
        """
        now = self.clock.now()
        expired: list[ApprovalRequest] = []
        for r in self._requests:
            if r.outcome == RequestOutcome.PENDING.value \
                    and now - r.requested_at_epoch > self.request_ttl_seconds:
                r.outcome = RequestOutcome.EXPIRED.value
                r.resolved_at_epoch = now
                expired.append(r)
        return expired

    def withdraw_superseded(self, candidate_id: str) -> bool:
        req = self._open_request_for(candidate_id)
        if req is None:
            return False
        req.outcome = RequestOutcome.WITHDRAWN_SUPERSEDED.value
        req.resolved_at_epoch = self.clock.now()
        return True

    # ------------------------------------------------------------------
    # Batching — one owner interaction, several decisions
    # ------------------------------------------------------------------

    def build_batch(self) -> tuple[str, list[ApprovalRequest]]:
        """Group all independent PENDING requests into one batch."""
        self.expire_stale_requests()
        pending = [r for r in self._requests if r.outcome == RequestOutcome.PENDING.value]
        pending.sort(key=lambda r: (-r.value_score, r.requested_at_epoch))
        if not pending:
            return "", []
        batch_id = uuid.uuid4().hex[:12]
        for r in pending:
            r.batch_id = batch_id
        return batch_id, pending

    def resolve_batch(self, batch_id: str, decisions: dict[str, bool]) -> None:
        """Apply owner decisions per candidate in one interaction.

        ``decisions`` maps candidate_id → approved?. Missing candidates
        remain PENDING. Resolving never consumes tokens or grants
        authority by itself — that remains SharedExecutor's job.
        """
        now = self.clock.now()
        for r in self._requests:
            if r.batch_id != batch_id or r.outcome != RequestOutcome.PENDING.value:
                continue
            if r.candidate_id in decisions:
                approved = decisions[r.candidate_id]
                r.outcome = (RequestOutcome.APPROVED.value if approved
                             else RequestOutcome.REJECTED.value)
                r.resolved_at_epoch = now
                if not approved:
                    self.note_rejection(r.candidate_id)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _open_request_for(self, candidate_id: str) -> ApprovalRequest | None:
        for r in reversed(self._requests):
            if r.candidate_id == candidate_id \
                    and r.outcome == RequestOutcome.PENDING.value:
                return r
        return None

    def metrics(self) -> dict[str, Any]:
        total = len(self._requests)
        by = lambda o: sum(1 for r in self._requests if r.outcome == o)
        resolved_useful = by(RequestOutcome.APPROVED.value)
        attention_events = len({r.batch_id for r in self._requests if r.batch_id}) \
            + sum(1 for r in self._requests if not r.batch_id
                  and r.outcome != RequestOutcome.PENDING.value)
        efficiency = (resolved_useful / attention_events) if attention_events else 0.0
        waits = [
            (r.resolved_at_epoch - r.requested_at_epoch)
            for r in self._requests if r.resolved_at_epoch is not None
        ]
        return {
            "approval_requests": total,
            "approved": resolved_useful,
            "rejected": by(RequestOutcome.REJECTED.value),
            "expired": by(RequestOutcome.EXPIRED.value),
            "withdrawn_superseded": by(RequestOutcome.WITHDRAWN_SUPERSEDED.value),
            "pending": by(RequestOutcome.PENDING.value),
            "attention_events": attention_events,
            "useful_outcomes_per_attention_event": round(efficiency, 4),
            "mean_wait_seconds": round(sum(waits) / len(waits), 2) if waits else 0.0,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_state(self) -> dict[str, Any]:
        return {
            "requests": [r.__dict__ for r in self._requests],
            "rejected_no_new_evidence": sorted(self._rejected_without_new_evidence),
        }

    @classmethod
    def from_state(cls, state: dict[str, Any], clock: ClockProtocol) -> "ApprovalRequestTracker":
        t = cls(clock=clock)
        t._requests = [ApprovalRequest(**r) for r in state.get("requests", ())]
        t._rejected_without_new_evidence = set(state.get("rejected_no_new_evidence", ()))
        return t


__all__ = ["ApprovalRequest", "ApprovalRequestTracker", "RequestOutcome"]
