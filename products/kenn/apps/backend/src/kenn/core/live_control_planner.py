"""Live Control Action Planner for Ableton Live 12.

Translates natural language audio engineering requests and live DAW context into
strongly-typed, versioned ActionProposal payloads requiring explicit user confirmation.
"""

from __future__ import annotations

import logging
import hashlib
import json
import math
import re
import time
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4

from kenn.ableton_osc_bridge import AbletonOSCClient, live_client
from kenn.core.confirmation import issue_confirmation
from kenn.plugin_actions import ActionProposal, BatchActionProposal, SCHEMA, BATCH_SCHEMA
from kenn.core.track_classifier import analyze_session_arrangement, classify_track_name
from kenn.core.device_units import display_to_raw, normalize_unit
from kenn.core.live_intent import parse_request

logger = logging.getLogger(__name__)
_PROPOSALS_BY_TOKEN: Dict[str, Dict[str, Any]] = {}
_PROPOSAL_LOCK = Lock()
MAX_PENDING_PROPOSALS = 1_000


def _prune_proposals_locked(*, now: float | None = None) -> None:
    current = time.time() if now is None else now
    expired = [
        token
        for token, proposal in _PROPOSALS_BY_TOKEN.items()
        if float((proposal.get("confirmation_meta") or {}).get("expires_at", 0)) <= current
    ]
    for token in expired:
        _PROPOSALS_BY_TOKEN.pop(token, None)
    overflow = len(_PROPOSALS_BY_TOKEN) - MAX_PENDING_PROPOSALS
    if overflow > 0:
        # Dicts preserve insertion order. Drop the oldest proposals first;
        # confirmation tokens remain independently expiry-checked at execute.
        for token in list(_PROPOSALS_BY_TOKEN)[:overflow]:
            _PROPOSALS_BY_TOKEN.pop(token, None)


def _store_proposal(confirm_token: str, proposal: Dict[str, Any]) -> None:
    with _PROPOSAL_LOCK:
        _prune_proposals_locked()
        _PROPOSALS_BY_TOKEN[confirm_token] = proposal
        _prune_proposals_locked()


def pending_proposal_count() -> int:
    """Return the bounded count only; proposal content remains private."""
    with _PROPOSAL_LOCK:
        _prune_proposals_locked()
        return len(_PROPOSALS_BY_TOKEN)


def _state_fingerprint(*, track_index: int, device_index: int, parameter_index: int, device_name: str, parameter: Dict[str, Any]) -> str:
    payload = {
        "track_index": track_index,
        "device_index": device_index,
        "parameter_index": parameter_index,
        "device_name": device_name,
        "parameter_name": parameter.get("name", ""),
        "before": parameter.get("value"),
        "min": parameter.get("min"),
        "max": parameter.get("max"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()



class LiveControlPlanner:
    """Generates typed ActionProposal and BatchActionProposal objects for Ableton Live parameters."""

    def __init__(self, osc_client: Optional[AbletonOSCClient] = None):
        self.osc_client = osc_client or live_client

    def propose_batch_parameter_changes(
        self,
        changes: List[Dict[str, Any]],
        *,
        reason: str,
        confidence: float = 0.9,
        session_id: str = "default_session",
    ) -> Dict[str, Any]:
        """Construct a BatchActionProposal containing multiple parameter change proposals and issue a single HMAC confirmation token."""
        if not changes:
            return {"ok": False, "error": "Batch action request requires at least one parameter change."}

        child_proposals: List[ActionProposal] = []
        token_text_parts: List[str] = []

        for position_in_batch, change in enumerate(changes, start=1):
            if not isinstance(change, dict):
                return {"ok": False, "error": f"Batch change {position_in_batch} must be an object."}
            try:
                track_idx = int(change.get("track_index", 0))
                device_idx = int(change.get("device_index", 0))
                param_idx = int(change.get("parameter_index", 0))
                proposed_val = float(change.get("proposed_value", 0.0))
            except (TypeError, ValueError, OverflowError):
                return {"ok": False, "error": f"Batch change {position_in_batch} has invalid numeric fields."}
            if track_idx < 0 or device_idx < 0 or param_idx < 0:
                return {"ok": False, "error": f"Batch change {position_in_batch} has a negative Live index."}
            p_reason = str(change.get("reason", reason))
            p_unit = str(change.get("unit", ""))

            # Fetch current parameters from Live
            params_info = self.osc_client.get_device_parameters(track_idx, device_idx)
            if not isinstance(params_info, dict) or not params_info.get("success"):
                return {
                    "ok": False,
                    "error": f"Failed to inspect device at track {track_idx}, device {device_idx}.",
                }

            device_name = params_info.get("device_name", f"Device {device_idx}")
            parameters = params_info.get("parameters", [])
            if not isinstance(parameters, list):
                return {"ok": False, "error": f"Live returned an invalid parameter list for '{device_name}'."}
            required_device_token = str(change.get("device_name_contains") or "").strip()
            if required_device_token and required_device_token.casefold() not in str(device_name).casefold():
                return {
                    "ok": False,
                    "error": (
                        f"Observed device '{device_name}' at track {track_idx}, device {device_idx} "
                        f"does not match required device family '{required_device_token}'."
                    ),
                }

            requested_param_name = str(change.get("parameter_name") or "").strip()
            resolve_by_name = change.get("resolve_parameter_by_name") is True
            target_param = None
            if resolve_by_name:
                named_matches = [
                    (position, item)
                    for position, item in enumerate(parameters)
                    if isinstance(item, dict)
                    and str(item.get("name") or "").strip().casefold() == requested_param_name.casefold()
                ]
                if len(named_matches) != 1:
                    return {
                        "ok": False,
                        "error": (
                            f"Expected one observed parameter named '{requested_param_name}' on "
                            f"'{device_name}', found {len(named_matches)}."
                        ),
                    }
                position, target_param = named_matches[0]
                raw_observed_index = target_param.get("index", position)
                if not isinstance(raw_observed_index, int) or raw_observed_index < 0:
                    return {
                        "ok": False,
                        "error": f"Observed parameter '{requested_param_name}' has an invalid Live index.",
                    }
                param_idx = raw_observed_index
            else:
                for item in parameters:
                    if not isinstance(item, dict):
                        continue
                    raw_index = item.get("index", -1)
                    if isinstance(raw_index, int) and not isinstance(raw_index, bool) and raw_index == param_idx:
                        target_param = item
                        break
            if target_param is None and 0 <= param_idx < len(parameters):
                # Backward compatibility for bridge responses without Live indices.
                target_param = parameters[param_idx]
            if not isinstance(target_param, dict):
                return {
                    "ok": False,
                    "error": f"Parameter index {param_idx} out of range for device '{device_name}'",
                }

            observed_param_name = str(target_param.get("name") or f"Parameter {param_idx}").strip()
            if requested_param_name and requested_param_name.casefold() != observed_param_name.casefold():
                return {
                    "ok": False,
                    "error": (
                        f"Requested parameter '{requested_param_name}' does not match observed "
                        f"parameter '{observed_param_name}' at index {param_idx} on '{device_name}'."
                    ),
                }
            param_name = observed_param_name
            try:
                current_val = float(target_param.get("value"))
                min_val = float(target_param.get("min"))
                max_val = float(target_param.get("max"))
            except (TypeError, ValueError, OverflowError):
                return {"ok": False, "error": f"Live returned invalid numeric state for '{param_name}'."}
            if not all(math.isfinite(value) for value in (current_val, min_val, max_val)) or min_val > max_val:
                return {"ok": False, "error": f"Live returned invalid numeric state for '{param_name}'."}
            if not math.isfinite(proposed_val) or proposed_val < min_val or proposed_val > max_val:
                return {"ok": False, "error": f"Proposed value {proposed_val} is outside valid range [{min_val}, {max_val}] for '{param_name}'."}
            clamped_val = proposed_val

            p_id = f"proposal-{uuid4().hex}"
            target_name = f"Track {track_idx} -> {device_name} -> {param_name}"

            child_proposal = ActionProposal(
                id=p_id,
                target="ableton_device",
                parameter=param_name,
                before=current_val,
                after=clamped_val,
                reason=p_reason,
                confidence=confidence,
                evidence=(f"Current Live session value for {target_name}: {current_val:.2f} {p_unit}".strip(),),
                expected_result=f"Set {target_name} from {current_val:.2f} {p_unit} to {clamped_val:.2f} {p_unit}".strip(),
                verification=f"Read back {target_name} from Live to confirm value equals {clamped_val:.2f} within tolerance.",
                risk="local_mutation",
                requires_confirmation=True,
                operation="set_device_parameter",
                track_index=track_idx,
                device_index=device_idx,
                parameter_index=param_idx,
                device_name=device_name,
                unit=p_unit,
                valid_range=(min_val, max_val),
                timestamp=time.time(),
                session_version="live-state-pending",
            )
            child_payload = child_proposal.payload()
            fingerprint = _state_fingerprint(
                track_index=track_idx,
                device_index=device_idx,
                parameter_index=param_idx,
                device_name=device_name,
                parameter=target_param,
            )
            child_payload["session_fingerprint"] = fingerprint
            child_payload["session_version"] = fingerprint
            child_proposals.append(child_payload)
            token_text_parts.append(f"{track_idx}:{device_idx}:{param_idx}:{clamped_val}")

        batch_id = f"batch-proposal-{uuid4().hex}"
        batch_proposal = BatchActionProposal(
            id=batch_id,
            proposals=tuple(),
            reason=reason,
            confidence=confidence,
        )

        batch_payload = batch_proposal.payload()
        batch_payload["proposals"] = child_proposals
        req_text = f"set_batch_device_parameter:{';'.join(token_text_parts)}"

        # Issue single HMAC confirmation token for the batch transaction
        confirm_token, confirm_meta = issue_confirmation(
            session_id=session_id,
            service_id="ableton_control",
            text=req_text,
            ttl_seconds=300,
        )

        batch_payload["confirmation_token"] = confirm_token
        batch_payload["confirmation_meta"] = confirm_meta
        _store_proposal(confirm_token, batch_payload)

        return {"ok": True, "proposal": batch_payload}


    def propose_parameter_change(
        self,
        *,
        track_index: int,
        device_index: int,
        parameter_index: int,
        proposed_value: float,
        reason: str,
        confidence: float = 0.9,
        session_id: str = "default_session",
        evidence: List[str] = None,
        parameter_name: str = "",
        unit: str = "",
        track_name: str = "",
        observed_parameter_info: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Query current parameter state from Live, construct an ActionProposal, and issue an HMAC token."""
        # The command gateway may pass the exact parameter block it just read
        # while resolving the request. Reusing that immutable observation
        # avoids a redundant OSC round-trip before confirmation; execution
        # still performs its own fresh stale-state check and readback.
        params_info = (
            observed_parameter_info
            if isinstance(observed_parameter_info, dict)
            else self.osc_client.get_device_parameters(track_index, device_index)
        )
        if not params_info.get("success"):
            return {
                "ok": False,
                "error": f"Failed to inspect target device parameters: {params_info.get('error', 'Unknown error')}",
            }

        device_name = params_info.get("device_name", f"Device {device_index}")
        parameters = params_info.get("parameters", [])

        target_param = next(
            (item for item in parameters if isinstance(item, dict) and int(item.get("index", -1)) == parameter_index),
            None,
        )
        if target_param is None and 0 <= parameter_index < len(parameters):
            # Backward compatibility for older bridge responses that omitted
            # original Live indices and returned a dense parameter list.
            target_param = parameters[parameter_index]
        if target_param is None:
            return {
                "ok": False,
                "error": f"Parameter index {parameter_index} out of range for device '{device_name}'",
            }
        param_name = parameter_name or target_param.get("name", f"Parameter {parameter_index}")
        current_val = float(target_param.get("value", 0.0))
        min_val = float(target_param.get("min", 0.0))
        max_val = float(target_param.get("max", 1.0))

        # 2. Validate proposed value within bounds
        if not math.isfinite(proposed_value) or proposed_value < min_val or proposed_value > max_val:
            return {"ok": False, "error": f"Proposed value {proposed_value} is outside valid range [{min_val}, {max_val}] for '{param_name}'."}
        clamped_val = proposed_value

        proposal_id = f"proposal-{uuid4().hex}"
        target_name = f"Track {track_index} -> {device_name} -> {param_name}"

        # 3. Create typed ActionProposal
        proposal = ActionProposal(
            id=proposal_id,
            target="ableton_device",
            parameter=param_name,
            before=current_val,
            after=clamped_val,
            reason=reason,
            confidence=confidence,
            evidence=tuple(evidence or [f"Current Live session value for {target_name}: {current_val:.2f} {unit}".strip()]),
            expected_result=f"Set {target_name} from {current_val:.2f} {unit} to {clamped_val:.2f} {unit}".strip(),
            verification=f"Read back {target_name} from Live to confirm value equals {clamped_val:.2f} within tolerance.",
            risk="local_mutation",
            requires_confirmation=True,
            operation="set_device_parameter",
            track_index=track_index,
            device_index=device_index,
            parameter_index=parameter_index,
            track_name=track_name,
            device_name=device_name,
            unit=unit,
            valid_range=(min_val, max_val),
            timestamp=time.time(),
            session_version="live-state-pending",
        )

        proposal_payload = proposal.payload()
        # AbletonOSC's bulk parameter response is intentionally raw and fast.
        # Add one targeted UI-value read to an exact proposal when the bridge
        # supports it, so the confirmation card can distinguish e.g. Glue
        # Attack raw=3 from Live's displayed value=1. Missing optional
        # metadata never blocks the safe raw-value path.
        value_string_reader = getattr(self.osc_client, "get_device_parameter_value_string", None)
        if callable(value_string_reader):
            try:
                display = value_string_reader(track_index, device_index, parameter_index)
            except Exception:
                display = None
            if isinstance(display, dict) and display.get("success") and display.get("value_string") not in (None, ""):
                proposal_payload["before_display"] = str(display["value_string"])
                proposal_payload["display_metadata"] = "AbletonOSC value_string"
        fingerprint = _state_fingerprint(
            track_index=track_index,
            device_index=device_index,
            parameter_index=parameter_index,
            device_name=device_name,
            parameter=target_param,
        )
        proposal_payload["session_fingerprint"] = fingerprint
        proposal_payload["session_version"] = fingerprint
        req_text = f"set_device_parameter:{track_index}:{device_index}:{parameter_index}:{clamped_val}"

        # 4. Issue HMAC confirmation token
        confirm_token, confirm_meta = issue_confirmation(
            session_id=session_id,
            service_id="ableton_control",
            text=req_text,
            ttl_seconds=300,
        )

        proposal_payload["confirmation_token"] = confirm_token
        proposal_payload["confirmation_meta"] = confirm_meta
        _store_proposal(confirm_token, proposal_payload)

        return {"ok": True, "proposal": proposal_payload}

    @staticmethod
    def proposal_for_token(confirm_token: str) -> Dict[str, Any] | None:
        with _PROPOSAL_LOCK:
            _prune_proposals_locked()
            proposal = _PROPOSALS_BY_TOKEN.get(str(confirm_token or ""))
        return dict(proposal) if proposal else None

    def parse_and_propose(
        self,
        query: str,
        session_state: Optional[Dict[str, Any]] = None,
        session_id: str = "default_session",
    ) -> Dict[str, Any]:
        """Parse and propose a device change without ever defaulting a target."""
        if session_state is None:
            session_state = self.osc_client.query_session_state()
        if session_state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live session is offline or has not returned a usable snapshot."}
        intent = parse_request(query, session_state)
        if intent.get("action") != "set_device_parameter":
            return {"ok": False, "intent": intent, "error": "A clarification is required before a supported device change can be proposed."}
        if intent.get("missing_fields") or intent.get("ambiguity"):
            return {"ok": False, "intent": intent, "error": "A clarification is required before a safe proposal can be made."}

        track = intent["track"]
        device = intent["device"]
        params_info = self.osc_client.get_device_parameters(int(track["index"]), int(device["index"]))
        if not params_info.get("success"):
            return {"ok": False, "intent": intent, "error": f"Could not inspect '{device['name']}' on track '{track['name']}'."}
        parameters = params_info.get("parameters", [])
        wanted = str(intent.get("parameter", {}).get("name", "")).lower()
        matches = [
            (int(parameter.get("index", index)), parameter)
            for index, parameter in enumerate(parameters)
            if wanted and wanted in str(parameter.get("name", "")).lower()
        ]
        if len(matches) != 1:
            intent["ambiguity"].append("Live returned zero or multiple parameters matching the requested name.")
            return {"ok": False, "intent": intent, "error": "The requested parameter was not uniquely identified by the current Live state."}
        param_index, parameter = matches[0]
        current = float(parameter.get("value", 0.0))
        requested = float(intent["desired_value"])
        unit = normalize_unit(intent.get("unit"))
        relative = bool(intent.get("relative"))
        if relative and unit not in {"", "value", "db"}:
            converted_delta, conversion_error = display_to_raw(
                device_name=str(device.get("name", "")),
                parameter_name=str(parameter.get("name", "")),
                value=requested,
                unit=unit,
                relative=True,
            )
            if conversion_error:
                return {"ok": False, "intent": intent, "error": conversion_error}
            requested = float(converted_delta)
        elif not relative and unit not in {"", "value", "db"}:
            converted_value, conversion_error = display_to_raw(
                device_name=str(device.get("name", "")),
                parameter_name=str(parameter.get("name", "")),
                value=requested,
                unit=unit,
            )
            if conversion_error:
                return {"ok": False, "intent": intent, "error": conversion_error}
            requested = float(converted_value)
        proposed = current + requested if relative else requested
        return self.propose_parameter_change(
            track_index=int(track["index"]),
            device_index=int(device["index"]),
            parameter_index=param_index,
            proposed_value=proposed,
            reason=f"Natural language request: {query.strip()}",
            session_id=session_id,
            parameter_name=str(parameter.get("name", "")),
            unit=unit,
            track_name=str(track.get("name", "")),
        )

    def perceive_live_session(self) -> Dict[str, Any]:
        """Query live Ableton track topology and analyze arrangement roles & masking risks."""
        if not self.osc_client:
            return {"ok": False, "error": "No OSC client configured."}

        tracks_res = self.osc_client.get_tracks()
        if not tracks_res.get("success"):
            return {"ok": False, "error": f"Failed to fetch live session tracks: {tracks_res.get('error')}"}

        raw_tracks = tracks_res.get("tracks", [])
        analysis = analyze_session_arrangement(raw_tracks)
        return {
            "ok": True,
            "session_perception": analysis,
        }
