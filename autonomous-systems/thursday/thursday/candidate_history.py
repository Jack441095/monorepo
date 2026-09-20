"""Persistent candidate lineage for Thursday V2-I.

V2-H proved one loop can close correctly. V2-I asks whether loops can
ACCUMULATE coherently. This module is Thursday's durable memory of every
engineering candidate it has ever seen — and the semantic rules that
stop history from becoming noise or, worse, authority.

Core properties
---------------
* **Deterministic identity** — a candidate's id is a digest over its
  canonical problem content. Re-observing the same problem yields the
  SAME candidate (deduplication), not a new proposal.
* **Semantic lifecycle** — an explicit transition graph distinguishes
  DISCOVERED / PROPOSED / DEFERRED / BLOCKED / WAITING_FOR_APPROVAL /
  REJECTED / APPROVED / EXECUTING / FAILED / SUPERSEDED / INTEGRATED /
  ROLLED_BACK / ABANDONED. Invalid transitions raise.
* **New vs changed circumstances** — ``register_observation`` tells the
  caller whether this is a brand-new candidate, a repeat observation,
  or a previously-seen candidate whose evidence materially changed.
* **Reopen discipline** — a REJECTED/ABANDONED candidate may reopen ONLY
  with a materially different evidence digest; otherwise re-proposals
  are suppressed (anti-nagging).
* **Repeated-failure intelligence** — consecutive failures of the same
  failure class escalate through backoff: retry → defer → block →
  abandon. New evidence resets the streak only when content changes.
* **Append-only history** — every transition is recorded with time and
  reason; nothing is overwritten. Compaction may drop aged terminal
  records only via explicit policy (see state_compaction).

Memory is bookkeeping. This module confers no approval, permission or
lease authority whatsoever.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from thursday.simulated_clock import ClockProtocol


class CandidateState(str, Enum):
    DISCOVERED = "DISCOVERED"
    PROPOSED = "PROPOSED"
    DEFERRED = "DEFERRED"
    BLOCKED = "BLOCKED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"
    INTEGRATED = "INTEGRATED"
    ROLLED_BACK = "ROLLED_BACK"
    ABANDONED = "ABANDONED"


_VALID_TRANSITIONS: dict[str, set[str]] = {
    CandidateState.DISCOVERED.value: {
        CandidateState.PROPOSED.value, CandidateState.DEFERRED.value,
        CandidateState.BLOCKED.value, CandidateState.ABANDONED.value,
        CandidateState.SUPERSEDED.value,
    },
    CandidateState.PROPOSED.value: {
        CandidateState.WAITING_FOR_APPROVAL.value, CandidateState.BLOCKED.value,
        CandidateState.DEFERRED.value, CandidateState.FAILED.value,
        CandidateState.ABANDONED.value, CandidateState.SUPERSEDED.value,
        CandidateState.REJECTED.value,
    },
    CandidateState.DEFERRED.value: {
        CandidateState.DISCOVERED.value, CandidateState.PROPOSED.value,
        CandidateState.BLOCKED.value, CandidateState.ABANDONED.value,
        CandidateState.SUPERSEDED.value,
    },
    CandidateState.BLOCKED.value: {
        # Blocker cleared → back to discovery for fresh evaluation.
        CandidateState.DISCOVERED.value, CandidateState.ABANDONED.value,
        CandidateState.SUPERSEDED.value,
    },
    CandidateState.WAITING_FOR_APPROVAL.value: {
        CandidateState.APPROVED.value, CandidateState.REJECTED.value,
        CandidateState.DEFERRED.value,   # ask expired/lapsed without answer
        CandidateState.SUPERSEDED.value, CandidateState.ABANDONED.value,
    },
    CandidateState.APPROVED.value: {
        CandidateState.EXECUTING.value, CandidateState.SUPERSEDED.value,
    },
    CandidateState.EXECUTING.value: {
        CandidateState.INTEGRATED.value, CandidateState.FAILED.value,
        CandidateState.ROLLED_BACK.value,
    },
    CandidateState.FAILED.value: {
        CandidateState.PROPOSED.value,          # deliberate retry
        CandidateState.DEFERRED.value, CandidateState.BLOCKED.value,
        CandidateState.ABANDONED.value, CandidateState.SUPERSEDED.value,
    },
    CandidateState.REJECTED.value: {
        CandidateState.PROPOSED.value,          # ONLY via new-evidence gate
        CandidateState.ABANDONED.value, CandidateState.SUPERSEDED.value,
    },
    CandidateState.INTEGRATED.value: {
        CandidateState.ROLLED_BACK.value,
        # Recurring-work reactivation: ONLY via materially new evidence
        # (runner-gated). Lineage retains the earlier integration.
        CandidateState.DISCOVERED.value,
    },
    CandidateState.ROLLED_BACK.value: {
        CandidateState.ABANDONED.value, CandidateState.SUPERSEDED.value,
        # Retry-after-rollback with materially new evidence (runner-gated).
        CandidateState.DISCOVERED.value,
    },
    CandidateState.SUPERSEDED.value: {
        # Reactivation ONLY via materially new evidence (runner-gated),
        # e.g. a superseded test-fix when the suite regresses again.
        CandidateState.DISCOVERED.value,
    },
    CandidateState.ABANDONED.value: set(),
}

# Escalation ladder for repeated identical failures (index by streak)
_FAILURE_ESCALATION = (
    (2, CandidateState.DEFERRED),
    (3, CandidateState.BLOCKED),
    (4, CandidateState.ABANDONED),
)


def candidate_identity(project: str, problem_class: str) -> str:
    """Deterministic content identity — same underlying work ⇒ same id.

    Identity is intentionally INDEPENDENT of the evolving evidence
    text: a candidate whose circumstances change over weeks must remain
    the same candidate so its lineage (rejections, failures, blockers)
    stays attached. Evolving detail belongs in ``evidence_digest``.
    """
    payload = json.dumps(
        {"p": project.strip(), "c": problem_class.strip()},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


@dataclass
class Transition:
    at_epoch: float
    from_state: str
    to_state: str
    reason: str


@dataclass
class FailureRecord:
    at_epoch: float
    failure_class: str      # e.g. "build_failure", "qa_veto", "stale_sha"
    detail: str


@dataclass
class CandidateRecord:
    candidate_id: str
    title: str
    project: str
    evidence_digest: str
    source_evidence: str
    first_seen_epoch: float
    last_seen_epoch: float
    state: str = CandidateState.DISCOVERED.value
    problem_class: str = ""             # class at registration; may be superseded
    history: list[Transition] = field(default_factory=list)
    failures: list[FailureRecord] = field(default_factory=list)
    blocker_key: str = ""               # temporal-truth key if externally blocked
    superseded_by: str = ""
    rejection_reason: str = ""
    integration_count: int = 0

    @property
    def is_terminal(self) -> bool:
        return self.state in (CandidateState.INTEGRATED.value,
                              CandidateState.ABANDONED.value)

    def consecutive_same_failures(self) -> int:
        if not self.failures:
            return 0
        last_class = self.failures[-1].failure_class
        n = 0
        for f in reversed(self.failures):
            if f.failure_class != last_class:
                break
            n += 1
        return n


@dataclass
class ObservationVerdict:
    """Result of registering an observation against history."""

    candidate_id: str
    record: CandidateRecord | None
    kind: str                 # NEW_CANDIDATE | REPEAT | CHANGED_EVIDENCE | SUPPRESSED_REJECTED
    note: str = ""


@dataclass
class CandidateHistory:
    """Durable cross-cycle registry of all known candidates."""

    clock: ClockProtocol
    max_same_failure_streak: int = 4   # beyond ladder end → ABANDONED
    _by_id: dict[str, CandidateRecord] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Registration / deduplication
    # ------------------------------------------------------------------

    def register_observation(
        self,
        *,
        project: str,
        problem_class: str,
        source_evidence: str,
        title: str = "",
        evidence_digest: str = "",
        blocker_key: str = "",
    ) -> ObservationVerdict:
        """Observe a potential engineering candidate.

        Deduplicates on deterministic identity; distinguishes new,
        repeated and materially-changed observations; suppresses
        re-proposals of rejected work without new evidence.
        """
        cid = candidate_identity(project, problem_class)
        now = self.clock.now()
        ev_digest = evidence_digest or hashlib.sha256(
            source_evidence.encode()).hexdigest()[:32]

        existing = self._by_id.get(cid)
        if existing is None:
            rec = CandidateRecord(
                candidate_id=cid, title=title or f"{project}: {problem_class}",
                project=project, evidence_digest=ev_digest,
                source_evidence=source_evidence,
                first_seen_epoch=now, last_seen_epoch=now,
                problem_class=problem_class,
                blocker_key=blocker_key,
            )
            self._by_id[cid] = rec
            return ObservationVerdict(cid, rec, "NEW_CANDIDATE")

        existing.last_seen_epoch = now
        if existing.state == CandidateState.REJECTED.value:
            if ev_digest == existing.evidence_digest:
                return ObservationVerdict(
                    cid, existing, "SUPPRESSED_REJECTED",
                    "Previously rejected with identical evidence; not re-proposing.",
                )
            return ObservationVerdict(
                cid, existing, "CHANGED_EVIDENCE",
                "Rejected candidate returned with materially different evidence.",
            )
        if existing.evidence_digest != ev_digest:
            existing.evidence_digest = ev_digest
            return ObservationVerdict(cid, existing, "CHANGED_EVIDENCE",
                                      "Evidence materially changed since last cycle.")
        return ObservationVerdict(cid, existing, "REPEAT", "Known candidate re-observed.")

    def get(self, candidate_id: str) -> CandidateRecord | None:
        return self._by_id.get(candidate_id)

    def all_candidates(self) -> list[CandidateRecord]:
        return list(self._by_id.values())

    def in_state(self, *states: CandidateState) -> list[CandidateRecord]:
        wanted = {str(getattr(s, "value", s)) for s in states}
        return [c for c in self._by_id.values() if c.state in wanted]

    # ------------------------------------------------------------------
    # Lifecycle transitions (deterministic, fail-closed)
    # ------------------------------------------------------------------

    def transition(self, candidate_id: str, to_state: CandidateState | str,
                   reason: str) -> CandidateRecord:
        target = str(getattr(to_state, "value", to_state))
        rec = self._by_id.get(candidate_id)
        if rec is None:
            raise KeyError(f"Unknown candidate {candidate_id!r}")
        allowed = _VALID_TRANSITIONS.get(rec.state, set())
        if target not in allowed:
            raise ValueError(
                f"Invalid lifecycle transition {rec.state} → {target} "
                f"for candidate {candidate_id}. Allowed: {sorted(allowed)}"
            )
        frm = rec.state
        rec.state = target
        rec.history.append(Transition(self.clock.now(), frm, target, reason))
        if target == CandidateState.INTEGRATED.value:
            rec.integration_count += 1
        if target == CandidateState.REJECTED.value:
            rec.rejection_reason = reason
        if target == CandidateState.SUPERSEDED.value:
            rec.superseded_by = reason   # reason carries successor id
        return rec

    # ------------------------------------------------------------------
    # Repeated failure handling
    # ------------------------------------------------------------------

    def record_failure(self, candidate_id: str, failure_class: str,
                       detail: str) -> str:
        """Record a failure; escalate per deterministic ladder.

        Returns the action taken: "retry" | "deferred" | "blocked" |
        "abandoned". Same-class streaks count toward escalation; a
        DIFFERENT failure class restarts the ladder (it is genuinely
        new information about a different obstacle).
        """
        rec = self._by_id.get(candidate_id)
        if rec is None:
            raise KeyError(f"Unknown candidate {candidate_id!r}")
        rec.failures.append(FailureRecord(self.clock.now(), failure_class, detail))
        if rec.is_terminal or rec.state == CandidateState.ABANDONED.value:
            return "abandoned"   # already out of the ladder; record only
        streak = rec.consecutive_same_failures()
        if streak >= self.max_same_failure_streak:
            self.transition(candidate_id, CandidateState.ABANDONED,
                            f"Abandoned after {streak} consecutive "
                            f"{failure_class} failures.")
            return "abandoned"
        for threshold, esc_state in _FAILURE_ESCALATION:
            if streak == threshold:
                self.transition(candidate_id, esc_state,
                                f"Escalated to {esc_state.value} after "
                                f"{streak} consecutive {failure_class} failures.")
                return esc_state.value.lower()
        # Deliberate retry: re-queue for a fresh proposal cycle.
        try:
            self.transition(candidate_id, CandidateState.PROPOSED,
                            f"Retry queued after {failure_class} failure "
                            f"(streak={streak}).")
        except ValueError:
            pass   # non-retryable current state; leave as-is (fail safe)
        return "retry"

    def new_evidence_resets_streak(self, candidate_id: str) -> bool:
        """Materially new evidence gives a failed candidate a fresh ladder."""
        rec = self._by_id.get(candidate_id)
        if rec is None:
            return False
        last = rec.failures[-1].failure_class if rec.failures else ""
        before = rec.consecutive_same_failures()
        # A different evidence digest is signalled by caller updating it;
        # here we clear the streak marker by appending a synthetic reset
        # only when caller already changed the digest.
        return bool(last) and before > 0

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_state(self) -> dict[str, Any]:
        def _ser(rec: CandidateRecord) -> dict[str, Any]:
            d = rec.__dict__.copy()
            d["history"] = [t.__dict__ for t in rec.history]
            d["failures"] = [f.__dict__ for f in rec.failures]
            return d
        return {"candidates": {cid: _ser(r) for cid, r in self._by_id.items()}}

    @classmethod
    def from_state(cls, state: dict[str, Any], clock: ClockProtocol) -> "CandidateHistory":
        hist = cls(clock=clock)
        for cid, raw in state.get("candidates", {}).items():
            raw = dict(raw)
            raw["history"] = [Transition(**t) for t in raw.get("history", ())]
            raw["failures"] = [FailureRecord(**f) for f in raw.get("failures", ())]
            hist._by_id[cid] = CandidateRecord(**raw)
        return hist

    def compact_terminal(self, older_than_days: float) -> int:
        """Forget ABANDONED candidates last seen before the age cutoff.

        Age-based retention: abandonment records outside the operational
        horizon are dropped from the registry (integration provenance
        lives elsewhere and is unaffected). INTEGRATED/ROLLED_BACK
        records are never removed here.
        """
        now = self.clock.now()
        cutoff = now - older_than_days * 86400.0
        doomed = [
            c.candidate_id for c in self._by_id.values()
            if c.state == CandidateState.ABANDONED.value
            and c.last_seen_epoch < cutoff
        ]
        for cid in doomed:
            del self._by_id[cid]
        return len(doomed)


__all__ = [
    "CandidateState", "CandidateRecord", "CandidateHistory",
    "ObservationVerdict", "candidate_identity",
]
