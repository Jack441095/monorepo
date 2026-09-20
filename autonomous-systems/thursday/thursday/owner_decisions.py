"""Owner decision ledger for Thursday V2-I.

Owner decisions persist as explicit, deterministic, scoped records —
never as free-text memory that later gets reinterpreted.

Decision types cover: candidate rejection, defer-until-condition,
target forbidding, project protection (never-modify), policy changes
and reconsider-when conditions.

THE AUTHORITY BOUNDARY (non-negotiable)
---------------------------------------
This ledger records what the owner DECIDED. It never GRANTS authority:

* a past REJECT does not auto-reject materially new work — but it does
  suppress re-proposals without new evidence;
* a past APPROVE recorded here is bookkeeping only — integration
  authority lives exclusively in V2-G ApprovalTokens;
* security policy changes take effect only as explicit records; natural
  language history is never promoted into security policy.

Every record carries provenance and optional expiry/supersession.
Expired or superseded decisions stop applying — fail closed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from thursday.simulated_clock import ClockProtocol


class DecisionType(str, Enum):
    REJECT_CANDIDATE = "REJECT_CANDIDATE"
    DEFER_UNTIL = "DEFER_UNTIL"
    FORBID_TARGET = "FORBID_TARGET"
    NEVER_MODIFY_PROJECT = "NEVER_MODIFY_PROJECT"
    SET_POLICY = "SET_POLICY"
    RECONSIDER_WHEN = "RECONSIDER_WHEN"


@dataclass(frozen=True)
class OwnerDecision:
    """One explicit owner decision, scoped and provenance-stamped."""

    decision_id: str
    decision_type: str
    scope: dict[str, str]        # e.g. {"candidate_id": X} / {"project": Y}
    decided_at_epoch: float
    provenance: str              # must start with "owner:" for owner input
    payload: dict[str, Any] = field(default_factory=dict)
    expires_at_epoch: float | None = None
    superseded_by: str = ""      # decision_id replacing this one

    def active(self, now: float) -> bool:
        if self.superseded_by:
            return False
        if self.expires_at_epoch is not None and now > self.expires_at_epoch:
            return False
        return True


@dataclass
class OwnerDecisionLedger:
    """Append-only ledger of owner decisions with deterministic lookup."""

    clock: ClockProtocol
    _decisions: list[OwnerDecision] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        decision_type: DecisionType | str,
        scope: dict[str, str],
        *,
        provenance: str,
        payload: dict[str, Any] | None = None,
        expires_at_epoch: float | None = None,
    ) -> OwnerDecision:
        if not provenance.startswith("owner:"):
            raise ValueError(
                "Owner decisions require explicit owner provenance "
                f"(got {provenance!r}) — memory is not authority."
            )
        d = OwnerDecision(
            decision_id=uuid.uuid4().hex,
            decision_type=str(getattr(decision_type, "value", decision_type)),
            scope=dict(scope),
            decided_at_epoch=self.clock.now(),
            provenance=provenance,
            payload=payload or {},
            expires_at_epoch=expires_at_epoch,
        )
        self._decisions.append(d)
        return d

    def supersede(self, old_decision_id: str, *, provenance: str) -> OwnerDecision | None:
        for i, d in enumerate(self._decisions):
            if d.decision_id == old_decision_id and d.active(self.clock.now()):
                replacement = self.record(
                    d.decision_type, d.scope, provenance=provenance,
                    payload=d.payload, expires_at_epoch=d.expires_at_epoch,
                )
                self._decisions[i] = OwnerDecision(
                    decision_id=d.decision_id, decision_type=d.decision_type,
                    scope=d.scope, decided_at_epoch=d.decided_at_epoch,
                    provenance=d.provenance, payload=d.payload,
                    expires_at_epoch=d.expires_at_epoch,
                    superseded_by=replacement.decision_id,
                )
                return replacement
        return None

    # ------------------------------------------------------------------
    # Deterministic lookups (all fail closed)
    # ------------------------------------------------------------------

    def active_decisions(self, dtype: DecisionType | str | None = None) -> list[OwnerDecision]:
        want = getattr(dtype, "value", dtype)
        now = self.clock.now()
        return [
            d for d in self._decisions
            if d.active(now) and (want is None or d.decision_type == want)
        ]

    def rejects_candidate(self, candidate_id: str) -> OwnerDecision | None:
        for d in self.active_decisions(DecisionType.REJECT_CANDIDATE):
            if d.scope.get("candidate_id") == candidate_id:
                return d
        return None

    def project_protected(self, project: str) -> bool:
        return any(
            d.scope.get("project") == project
            for d in self.active_decisions(DecisionType.NEVER_MODIFY_PROJECT)
        )

    def target_forbidden(self, target: str) -> bool:
        return any(
            d.scope.get("target") == target
            for d in self.active_decisions(DecisionType.FORBID_TARGET)
        )

    def defer_condition(self, candidate_id: str) -> dict[str, str] | None:
        for d in self.active_decisions(DecisionType.DEFER_UNTIL):
            if d.scope.get("candidate_id") == candidate_id:
                return dict(d.payload)
        return None

    def policy_value(self, key: str) -> Any | None:
        """Newest active SET_POLICY payload value for ``key``."""
        vals = [
            d.payload.get(key) for d in self.active_decisions(DecisionType.SET_POLICY)
            if key in d.payload
        ]
        return vals[-1] if vals else None

    # ------------------------------------------------------------------
    # Persistence (bounded: decisions are compacted only by supersession,
    # never deleted while active — see state_compaction)
    # ------------------------------------------------------------------

    def to_state(self) -> dict[str, Any]:
        return {"decisions": [d.__dict__ for d in self._decisions]}

    @classmethod
    def from_state(cls, state: dict[str, Any], clock: ClockProtocol) -> "OwnerDecisionLedger":
        led = cls(clock=clock)
        for raw in state.get("decisions", ()):
            led._decisions.append(OwnerDecision(**raw))
        return led


__all__ = ["DecisionType", "OwnerDecision", "OwnerDecisionLedger"]
