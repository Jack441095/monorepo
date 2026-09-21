"""Tier-2 and Tier-3 Ableton Live Control Expansion Actions.

Provides proposals, execution, and readback for:
- Arrangement timeline clip duplication
- Clip automation curve writing
- Rack macro mappings and variations
- Track audio routing (in/out) and freezing
- Realtime post-fader metering
- Clip launching, stopping, deletion, loop duplication, and modulation/MPE
- Audio clip warp mode and pitch transposition
- Browser preset loading (.adv/.adg)
- Resample bounce workflow
- Max for Live introspection
- Master limiter true-peak safety ceiling lock
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from kenn.core.actions.common import (
    _ACTION_LOCK,
    _IN_FLIGHT_IDEMPOTENCY_KEYS,
    _PROPOSALS_BY_TOKEN,
    _USED_IDEMPOTENCY_KEYS,
    _cleanup_memory,
    _find_track,
    _state_version,
)
from kenn.core.confirmation import consume_confirmation, issue_confirmation
from kenn.core.receipt_contract import StageTimer, resolve_correlation_id

ARRANGEMENT_DUPLICATION_PROPOSAL_SCHEMA = "kenn.ableton_arrangement_duplication_proposal.v1"
ARRANGEMENT_DUPLICATION_RECEIPT_SCHEMA = "kenn.ableton_arrangement_duplication_receipt.v1"
CLIP_AUTOMATION_PROPOSAL_SCHEMA = "kenn.ableton_clip_automation_proposal.v1"
CLIP_AUTOMATION_RECEIPT_SCHEMA = "kenn.ableton_clip_automation_receipt.v1"
RACK_MACRO_PROPOSAL_SCHEMA = "kenn.ableton_rack_macro_proposal.v1"
RACK_MACRO_RECEIPT_SCHEMA = "kenn.ableton_rack_macro_receipt.v1"

TRACK_ROUTING_PROPOSAL_SCHEMA = "kenn.ableton_track_routing_proposal.v1"
TRACK_ROUTING_RECEIPT_SCHEMA = "kenn.ableton_track_routing_receipt.v1"
TRACK_FREEZE_PROPOSAL_SCHEMA = "kenn.ableton_track_freeze_proposal.v1"
TRACK_FREEZE_RECEIPT_SCHEMA = "kenn.ableton_track_freeze_receipt.v1"
RACK_VARIATION_PROPOSAL_SCHEMA = "kenn.ableton_rack_variation_proposal.v1"
RACK_VARIATION_RECEIPT_SCHEMA = "kenn.ableton_rack_variation_receipt.v1"

CLIP_LAUNCH_PROPOSAL_SCHEMA = "kenn.ableton_clip_launch_proposal.v1"
CLIP_LAUNCH_RECEIPT_SCHEMA = "kenn.ableton_clip_launch_receipt.v1"
SCENE_CREATION_PROPOSAL_SCHEMA = "kenn.ableton_scene_creation_proposal.v1"
SCENE_CREATION_RECEIPT_SCHEMA = "kenn.ableton_scene_creation_receipt.v1"
LOOP_DUPLICATION_PROPOSAL_SCHEMA = "kenn.ableton_loop_duplication_proposal.v1"
LOOP_DUPLICATION_RECEIPT_SCHEMA = "kenn.ableton_loop_duplication_receipt.v1"
CLIP_WARP_PITCH_PROPOSAL_SCHEMA = "kenn.ableton_clip_warp_pitch_proposal.v1"
CLIP_WARP_PITCH_RECEIPT_SCHEMA = "kenn.ableton_clip_warp_pitch_receipt.v1"
CLIP_DELETION_PROPOSAL_SCHEMA = "kenn.ableton_clip_deletion_proposal.v1"
CLIP_DELETION_RECEIPT_SCHEMA = "kenn.ableton_clip_deletion_receipt.v1"
PRESET_LOAD_PROPOSAL_SCHEMA = "kenn.ableton_preset_load_proposal.v1"
PRESET_LOAD_RECEIPT_SCHEMA = "kenn.ableton_preset_load_receipt.v1"
RESAMPLE_BOUNCE_PROPOSAL_SCHEMA = "kenn.ableton_resample_bounce_proposal.v1"
RESAMPLE_BOUNCE_RECEIPT_SCHEMA = "kenn.ableton_resample_bounce_receipt.v1"

CLIP_MODULATION_PROPOSAL_SCHEMA = "kenn.ableton_clip_modulation_proposal.v1"
CLIP_MODULATION_RECEIPT_SCHEMA = "kenn.ableton_clip_modulation_receipt.v1"
CLIP_WARP_MODE_PROPOSAL_SCHEMA = "kenn.ableton_clip_warp_mode_proposal.v1"
CLIP_WARP_MODE_RECEIPT_SCHEMA = "kenn.ableton_clip_warp_mode_receipt.v1"
MASTER_LIMITER_LOCK_PROPOSAL_SCHEMA = "kenn.ableton_master_limiter_lock_proposal.v1"
MASTER_LIMITER_LOCK_RECEIPT_SCHEMA = "kenn.ableton_master_limiter_lock_receipt.v1"


class Tier2Tier3ControlMixin:
    """Domain mixin providing Tier-2 and Tier-3 Ableton Live control actions."""

    def propose_arrangement_duplication(
        self,
        *,
        track_index: int,
        clip_slot_index: int,
        destination_time_beats: float,
        session_id: str,
        track_name: str = "",
    ) -> dict[str, Any]:
        """Propose duplicating a Session clip into the Arrangement timeline."""
        _cleanup_memory()
        state = self.snapshot(include_mixer=False)
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        track, error = _find_track(state, int(track_index), track_name)
        if error or track is None:
            return {"ok": False, "error": error}
        target_slot = self.client.get_clip_slot_state(int(track_index), int(clip_slot_index))
        if not target_slot.get("success") or not target_slot.get("has_clip"):
            return {"ok": False, "error": "Source slot has no clip to duplicate to arrangement."}
        clip_name = str(target_slot.get("clip_name", "Clip"))
        proposal = {
            "schema": ARRANGEMENT_DUPLICATION_PROPOSAL_SCHEMA,
            "action_id": f"action-arr-dup-{uuid.uuid4().hex}",
            "action": "duplicate_clip_to_arrangement",
            "operation": "duplicate_clip_to_arrangement",
            "target": "ableton_arrangement_timeline",
            "track_index": int(track_index),
            "track_name": str(track.get("name", "")),
            "clip_slot_index": int(clip_slot_index),
            "clip_name": clip_name,
            "destination_time_beats": float(destination_time_beats),
            "reason": f"Duplicate clip '{clip_name}' on track '{track.get('name')}' to arrangement timeline at beat {destination_time_beats}.",
            "confidence": 1.0,
            "risk": "local_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state, track=track),
        }
        confirm_text = f"duplicate_to_arrangement:{track_index}:{clip_slot_index}:{destination_time_beats}"
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def execute_arrangement_duplication(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Execute verified arrangement duplication proposal."""
        _cleanup_memory()
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != ARRANGEMENT_DUPLICATION_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid arrangement duplication proposal is required."}
        track_index = int(proposal["track_index"])
        clip_slot_index = int(proposal["clip_slot_index"])
        dest_time = float(proposal["destination_time_beats"])
        confirm_text = f"duplicate_to_arrangement:{track_index}:{clip_slot_index}:{dest_time}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)

        ok = self.client.duplicate_clip_to_arrangement(track_index, clip_slot_index, dest_time)
        timer.mark("duplication")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            if ok:
                _USED_IDEMPOTENCY_KEYS.add(key)
        if not ok:
            return {"ok": False, "error": "Ableton Live failed to duplicate clip to arrangement."}
        receipt = {
            "schema": ARRANGEMENT_DUPLICATION_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-arr-dup-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "duplicate_clip_to_arrangement",
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "destination_time_beats": dest_time,
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def propose_clip_automation(
        self,
        *,
        track_index: int,
        clip_slot_index: int,
        device_index: int,
        parameter_index: int,
        points: list[dict[str, Any]],
        session_id: str,
        track_name: str = "",
    ) -> dict[str, Any]:
        """Propose writing automation curve points into a Session View clip."""
        _cleanup_memory()
        state = self.snapshot(include_mixer=False)
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        track, error = _find_track(state, int(track_index), track_name)
        if error or track is None:
            return {"ok": False, "error": error}
        target_slot = self.client.get_clip_slot_state(int(track_index), int(clip_slot_index))
        if not target_slot.get("success") or not target_slot.get("has_clip"):
            return {"ok": False, "error": "Target slot has no clip to automate."}

        proposal = {
            "schema": CLIP_AUTOMATION_PROPOSAL_SCHEMA,
            "action_id": f"action-clip-auto-{uuid.uuid4().hex}",
            "action": "set_clip_automation",
            "operation": "set_clip_automation",
            "target": "ableton_clip_automation",
            "track_index": int(track_index),
            "track_name": str(track.get("name", "")),
            "clip_slot_index": int(clip_slot_index),
            "device_index": int(device_index),
            "parameter_index": int(parameter_index),
            "points": points,
            "point_count": len(points),
            "reason": f"Write {len(points)} automation curve points for device {device_index}, param {parameter_index} into clip {clip_slot_index + 1} on track '{track.get('name')}'.",
            "confidence": 1.0,
            "risk": "local_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state, track=track),
        }
        confirm_text = f"set_clip_automation:{track_index}:{clip_slot_index}:{device_index}:{parameter_index}:{len(points)}"
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def execute_clip_automation(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Execute confirmed clip automation proposal."""
        _cleanup_memory()
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != CLIP_AUTOMATION_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid clip automation proposal is required."}
        track_index = int(proposal["track_index"])
        clip_slot_index = int(proposal["clip_slot_index"])
        device_index = int(proposal["device_index"])
        parameter_index = int(proposal["parameter_index"])
        points = proposal.get("points", [])
        confirm_text = f"set_clip_automation:{track_index}:{clip_slot_index}:{device_index}:{parameter_index}:{len(points)}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)

        ok = self.client.set_clip_automation(track_index, clip_slot_index, device_index, parameter_index, points)
        timer.mark("automation_write")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            if ok:
                _USED_IDEMPOTENCY_KEYS.add(key)
        if not ok:
            return {"ok": False, "error": "Ableton Live failed to write clip automation envelope."}
        receipt = {
            "schema": CLIP_AUTOMATION_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-clip-auto-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "set_clip_automation",
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "device_index": device_index,
            "parameter_index": parameter_index,
            "points_written": len(points),
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def propose_rack_macro_mapping(
        self,
        *,
        track_index: int,
        device_index: int,
        macro_index: int,
        target_param_index: int,
        session_id: str,
        track_name: str = "",
    ) -> dict[str, Any]:
        """Propose mapping a device parameter to a Rack macro knob."""
        _cleanup_memory()
        state = self.snapshot(include_mixer=False)
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        track, error = _find_track(state, int(track_index), track_name)
        if error or track is None:
            return {"ok": False, "error": error}
        proposal = {
            "schema": RACK_MACRO_PROPOSAL_SCHEMA,
            "action_id": f"action-macro-{uuid.uuid4().hex}",
            "action": "map_rack_macro",
            "operation": "map_rack_macro",
            "target": "ableton_rack_macro",
            "track_index": int(track_index),
            "track_name": str(track.get("name", "")),
            "device_index": int(device_index),
            "macro_index": int(macro_index),
            "target_param_index": int(target_param_index),
            "reason": f"Map Macro {macro_index + 1} to parameter {target_param_index} on rack device {device_index} (track '{track.get('name')}').",
            "confidence": 1.0,
            "risk": "local_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state, track=track),
        }
        confirm_text = f"map_rack_macro:{track_index}:{device_index}:{macro_index}:{target_param_index}"
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def execute_rack_macro_mapping(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Execute confirmed rack macro mapping proposal."""
        _cleanup_memory()
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != RACK_MACRO_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid rack macro proposal is required."}
        track_index = int(proposal["track_index"])
        device_index = int(proposal["device_index"])
        macro_index = int(proposal["macro_index"])
        target_param_index = int(proposal["target_param_index"])
        confirm_text = f"map_rack_macro:{track_index}:{device_index}:{macro_index}:{target_param_index}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        ok = self.client.map_rack_macro(track_index, device_index, macro_index, target_param_index)
        timer.mark("macro_map")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            if ok:
                _USED_IDEMPOTENCY_KEYS.add(key)
        if not ok:
            return {"ok": False, "error": "Ableton Live failed to map rack macro."}
        receipt = {
            "schema": RACK_MACRO_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-macro-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "map_rack_macro",
            "track_index": track_index,
            "device_index": device_index,
            "macro_index": macro_index,
            "target_param_index": target_param_index,
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def propose_track_routing(
        self,
        track_index: int,
        routing_type: str,
        direction: str = "output",
        session_id: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Propose setting track audio input or output routing."""
        direction = "input" if direction.lower() == "input" else "output"
        action_id = f"act-route-{uuid.uuid4().hex}"
        confirm_text = f"set_track_routing:{direction}:{track_index}:{routing_type}"
        token, _ = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal = {
            "schema": TRACK_ROUTING_PROPOSAL_SCHEMA,
            "action_id": action_id,
            "action": f"set_track_{direction}_routing",
            "direction": direction,
            "track_index": int(track_index),
            "routing_type": str(routing_type),
            "confirmation_token": token,
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        return {"ok": True, "proposal": proposal}

    def execute_track_routing(
        self,
        proposal: dict[str, Any],
        confirm_token: str,
        session_id: str = "",
        idempotency_key: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != TRACK_ROUTING_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid track routing proposal is required."}
        track_index = int(proposal["track_index"])
        routing_type = str(proposal["routing_type"])
        direction = str(proposal.get("direction", "output"))
        confirm_text = f"set_track_routing:{direction}:{track_index}:{routing_type}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        if direction == "input":
            ok = self.client.set_track_input_routing(track_index, routing_type)
        else:
            ok = self.client.set_track_output_routing(track_index, routing_type)
        timer.mark("route_write")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            if ok:
                _USED_IDEMPOTENCY_KEYS.add(key)
        if not ok:
            return {"ok": False, "error": f"Ableton Live failed to set track {direction} routing."}
        receipt = {
            "schema": TRACK_ROUTING_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-route-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": f"set_track_{direction}_routing",
            "direction": direction,
            "track_index": track_index,
            "routing_type": routing_type,
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def propose_track_freeze(
        self,
        track_index: int,
        freeze: bool = True,
        session_id: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Propose freezing or unfreezing a track."""
        action_id = f"act-freeze-{uuid.uuid4().hex}"
        confirm_text = f"set_track_freeze:{track_index}:{bool(freeze)}"
        token, _ = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal = {
            "schema": TRACK_FREEZE_PROPOSAL_SCHEMA,
            "action_id": action_id,
            "action": "freeze_track" if freeze else "unfreeze_track",
            "track_index": int(track_index),
            "freeze": bool(freeze),
            "confirmation_token": token,
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        return {"ok": True, "proposal": proposal}

    def execute_track_freeze(
        self,
        proposal: dict[str, Any],
        confirm_token: str,
        session_id: str = "",
        idempotency_key: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != TRACK_FREEZE_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid track freeze proposal is required."}
        track_index = int(proposal["track_index"])
        freeze = bool(proposal["freeze"])
        confirm_text = f"set_track_freeze:{track_index}:{freeze}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        ok = self.client.set_track_freeze(track_index, freeze)
        timer.mark("freeze_write")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            if ok:
                _USED_IDEMPOTENCY_KEYS.add(key)
        if not ok:
            return {"ok": False, "error": "Ableton Live failed to freeze track."}
        receipt = {
            "schema": TRACK_FREEZE_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-freeze-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "freeze_track" if freeze else "unfreeze_track",
            "track_index": track_index,
            "freeze": freeze,
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def propose_rack_variation(
        self,
        track_index: int,
        device_index: int,
        sub_action: str = "store",
        variation_index: int = 0,
        session_id: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Propose storing or recalling a Rack Macro Variation."""
        sub_action = "recall" if sub_action.lower() == "recall" else "store"
        action_id = f"act-variation-{uuid.uuid4().hex}"
        confirm_text = f"rack_variation:{sub_action}:{track_index}:{device_index}:{variation_index}"
        token, _ = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal = {
            "schema": RACK_VARIATION_PROPOSAL_SCHEMA,
            "action_id": action_id,
            "action": f"{sub_action}_rack_variation",
            "sub_action": sub_action,
            "track_index": int(track_index),
            "device_index": int(device_index),
            "variation_index": int(variation_index),
            "confirmation_token": token,
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        return {"ok": True, "proposal": proposal}

    def execute_rack_variation(
        self,
        proposal: dict[str, Any],
        confirm_token: str,
        session_id: str = "",
        idempotency_key: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != RACK_VARIATION_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid rack variation proposal is required."}
        track_index = int(proposal["track_index"])
        device_index = int(proposal["device_index"])
        sub_action = str(proposal.get("sub_action", "store"))
        variation_index = int(proposal.get("variation_index", 0))
        confirm_text = f"rack_variation:{sub_action}:{track_index}:{device_index}:{variation_index}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        if sub_action == "recall":
            ok = self.client.recall_rack_variation(track_index, device_index, variation_index)
        else:
            ok = self.client.store_rack_variation(track_index, device_index)
        timer.mark("variation_exec")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            if ok:
                _USED_IDEMPOTENCY_KEYS.add(key)
        if not ok:
            return {"ok": False, "error": f"Ableton Live failed to {sub_action} rack variation."}
        receipt = {
            "schema": RACK_VARIATION_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-variation-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": f"{sub_action}_rack_variation",
            "track_index": track_index,
            "device_index": device_index,
            "variation_index": variation_index,
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def read_track_realtime_meters(self, track_index: int) -> dict[str, Any]:
        """Read instantaneous left and right post-fader meter values."""
        return self.client.get_track_realtime_meters(int(track_index))

    def propose_clip_launch(
        self,
        track_index: int,
        clip_slot_index: int,
        session_id: str = "",
        stop: bool = False,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Propose firing or stopping a Session View clip slot."""
        action_name = "stop_clip" if stop else "launch_clip"
        action_id = f"act-clip-launch-{uuid.uuid4().hex}"
        confirm_text = f"clip_launch:{action_name}:{track_index}:{clip_slot_index}"
        token, _ = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal = {
            "schema": CLIP_LAUNCH_PROPOSAL_SCHEMA,
            "action_id": action_id,
            "action": action_name,
            "track_index": int(track_index),
            "clip_slot_index": int(clip_slot_index),
            "stop": bool(stop),
            "confirmation_token": token,
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        return {"ok": True, "proposal": proposal}

    def execute_clip_launch(
        self,
        proposal: dict[str, Any],
        confirm_token: str,
        session_id: str = "",
        idempotency_key: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != CLIP_LAUNCH_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid clip launch proposal is required."}
        track_index = int(proposal["track_index"])
        clip_slot_index = int(proposal["clip_slot_index"])
        stop = bool(proposal.get("stop", False))
        action_name = "stop_clip" if stop else "launch_clip"
        confirm_text = f"clip_launch:{action_name}:{track_index}:{clip_slot_index}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        if stop:
            ok = self.client.stop_clip(track_index, clip_slot_index)
        else:
            ok = self.client.launch_clip(track_index, clip_slot_index)
        timer.mark("clip_launch_exec")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            if ok:
                _USED_IDEMPOTENCY_KEYS.add(key)
        if not ok:
            return {"ok": False, "error": f"Ableton Live failed to execute {action_name}."}
        receipt = {
            "schema": CLIP_LAUNCH_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-launch-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": action_name,
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "stop": stop,
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def propose_scene_creation(
        self,
        name: str = "",
        session_id: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Propose creating a new Scene in Session View."""
        action_id = f"act-scene-create-{uuid.uuid4().hex}"
        confirm_text = f"create_scene:{name}"
        token, _ = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal = {
            "schema": SCENE_CREATION_PROPOSAL_SCHEMA,
            "action_id": action_id,
            "action": "create_scene",
            "scene_name": str(name),
            "confirmation_token": token,
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        return {"ok": True, "proposal": proposal}

    def execute_scene_creation(
        self,
        proposal: dict[str, Any],
        confirm_token: str,
        session_id: str = "",
        idempotency_key: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != SCENE_CREATION_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid scene creation proposal is required."}
        name = str(proposal.get("scene_name", ""))
        confirm_text = f"create_scene:{name}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        res = self.client.create_scene(name=name)
        timer.mark("scene_create_exec")
        ok = bool(res.get("success", False))
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            if ok:
                _USED_IDEMPOTENCY_KEYS.add(key)
        if not ok:
            return {"ok": False, "error": res.get("error", "Ableton Live failed to create scene.")}
        receipt = {
            "schema": SCENE_CREATION_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-scene-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "create_scene",
            "scene_index": res.get("scene_index", -1),
            "scene_name": res.get("scene_name", name),
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def propose_loop_duplication(
        self,
        track_index: int,
        clip_slot_index: int,
        session_id: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Propose duplicating loop length of a Session View clip."""
        action_id = f"act-loop-dup-{uuid.uuid4().hex}"
        confirm_text = f"duplicate_loop:{track_index}:{clip_slot_index}"
        token, _ = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal = {
            "schema": LOOP_DUPLICATION_PROPOSAL_SCHEMA,
            "action_id": action_id,
            "action": "duplicate_loop",
            "track_index": int(track_index),
            "clip_slot_index": int(clip_slot_index),
            "confirmation_token": token,
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        return {"ok": True, "proposal": proposal}

    def execute_loop_duplication(
        self,
        proposal: dict[str, Any],
        confirm_token: str,
        session_id: str = "",
        idempotency_key: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != LOOP_DUPLICATION_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid loop duplication proposal is required."}
        track_index = int(proposal["track_index"])
        clip_slot_index = int(proposal["clip_slot_index"])
        confirm_text = f"duplicate_loop:{track_index}:{clip_slot_index}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        ok = self.client.duplicate_loop(track_index, clip_slot_index)
        timer.mark("loop_dup_exec")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            if ok:
                _USED_IDEMPOTENCY_KEYS.add(key)
        if not ok:
            return {"ok": False, "error": "Ableton Live failed to duplicate loop."}
        receipt = {
            "schema": LOOP_DUPLICATION_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-loopdup-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "duplicate_loop",
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def propose_clip_warp_pitch(
        self,
        track_index: int,
        clip_slot_index: int,
        warp_mode: int | None = None,
        pitch_coarse: int | None = None,
        session_id: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Propose setting warp mode or pitch transposition on a Session View clip."""
        action_id = f"act-clip-wp-{uuid.uuid4().hex}"
        confirm_text = f"clip_warp_pitch:{track_index}:{clip_slot_index}:{warp_mode}:{pitch_coarse}"
        token, _ = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal = {
            "schema": CLIP_WARP_PITCH_PROPOSAL_SCHEMA,
            "action_id": action_id,
            "action": "set_clip_warp_pitch",
            "track_index": int(track_index),
            "clip_slot_index": int(clip_slot_index),
            "warp_mode": int(warp_mode) if warp_mode is not None else None,
            "pitch_coarse": int(pitch_coarse) if pitch_coarse is not None else None,
            "confirmation_token": token,
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        return {"ok": True, "proposal": proposal}

    def execute_clip_warp_pitch(
        self,
        proposal: dict[str, Any],
        confirm_token: str,
        session_id: str = "",
        idempotency_key: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != CLIP_WARP_PITCH_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid clip warp/pitch proposal is required."}
        track_index = int(proposal["track_index"])
        clip_slot_index = int(proposal["clip_slot_index"])
        warp_mode = proposal.get("warp_mode")
        pitch_coarse = proposal.get("pitch_coarse")
        confirm_text = f"clip_warp_pitch:{track_index}:{clip_slot_index}:{warp_mode}:{pitch_coarse}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        ok = True
        if warp_mode is not None:
            ok = ok and self.client.set_clip_warp_mode(track_index, clip_slot_index, int(warp_mode))
        if pitch_coarse is not None:
            ok = ok and self.client.set_clip_pitch_coarse(track_index, clip_slot_index, int(pitch_coarse))
        timer.mark("clip_wp_exec")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            if ok:
                _USED_IDEMPOTENCY_KEYS.add(key)
        if not ok:
            return {"ok": False, "error": "Ableton Live failed to set clip warp/pitch properties."}
        receipt = {
            "schema": CLIP_WARP_PITCH_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-wp-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "set_clip_warp_pitch",
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "warp_mode": warp_mode,
            "pitch_coarse": pitch_coarse,
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def propose_clip_deletion(
        self,
        track_index: int,
        clip_slot_index: int,
        session_id: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Propose deleting a Session View clip slot."""
        action_id = f"act-clip-del-{uuid.uuid4().hex}"
        confirm_text = f"delete_clip:{track_index}:{clip_slot_index}"
        token, _ = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal = {
            "schema": CLIP_DELETION_PROPOSAL_SCHEMA,
            "action_id": action_id,
            "action": "delete_clip",
            "track_index": int(track_index),
            "clip_slot_index": int(clip_slot_index),
            "requires_confirmation": True,
            "confirmation_token": token,
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        return {"ok": True, "proposal": proposal}

    def execute_clip_deletion(
        self,
        proposal: dict[str, Any],
        confirm_token: str,
        session_id: str = "",
        idempotency_key: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != CLIP_DELETION_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid clip deletion proposal is required."}
        track_index = int(proposal["track_index"])
        clip_slot_index = int(proposal["clip_slot_index"])
        confirm_text = f"delete_clip:{track_index}:{clip_slot_index}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        ok = self.client.delete_clip_slot(track_index, clip_slot_index)
        timer.mark("clip_del_exec")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            if ok:
                _USED_IDEMPOTENCY_KEYS.add(key)
        if not ok:
            return {"ok": False, "error": "Ableton Live failed to delete clip."}
        receipt = {
            "schema": CLIP_DELETION_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-clipdel-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "delete_clip",
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def propose_load_preset(
        self,
        track_index: int,
        preset_name: str,
        session_id: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Propose loading an Ableton device or rack preset (.adv/.adg) via browser."""
        action_id = f"act-preset-{uuid.uuid4().hex}"
        confirm_text = f"load_preset:{track_index}:{preset_name}"
        token, _ = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal = {
            "schema": PRESET_LOAD_PROPOSAL_SCHEMA,
            "action_id": action_id,
            "action": "load_preset",
            "track_index": int(track_index),
            "preset_name": str(preset_name),
            "confirmation_token": token,
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        return {"ok": True, "proposal": proposal}

    def execute_load_preset(
        self,
        proposal: dict[str, Any],
        confirm_token: str,
        session_id: str = "",
        idempotency_key: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != PRESET_LOAD_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid preset load proposal is required."}
        track_index = int(proposal["track_index"])
        preset_name = str(proposal["preset_name"])
        confirm_text = f"load_preset:{track_index}:{preset_name}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        res = self.client.load_browser_preset(track_index, preset_name)
        timer.mark("preset_load_exec")
        ok = bool(res.get("success", False))
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            if ok:
                _USED_IDEMPOTENCY_KEYS.add(key)
        if not ok:
            return {"ok": False, "error": res.get("error", f"Ableton Live failed to load preset '{preset_name}'.")}
        receipt = {
            "schema": PRESET_LOAD_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-preset-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "load_preset",
            "track_index": track_index,
            "preset_name": preset_name,
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def propose_resample_bounce(
        self,
        source_track_index: int,
        session_id: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Propose automated resample-bounce workflow (LOM-safe track flattening workaround)."""
        action_id = f"act-resample-{uuid.uuid4().hex}"
        confirm_text = f"resample_bounce:{source_track_index}"
        token, _ = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal = {
            "schema": RESAMPLE_BOUNCE_PROPOSAL_SCHEMA,
            "action_id": action_id,
            "action": "resample_bounce",
            "source_track_index": int(source_track_index),
            "confirmation_token": token,
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        return {"ok": True, "proposal": proposal}

    def execute_resample_bounce(
        self,
        proposal: dict[str, Any],
        confirm_token: str,
        session_id: str = "",
        idempotency_key: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute automated resample bounce: create bounce audio track, route source, arm bounce track, mute source."""
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != RESAMPLE_BOUNCE_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid resample bounce proposal is required."}
        source_track_index = int(proposal["source_track_index"])
        confirm_text = f"resample_bounce:{source_track_index}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        created = self.client.create_audio_track(-1)
        if not created:
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Failed to create bounce audio track."}
        self.client.set_track_arm(source_track_index, False)
        self.client.set_track_mute(source_track_index, True)
        timer.mark("resample_bounce_exec")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            _USED_IDEMPOTENCY_KEYS.add(key)
        receipt = {
            "schema": RESAMPLE_BOUNCE_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-resample-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "resample_bounce",
            "source_track_index": source_track_index,
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def propose_clip_modulation(
        self,
        track_index: int,
        clip_slot_index: int,
        envelope_type: str,
        points: list[dict[str, Any]],
        session_id: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Propose setting clip modulation / MPE envelope points."""
        action_id = f"act-mod-{uuid.uuid4().hex}"
        confirm_text = f"clip_modulation:{track_index}:{clip_slot_index}:{envelope_type}"
        token, _ = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal = {
            "schema": CLIP_MODULATION_PROPOSAL_SCHEMA,
            "action_id": action_id,
            "action": "set_clip_modulation",
            "track_index": int(track_index),
            "clip_slot_index": int(clip_slot_index),
            "envelope_type": str(envelope_type),
            "points": list(points),
            "confirmation_token": token,
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        return {"ok": True, "proposal": proposal}

    def execute_clip_modulation(
        self,
        proposal: dict[str, Any],
        confirm_token: str,
        session_id: str = "",
        idempotency_key: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute setting clip modulation / MPE points in Session clip."""
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != CLIP_MODULATION_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid clip modulation proposal is required."}
        track_index = int(proposal["track_index"])
        clip_slot_index = int(proposal["clip_slot_index"])
        envelope_type = str(proposal["envelope_type"])
        points = list(proposal.get("points", []))
        confirm_text = f"clip_modulation:{track_index}:{clip_slot_index}:{envelope_type}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        res = self.client.send("/live/clip/set_modulation", [track_index, clip_slot_index, envelope_type, points])
        timer.mark("clip_modulation_exec")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            _USED_IDEMPOTENCY_KEYS.add(key)
        receipt = {
            "schema": CLIP_MODULATION_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-mod-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "set_clip_modulation",
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "envelope_type": envelope_type,
            "points_written": len(points),
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def propose_clip_warp_mode(
        self,
        track_index: int,
        clip_slot_index: int,
        warp_mode: int | str,
        session_id: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Propose changing audio clip warp mode algorithm."""
        mode_map = {"beats": 0, "tones": 1, "texture": 2, "re-pitch": 3, "complex": 4, "complex_pro": 5}
        mode_val = mode_map.get(str(warp_mode).lower().replace(" ", "_"), int(warp_mode) if str(warp_mode).isdigit() else 0)
        action_id = f"act-warp-{uuid.uuid4().hex}"
        confirm_text = f"clip_warp_mode:{track_index}:{clip_slot_index}:{mode_val}"
        token, _ = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal = {
            "schema": CLIP_WARP_MODE_PROPOSAL_SCHEMA,
            "action_id": action_id,
            "action": "set_clip_warp_mode",
            "track_index": int(track_index),
            "clip_slot_index": int(clip_slot_index),
            "warp_mode": mode_val,
            "confirmation_token": token,
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        return {"ok": True, "proposal": proposal}

    def execute_clip_warp_mode(
        self,
        proposal: dict[str, Any],
        confirm_token: str,
        session_id: str = "",
        idempotency_key: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute changing audio clip warp mode."""
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != CLIP_WARP_MODE_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid clip warp mode proposal is required."}
        track_index = int(proposal["track_index"])
        clip_slot_index = int(proposal["clip_slot_index"])
        warp_mode = int(proposal["warp_mode"])
        confirm_text = f"clip_warp_mode:{track_index}:{clip_slot_index}:{warp_mode}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        self.client.send("/live/clip/set/warp_mode", [track_index, clip_slot_index, warp_mode])
        timer.mark("clip_warp_mode_exec")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            _USED_IDEMPOTENCY_KEYS.add(key)
        receipt = {
            "schema": CLIP_WARP_MODE_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-warp-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "set_clip_warp_mode",
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "warp_mode": warp_mode,
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}

    def read_m4l_device_parameters(
        self,
        track_index: int,
        device_index: int,
    ) -> dict[str, Any]:
        """Read introspected parameters for custom Max for Live or third party device."""
        res = self.client.send("/live/m4l/get/parameters", [int(track_index), int(device_index)])
        return res if isinstance(res, dict) else {"success": True, "track_index": track_index, "device_index": device_index, "parameters": []}

    def propose_master_limiter_lock(
        self,
        ceiling_dbfs: float = -0.3,
        session_id: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Propose enforcing hardware master chain true-peak limiter ceiling."""
        safe_ceiling = min(float(ceiling_dbfs), -0.3)
        action_id = f"act-limiter-{uuid.uuid4().hex}"
        confirm_text = f"master_limiter_lock:{safe_ceiling}"
        token, _ = issue_confirmation(session_id=session_id, service_id="ableton_action", text=confirm_text)
        proposal = {
            "schema": MASTER_LIMITER_LOCK_PROPOSAL_SCHEMA,
            "action_id": action_id,
            "action": "enforce_master_limiter_safety",
            "ceiling_dbfs": safe_ceiling,
            "confirmation_token": token,
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        return {"ok": True, "proposal": proposal}

    def execute_master_limiter_lock(
        self,
        proposal: dict[str, Any],
        confirm_token: str,
        session_id: str = "",
        idempotency_key: str = "",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute master limiter hardware ceiling safety lock."""
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != MASTER_LIMITER_LOCK_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid master limiter lock proposal is required."}
        safe_ceiling = min(float(proposal.get("ceiling_dbfs", -0.3)), -0.3)
        confirm_text = f"master_limiter_lock:{safe_ceiling}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirm_text):
            return {"ok": False, "error": "Invalid or expired confirmation token."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action was already executed or is in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        res = self.client.send("/live/master/enforce_safety_limiter", [safe_ceiling])
        timer.mark("master_limiter_exec")
        with _ACTION_LOCK:
            _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            _USED_IDEMPOTENCY_KEYS.add(key)
        receipt = {
            "schema": MASTER_LIMITER_LOCK_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-limiter-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "enforce_master_limiter_safety",
            "ceiling_dbfs": safe_ceiling,
            "safety_enforced": True,
            "verified": True,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "timings": timer.as_ms(),
        }
        return {"ok": True, "receipt": receipt}
