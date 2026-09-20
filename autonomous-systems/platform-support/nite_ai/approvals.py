"""Approval contracts (Phase 5A).

A generic, product-neutral approval model for high-risk actions. Contracts
only — no execution of external/write actions. Aligns with the frozen NITE
DSP AI UX grammar (proposal → preview → accept → undo).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nite_ai._serialization import dataclass_to_dict
from nite_ai.contracts.evidence import EvidencePacket
from nite_ai.errors import ValidationError
from nite_ai.permissions import ActionRisk, Permission


class ActionLevel(str, Enum):
    READ = "read"
    PROPOSE = "propose"
    PREVIEW = "preview"
    WRITE = "write"
    EXTERNAL = "external"
    DESTRUCTIVE = "destructive"


class Reversibility(str, Enum):
    REVERSIBLE = "reversible"
    PARTIALLY_REVERSIBLE = "partially_reversible"
    IRREVERSIBLE = "irreversible"


_LEVEL_TO_MIN_RISK: dict[ActionLevel, ActionRisk] = {
    ActionLevel.READ: ActionRisk.LOW,
    ActionLevel.PROPOSE: ActionRisk.LOW,
    ActionLevel.PREVIEW: ActionRisk.LOW,
    ActionLevel.WRITE: ActionRisk.HIGH,
    ActionLevel.EXTERNAL: ActionRisk.HIGH,
    ActionLevel.DESTRUCTIVE: ActionRisk.CRITICAL,
}


@dataclass(frozen=True)
class ApprovalRequest:
    """A proposed action awaiting human decision."""

    approval_id: str
    action_level: ActionLevel
    capability_id: str
    summary: str                       # machine text describing the proposed action
    effects: tuple[str, ...] = ()      # enumerated expected effects
    evidence: EvidencePacket | None = None
    reversibility: Reversibility = Reversibility.REVERSIBLE
    required_permissions: tuple[Permission, ...] = ()
    undo_ref: str | None = None        # reference to the undo/rollback artifact
    expires_at_epoch: float | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.approval_id or not self.summary:
            raise ValidationError("ApprovalRequest requires id and summary")
        min_risk = _LEVEL_TO_MIN_RISK[self.action_level]
        if min_risk is ActionRisk.CRITICAL:
            if Permission.DESTRUCTIVE not in self.required_permissions:
                raise ValidationError(
                    "destructive approval requests must declare the destructive permission"
                )
        if self.action_level in (ActionLevel.WRITE, ActionLevel.EXTERNAL, ActionLevel.DESTRUCTIVE):
            if self.reversibility is Reversibility.IRREVERSIBLE and self.undo_ref is None:
                pass  # irreversible actions are allowed but must never claim undo
            if self.undo_ref and self.reversibility is Reversibility.IRREVERSIBLE:
                raise ValidationError("irreversible actions cannot declare an undo reference")

    @property
    def requires_human_approval(self) -> bool:
        return self.action_level in (
            ActionLevel.WRITE,
            ActionLevel.EXTERNAL,
            ActionLevel.DESTRUCTIVE,
        )

    def to_dict(self) -> dict:
        return dataclass_to_dict(self)


@dataclass(frozen=True)
class ApprovalDecision:
    approval_id: str
    approved: bool
    decided_by: str            # e.g. "owner", never a model output
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.approval_id or not self.decided_by:
            raise ValidationError("ApprovalDecision requires approval_id and decided_by")


__all__ = [
    "ActionLevel",
    "ApprovalDecision",
    "ApprovalRequest",
    "Reversibility",
]
