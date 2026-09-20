"""Versioned, reversible action proposals for the KENN plug-in surface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4


SCHEMA = "kenn.action_proposal.v1"


@dataclass(frozen=True)
class ActionProposal:
    id: str
    target: str
    parameter: str
    before: float
    after: float
    reason: str
    confidence: float
    evidence: tuple[str, ...] = ()
    expected_result: str = ""
    verification: str = ""
    risk: str = "local_mutation"
    requires_confirmation: bool = True

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value["schema"] = SCHEMA
        value["evidence"] = list(self.evidence)
        value["undo"] = {"target": self.target, "parameter": self.parameter, "value": self.before}
        return value


def proposals_from_live_context(context: dict[str, Any] | None, *, target_lufs: float = -14.0) -> list[dict[str, Any]]:
    """Return conservative suggestions from measured facts only.

    This does not claim to identify sources or third-party plug-in parameters.
    The sole current action target is the KENN plug-in's own target setting.
    """
    if not context:
        return []
    peak = float(context.get("peak_dbfs", -100.0))
    proposals: list[ActionProposal] = []
    if peak > -0.3:
        proposals.append(ActionProposal(
            id=f"proposal-{uuid4().hex}", target="kenn_mix_assistant", parameter="target_lufs",
            before=target_lufs, after=min(target_lufs, -15.0), confidence=0.91,
            reason="The measured bus peak is within 0.3 dBFS of full scale. Lowering the delivery target preserves more headroom for a reviewed render.",
            evidence=(f"Latest plug-in bus peak: {peak:.1f} dBFS.", "This is a bus snapshot and does not identify the source of the peak."),
            expected_result="The KENN target is lowered by at least 1 LUFS, leaving more requested delivery headroom; it does not change audio until a later render/process uses that target.",
            verification="After applying, confirm the displayed target changed, render or review the intended section, then compare peak/true-peak and loudness at matched playback level. Undo restores the prior target.",
        ))
    return [proposal.payload() for proposal in proposals]


def validate_apply_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate an explicit, reversible client-side apply request."""
    if payload.get("schema") != SCHEMA or not payload.get("requires_confirmation"):
        return {"ok": False, "error": "A confirmed action proposal is required."}
    if payload.get("target") != "kenn_mix_assistant" or payload.get("parameter") != "target_lufs":
        return {"ok": False, "error": "This plug-in action target is not supported."}
    try:
        before, after = float(payload["before"]), float(payload["after"])
    except (KeyError, TypeError, ValueError):
        return {"ok": False, "error": "Action values must be numeric."}
    if not -24.0 <= before <= -6.0 or not -24.0 <= after <= -6.0:
        return {"ok": False, "error": "Target LUFS is outside the plug-in's safe range."}
    return {"ok": True, "action": payload, "undo": {"target": "kenn_mix_assistant", "parameter": "target_lufs", "value": before}}
