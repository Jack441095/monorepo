"""Versioned, reversible action proposals for the KENN plug-in surface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import math
import time
from uuid import uuid4


SCHEMA = "kenn.action_proposal.v1"
BATCH_SCHEMA = "kenn.batch_action_proposal.v1"


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
    operation: str = "set_parameter"
    track_index: int | None = None
    track_name: str = ""
    device_index: int | None = None
    device_name: str = ""
    parameter_index: int | None = None
    unit: str = ""
    valid_range: tuple[float, float] | None = None
    timestamp: float = 0.0
    session_version: str = ""

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value["schema"] = SCHEMA
        if not value["timestamp"]:
            value["timestamp"] = time.time()
        value["evidence"] = list(self.evidence)
        value["undo"] = {
            "target": self.target,
            "parameter": self.parameter,
            "value": self.before,
            "track_index": self.track_index,
            "device_index": self.device_index,
            "parameter_index": self.parameter_index,
        }
        if self.valid_range:
            value["valid_range"] = list(self.valid_range)
        return value


@dataclass(frozen=True)
class BatchActionProposal:
    id: str
    proposals: tuple[ActionProposal, ...]
    reason: str
    confidence: float = 0.9
    risk: str = "local_mutation"
    requires_confirmation: bool = True

    def payload(self) -> dict[str, Any]:
        return {
            "schema": BATCH_SCHEMA,
            "id": self.id,
            "proposals": [p.payload() for p in self.proposals],
            "reason": self.reason,
            "confidence": self.confidence,
            "risk": self.risk,
            "requires_confirmation": self.requires_confirmation,
        }



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
    schema = payload.get("schema")
    if schema not in {SCHEMA, BATCH_SCHEMA} or not payload.get("requires_confirmation"):
        return {"ok": False, "error": "A confirmed action proposal is required."}

    if schema == BATCH_SCHEMA:
        child_proposals = payload.get("proposals", [])
        if not child_proposals or not isinstance(child_proposals, list):
            return {"ok": False, "error": "Batch action proposals require a non-empty list of child proposals."}
        for child in child_proposals:
            res = validate_apply_request(child)
            if not res.get("ok"):
                return {"ok": False, "error": f"Invalid child proposal in batch: {res.get('error')}"}
        return {"ok": True, "action": payload}


    target = payload.get("target")
    if target == "kenn_mix_assistant" and payload.get("parameter") == "target_lufs":
        try:
            before, after = float(payload["before"]), float(payload["after"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "Action values must be numeric."}
        if not -24.0 <= before <= -6.0 or not -24.0 <= after <= -6.0:
            return {"ok": False, "error": "Target LUFS is outside the plug-in's safe range."}
        return {"ok": True, "action": payload, "undo": {"target": "kenn_mix_assistant", "parameter": "target_lufs", "value": before}}

    if target in {"ableton_device", "ableton_parameter"}:
        try:
            before, after = float(payload["before"]), float(payload["after"])
            track_idx = int(payload["track_index"])
            device_idx = int(payload["device_index"])
            param_idx = int(payload["parameter_index"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "Ableton parameter proposals require numeric indices and values."}

        valid_range = payload.get("valid_range")
        if not all(math.isfinite(value) for value in (before, after)):
            return {"ok": False, "error": "Action values must be finite numbers."}
        if track_idx < 0 or device_idx < 0 or param_idx < 0:
            return {"ok": False, "error": "Ableton target indices must be non-negative."}
        if not payload.get("device_name") or not payload.get("parameter"):
            return {"ok": False, "error": "Ableton proposals require the device and parameter names read from Live."}
        if valid_range and len(valid_range) == 2:
            min_val, max_val = float(valid_range[0]), float(valid_range[1])
            if min_val > max_val:
                return {"ok": False, "error": "Invalid parameter range."}
            if not (min_val <= after <= max_val):
                return {"ok": False, "error": f"Proposed value {after} is outside valid parameter range [{min_val}, {max_val}]."}

        return {
            "ok": True,
            "action": payload,
            "undo": {
                "target": target,
                "parameter": payload.get("parameter", ""),
                "value": before,
                "track_index": track_idx,
                "device_index": device_idx,
                "parameter_index": param_idx,
            },
        }

    return {"ok": False, "error": f"Unsupported action target '{target}'."}
