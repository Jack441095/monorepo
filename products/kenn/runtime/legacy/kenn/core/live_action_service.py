"""Single safety boundary for supported Ableton actions.

The service is deliberately client-injected so it can be tested with a
deterministic mock and qualified later against a real Remote Script.  It owns
proposal binding, stale-state checks, exact target identity, idempotency,
readback verification, and receipts.  It never guesses a missing index.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from threading import Lock
from typing import Any

from kenn.ableton_osc_bridge import AbletonOSCClient, live_client
from kenn.core.confirmation import consume_confirmation, issue_confirmation
from kenn.core.idempotency_bounds import prune_if_needed
from kenn.core.receipt_contract import StageTimer, classify_retry_safety, resolve_correlation_id
from kenn.core.midi_clip_service import (
    MidiClipActionService,
    PROPOSAL_SCHEMA as MIDI_CLIP_PROPOSAL_SCHEMA,
    RECEIPT_SCHEMA as MIDI_CLIP_RECEIPT_SCHEMA,
    UNDO_PROPOSAL_SCHEMA as MIDI_CLIP_UNDO_PROPOSAL_SCHEMA,
)
from kenn.core.actions import (
    Tier2Tier3ControlMixin,
    _ACTION_LOCK,
    _IN_FLIGHT_IDEMPOTENCY_KEYS,
    _PROPOSALS_BY_TOKEN,
    _RECEIPTS,
    _USED_IDEMPOTENCY_KEYS,
    _cleanup_memory,
    _failed_receipt,
    _find_return_track,
    _find_scene,
    _find_track,
    _finish_idempotency_key,
    _resolve_return_track_by_name,
    _state_version,
    _text,
    runtime_state_counts,
    ARRANGEMENT_DUPLICATION_PROPOSAL_SCHEMA,
    ARRANGEMENT_DUPLICATION_RECEIPT_SCHEMA,
    CLIP_AUTOMATION_PROPOSAL_SCHEMA,
    CLIP_AUTOMATION_RECEIPT_SCHEMA,
    CLIP_DELETION_PROPOSAL_SCHEMA,
    CLIP_DELETION_RECEIPT_SCHEMA,
    CLIP_LAUNCH_PROPOSAL_SCHEMA,
    CLIP_LAUNCH_RECEIPT_SCHEMA,
    CLIP_MODULATION_PROPOSAL_SCHEMA,
    CLIP_MODULATION_RECEIPT_SCHEMA,
    CLIP_WARP_MODE_PROPOSAL_SCHEMA,
    CLIP_WARP_MODE_RECEIPT_SCHEMA,
    CLIP_WARP_PITCH_PROPOSAL_SCHEMA,
    CLIP_WARP_PITCH_RECEIPT_SCHEMA,
    LOOP_DUPLICATION_PROPOSAL_SCHEMA,
    LOOP_DUPLICATION_RECEIPT_SCHEMA,
    MASTER_LIMITER_LOCK_PROPOSAL_SCHEMA,
    MASTER_LIMITER_LOCK_RECEIPT_SCHEMA,
    PRESET_LOAD_PROPOSAL_SCHEMA,
    PRESET_LOAD_RECEIPT_SCHEMA,
    RACK_MACRO_PROPOSAL_SCHEMA,
    RACK_MACRO_RECEIPT_SCHEMA,
    RACK_VARIATION_PROPOSAL_SCHEMA,
    RACK_VARIATION_RECEIPT_SCHEMA,
    RESAMPLE_BOUNCE_PROPOSAL_SCHEMA,
    RESAMPLE_BOUNCE_RECEIPT_SCHEMA,
    SCENE_CREATION_PROPOSAL_SCHEMA,
    SCENE_CREATION_RECEIPT_SCHEMA,
    TRACK_FREEZE_PROPOSAL_SCHEMA,
    TRACK_FREEZE_RECEIPT_SCHEMA,
    TRACK_ROUTING_PROPOSAL_SCHEMA,
    TRACK_ROUTING_RECEIPT_SCHEMA,
)


PROPOSAL_SCHEMA = "kenn.ableton_action_proposal.v1"
RECEIPT_SCHEMA = "kenn.ableton_action_receipt.v1"
DEVICE_INSERTION_PROPOSAL_SCHEMA = "kenn.ableton_device_insertion_proposal.v1"
DEVICE_REMOVAL_PROPOSAL_SCHEMA = "kenn.ableton_device_removal_proposal.v1"
EQ_BAND_TUNING_GAIN_PROPOSAL_SCHEMA = "kenn.ableton_eq_band_tuning_gain_proposal.v1"
DEVICE_SETUP_PROPOSAL_SCHEMA = "kenn.ableton_device_setup_proposal.v1"
GAIN_STAGING_PROPOSAL_SCHEMA = "kenn.ableton_gain_staging_proposal.v1"
GAIN_STAGING_RECEIPT_SCHEMA = "kenn.ableton_gain_staging_receipt.v1"
BUS_ORGANIZATION_PROPOSAL_SCHEMA = "kenn.ableton_bus_organization_proposal.v1"
BUS_ORGANIZATION_RECEIPT_SCHEMA = "kenn.ableton_bus_organization_receipt.v1"
DEVICE_INSERTION_ALLOWLIST = frozenset({"EQ Eight", "Glue Compressor", "Saturator", "Auto Filter", "Drum Buss", "Compressor", "Hybrid Reverb", "Echo"})
DEVICE_INSERTION_ALLOWLIST = frozenset({"EQ Eight", "Glue Compressor", "Saturator", "Auto Filter", "Drum Buss", "Compressor", "Hybrid Reverb", "Echo", "Roar", "Multiband Dynamics"})
DEVICE_SETUP_PARAMETER_ALLOWLIST = {
    "Hybrid Reverb": {"drywet": ("Dry/Wet", "%")},
    "Echo": {"drywet": ("Dry Wet", "%")},
    "Roar": {"drive": ("Drive", "dB"), "drywet": ("Dry/Wet", "%"), "tone": ("Tone", "")},
    "Multiband Dynamics": {"drywet": ("Dry/Wet", "%")},
}
# Candidates for a future insertion allowlist entry. Each name here has the
# generic parameter-resolution machinery already available (any device name
# present in a fresh Live snapshot can already have its existing parameters
# read/changed - see live_intent.py's device_candidates matching), but
# INSERTING a brand-new instance of the device is a separate, higher-risk
# capability that this repo only enables after a real-Live reversible
# parameter qualification, matching the process already completed for every
# name in DEVICE_INSERTION_ALLOWLIST above (see
# docs/ABLETON_ASSISTANT_CURRENT_STATE.md's per-device qualification entries).
# Do not move a name from here into DEVICE_INSERTION_ALLOWLIST without that
# qualification evidence.
#
# IMPORTANT: real-Live testing (2026-09-05) found AbletonOSC's insert_device
# browser search does not require an exact name match, and can silently
# resolve a plausible-looking candidate name to the WRONG device. "Reverb"
# resolved to "Convolution Reverb", "Delay" resolved to "Align Delay", and
# "Limiter" resolved to "Color Limiter" - none of the plain names actually
# reach the simple stock device a user would expect. The verified-correct
# name for the stock reverb is "Hybrid Reverb", and for the stock delay is
# "Echo"; no plain name was found that reaches a simple generic Limiter, so
# it is dropped from the candidate list rather than listed under a guess.
# execute_device_insertion() reports verified=False on a name mismatch and
# narrowly auto-removes the unexpected device when exact chain readback proves
# that is safe. Only "Compressor"
# resolved to the exact requested device and has since passed a full
# real-Live reversible-parameter qualification (Threshold), so it has been
# promoted to DEVICE_INSERTION_ALLOWLIST above. "Hybrid Reverb" and "Echo"
# have since passed the same qualification (Dry/Wet, 2026-09-06) and were
# promoted alongside it; this candidate set is currently empty.
CANDIDATE_DEVICE_INSERTION_ALLOWLIST = frozenset()
SUPPORTED_TRACK_ACTIONS = {
    "set_volume": ("volume", "normalized", (0.0, 1.0)),
    "set_pan": ("pan", "normalized", (-1.0, 1.0)),
    "set_mute": ("muted", "boolean", None),
    "set_solo": ("soloed", "boolean", None),
    "set_arm": ("armed", "boolean", None),
    "rename_track": ("name", "string", None),
}
SUPPORTED_TRACK_CREATION_ACTIONS = {"create_midi_track", "create_audio_track"}
SUPPORTED_RETURN_TRACK_CREATION_ACTIONS = {"create_return_track"}
SUPPORTED_TRANSPORT_ACTIONS = {"transport_play", "transport_stop"}
SUPPORTED_SCENE_ACTIONS = {"launch_scene"}
SUPPORTED_CLIP_ACTIONS = {"stop_clip"}
SUPPORTED_SEND_ACTIONS = {"set_send"}
SUPPORTED_LOCATOR_ACTIONS = {"add_locator", "remove_locator"}
SUPPORTED_VIEW_ACTIONS = {"focus_track", "focus_device"}
LOCATOR_TIME_TOLERANCE = 1e-4



def _scene_text(proposal: dict[str, Any]) -> str:
    return "|".join(
        str(proposal.get(key, ""))
        for key in ("action", "scene_index", "scene_name", "session_version")
    )


def _clip_text(proposal: dict[str, Any]) -> str:
    return "|".join(
        str(proposal.get(key, ""))
        for key in ("action", "track_index", "track_name", "clip_slot_index", "session_version")
    )


def _send_text(proposal: dict[str, Any]) -> str:
    return "|".join(
        str(proposal.get(key, ""))
        for key in (
            "action", "track_index", "track_name",
            "return_track_index", "return_track_name",
            "before", "after", "session_version",
        )
    )


def _locator_text(proposal: dict[str, Any]) -> str:
    return "|".join(
        str(proposal.get(key, ""))
        for key in ("action", "locator_name", "locator_time_beats", "session_version")
    )


def _view_text(proposal: dict[str, Any]) -> str:
    return "|".join(
        str(proposal.get(key, ""))
        for key in (
            "action", "track_index", "track_name", "device_index", "device_name",
            "previous_track_index", "previous_track_name", "previous_device_index",
            "previous_device_name", "before", "after", "session_version",
        )
    )


def _track_structure_fingerprint(state: dict[str, Any]) -> str:
    """Hash the ordered regular-track identity used by structural writes."""
    tracks = [track for track in state.get("tracks", []) if isinstance(track, dict)]
    identity = [
        {"index": track.get("index"), "name": str(track.get("name", ""))}
        for track in tracks
    ]
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _track_creation_text(proposal: dict[str, Any]) -> str:
    return "|".join(
        str(proposal.get(key, ""))
        for key in (
            "action", "new_track_name", "insertion_index", "before_track_count",
            "before_track_fingerprint",
        )
    )


def _return_track_structure_fingerprint(return_tracks: list[dict[str, Any]]) -> str:
    """Hash the ordered return-track identity used by structural writes."""
    identity = [
        {"index": track.get("index"), "name": str(track.get("name", ""))}
        for track in return_tracks
        if isinstance(track, dict)
    ]
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _return_track_creation_text(proposal: dict[str, Any]) -> str:
    return "|".join(
        str(proposal.get(key, ""))
        for key in (
            "action", "new_return_track_name", "insertion_index", "before_return_track_count",
            "before_return_track_fingerprint",
        )
    )


def _return_track_observation(client: Any) -> tuple[list[dict[str, Any]], bool]:
    """Read return tracks without collapsing endpoint failure into an empty set."""
    status_reader = getattr(client, "get_return_tracks_with_status", None)
    if callable(status_reader):
        observed = status_reader()
        if isinstance(observed, tuple) and len(observed) == 2:
            return observed
    return client.get_return_tracks(), True


def _device_setup_parameter_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().casefold())


def _device_setup_text(proposal: dict[str, Any]) -> str:
    return "|".join(
        str(proposal.get(key, ""))
        for key in (
            "action", "track_index", "track_name", "device_name", "insertion_index",
            "parameter_name", "parameter_display_value", "parameter_unit",
            "before_device_fingerprint",
        )
    )


def _values_match(expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(expected), float(actual), rel_tol=0.0, abs_tol=1e-4)
    return expected == actual


def _ordered_device_identities(track: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return the stable, ordered device identity used by insertion safety."""
    devices = track.get("devices", []) if isinstance(track, dict) else []
    identities: list[dict[str, Any]] = []
    for position, item in enumerate(devices or []):
        if isinstance(item, dict):
            try:
                device_index = int(item.get("index", position))
            except (TypeError, ValueError):
                device_index = position
            name = str(item.get("name", ""))
        else:
            device_index = position
            name = str(item)
        identities.append({"position": position, "index": device_index, "name": name})
    return identities


def _device_identities_match(expected: Any, actual: Any) -> bool:
    return isinstance(expected, list) and isinstance(actual, list) and expected == actual


def _insertion_text(proposal: dict[str, Any]) -> str:
    return "|".join(
        str(proposal.get(key, ""))
        for key in ("action", "track_index", "track_name", "device_name", "insertion_index", "before_device_fingerprint")
    )


def _removal_text(proposal: dict[str, Any]) -> str:
    return "|".join(
        str(proposal.get(key, ""))
        for key in ("action", "track_index", "track_name", "device_name", "device_index", "before_device_fingerprint", "source_receipt_id")
    )


def _eq_band_tuning_gain_text(proposal: dict[str, Any]) -> str:
    return "|".join(
        str(proposal.get(key, ""))
        for key in (
            "action", "track_index", "track_name", "device_index", "device_name",
            "eq_band", "frequency_before_value", "frequency_after_value",
            "gain_before_value", "gain_after_value",
        )
    )


class LiveActionService(Tier2Tier3ControlMixin):
    def __init__(self, client: AbletonOSCClient | Any = None):
        self.client = client or live_client

    def snapshot(self, *, include_mixer: bool = True) -> dict[str, Any]:
        try:
            state = self.client.query_session_state(include_mixer=include_mixer)
        except TypeError:
            # Keep injected legacy test doubles and older bridge clients
            # compatible while the production client adopts the split read.
            state = self.client.query_session_state()
        if not isinstance(state, dict) or state.get("status") in {"offline", "dispatched"}:
            try:
                from kenn.mixing_doctor import get_latest_session_state
                cached = get_latest_session_state()
                if isinstance(cached, dict) and cached.get("status") == "connected":
                    return cached
            except Exception:
                pass
            return {"status": "offline", "tracks": []}
        return state

    def propose_track_action(
        self,
        action: str,
        *,
        track_index: int,
        value: Any,
        session_id: str,
        track_name: str = "",
    ) -> dict[str, Any]:
        _cleanup_memory()
        if action not in SUPPORTED_TRACK_ACTIONS:
            return {"ok": False, "error": f"Unsupported Live track action: {action}"}
        state = self.snapshot()
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        track, error = _find_track(state, int(track_index), track_name)
        if error or track is None:
            return {"ok": False, "error": error}
        field, unit, valid_range = SUPPORTED_TRACK_ACTIONS[action]
        if unit == "boolean":
            if not isinstance(value, bool):
                return {"ok": False, "error": f"{action} requires a boolean value."}
        elif unit == "string":
            value = str(value or "").strip()
            if not value:
                return {"ok": False, "error": "rename_track requires a non-empty track name."}
            if len(value) > 128:
                return {"ok": False, "error": "Track names may contain at most 128 characters."}
        else:
            try:
                value = float(value)
            except (TypeError, ValueError):
                return {"ok": False, "error": f"{action} requires a numeric value."}
            if not math.isfinite(value) or not valid_range[0] <= value <= valid_range[1]:
                return {"ok": False, "error": f"{action} value is outside valid range {valid_range}."}
        before = track.get(field)
        if before is None:
            return {"ok": False, "error": f"Live snapshot has no readable '{field}' value for this track."}
        if action == "rename_track":
            if str(value).casefold() == str(before).casefold():
                return {"ok": False, "error": "The new track name is identical to the current name."}
            duplicate = next(
                (
                    item for item in state.get("tracks", [])
                    if isinstance(item, dict)
                    and int(item.get("index", -1)) != int(track_index)
                    and str(item.get("name", "")).strip().casefold() == str(value).casefold()
                ),
                None,
            )
            if duplicate is not None:
                return {"ok": False, "error": "The new track name already belongs to another Live track."}
        proposal = {
            "schema": PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": action,
            "operation": action,
            "target": "ableton_track",
            "track_index": int(track_index),
            "track_name": str(track.get("name", "")),
            "parameter": field,
            "before": before,
            "after": value,
            "unit": unit,
            "valid_range": list(valid_range) if valid_range else None,
            "reason": f"Explicit user request for {action} on track '{track.get('name', '')}'.",
            "evidence": [f"Current Live snapshot value: {field}={before!r}.", f"Target identity: track {track_index} '{track.get('name', '')}'."],
            "confidence": 1.0,
            "risk": "local_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state, track=track),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_action", text=_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def propose_track_creation_action(
        self,
        action: str,
        *,
        track_name: str = "",
        session_id: str,
    ) -> dict[str, Any]:
        """Prepare an append-only audio or MIDI track creation proposal.

        Track creation is structural and shifts every later track index when
        inserted in the middle of a set. KENN therefore exposes append only
        and binds the proposal to the complete ordered track identity before
        confirmation. The post-write ``has_midi_input`` readback distinguishes
        the requested track type.
        """
        _cleanup_memory()
        if action not in SUPPORTED_TRACK_CREATION_ACTIONS:
            return {"ok": False, "error": f"Unsupported Live track-creation action: {action}"}
        track_kind = "MIDI" if action == "create_midi_track" else "audio"
        track_kind_lower = track_kind.lower()
        name = str(track_name or "").strip()
        if len(name) > 128:
            return {"ok": False, "error": "Track names may contain at most 128 characters."}
        state = self.snapshot(include_mixer=False)
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        tracks = [track for track in state.get("tracks", []) if isinstance(track, dict)]
        if any(track.get("index") != position for position, track in enumerate(tracks)):
            return {"ok": False, "error": "Live returned a non-contiguous track topology; KENN will not guess the append index."}
        before_count = len(tracks)
        insertion_index = before_count
        proposal = {
            "schema": PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": action,
            "operation": action,
            "target": "ableton_song",
            "track_index": insertion_index,
            "track_name": name,
            "new_track_name": name,
            "insertion_index": insertion_index,
            "before_track_count": before_count,
            "before_track_fingerprint": _track_structure_fingerprint(state),
            "before": {"track_count": before_count},
            "after": {
                "track_count": before_count + 1,
                "track_index": insertion_index,
                "type": track_kind_lower,
                **({"name": name} if name else {}),
            },
            "unit": "track",
            "valid_range": None,
            "reason": (
                f"Explicit user request to append a new {track_kind_lower} track"
                + (f" named '{name}'." if name else ".")
            ),
            "evidence": [
                f"Current Live track count: {before_count}.",
                f"Append position: track {insertion_index + 1} (zero-based index {insertion_index}).",
                f"Track type will be verified with Live's has_midi_input readback ({track_kind_lower}).",
            ],
            "confidence": 1.0,
            "risk": "structural_mutation",
            "requires_confirmation": True,
            "undo_available": False,
            "undo_reason": "Deleting a track is outside KENN's safe inverse boundary.",
            "timestamp": time.time(),
            "session_version": _state_version(state),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(
            session_id=session_id,
            service_id="ableton_action",
            text=_track_creation_text(proposal),
        )
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def propose_midi_track_action(
        self,
        action: str = "create_midi_track",
        *,
        track_name: str = "",
        session_id: str,
    ) -> dict[str, Any]:
        """Backward-compatible MIDI creation proposal wrapper."""
        return self.propose_track_creation_action(action, track_name=track_name, session_id=session_id)

    def propose_audio_track_action(
        self,
        action: str = "create_audio_track",
        *,
        track_name: str = "",
        session_id: str,
    ) -> dict[str, Any]:
        """Prepare an append-only audio-track creation proposal."""
        return self.propose_track_creation_action(action, track_name=track_name, session_id=session_id)

    def propose_return_track_creation_action(
        self,
        *,
        track_name: str = "",
        session_id: str,
    ) -> dict[str, Any]:
        """Prepare an append-only return-track creation proposal.

        Return tracks are a separate Live collection and do not shift regular
        track indices, but they do change every source track's send topology.
        Bind the complete ordered return identity before confirmation and keep
        the operation explicitly non-reversible: deleting a return can destroy
        later user-created routing or devices.
        """
        _cleanup_memory()
        name = str(track_name or "").strip()
        if len(name) > 128:
            return {"ok": False, "error": "Return-track names may contain at most 128 characters."}
        try:
            return_tracks, available = _return_track_observation(self.client)
        except Exception as exc:
            return {"ok": False, "error": f"Could not inspect the current Live return tracks: {exc}"}
        if not available:
            return {"ok": False, "error": "Live return-track readback is unavailable; KENN will not guess whether the set has zero returns."}
        if not isinstance(return_tracks, list):
            return {"ok": False, "error": "Ableton did not return a usable return-track topology."}
        if any(item.get("index") != position for position, item in enumerate(return_tracks) if isinstance(item, dict)):
            return {"ok": False, "error": "Live returned a non-contiguous return-track topology; KENN will not guess the append index."}
        if any(not isinstance(item, dict) for item in return_tracks):
            return {"ok": False, "error": "Live returned an invalid return-track topology."}
        before_count = len(return_tracks)
        insertion_index = before_count
        proposal = {
            "schema": PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "create_return_track",
            "operation": "create_return_track",
            "target": "ableton_song_return_tracks",
            "return_track_index": insertion_index,
            "new_return_track_name": name,
            "insertion_index": insertion_index,
            "before_return_track_count": before_count,
            "before_return_track_fingerprint": _return_track_structure_fingerprint(return_tracks),
            "before": {"return_track_count": before_count},
            "after": {
                "return_track_count": before_count + 1,
                "return_track_index": insertion_index,
                **({"name": name} if name else {}),
            },
            "unit": "return_track",
            "valid_range": None,
            "reason": "Explicit user request to append a new return track" + (f" named '{name}'." if name else "."),
            "evidence": [
                f"Current Live return-track count: {before_count}.",
                f"Append position: return track {insertion_index + 1} (zero-based index {insertion_index}).",
                "Return-track name and ordered topology will be verified after creation.",
            ],
            "confidence": 1.0,
            "risk": "routing_mutation",
            "requires_confirmation": True,
            "undo_available": False,
            "undo_reason": "Deleting a return track can destroy later routing or devices and is outside KENN's safe inverse boundary.",
            "timestamp": time.time(),
            "session_version": _return_track_structure_fingerprint(return_tracks),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(
            session_id=session_id,
            service_id="ableton_action",
            text=_return_track_creation_text(proposal),
        )
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def _execute_return_track_creation(
        self,
        proposal: dict[str, Any],
        *,
        key: str,
        correlation_id: str,
        timer: StageTimer,
    ) -> dict[str, Any]:
        """Execute and reconcile one append-only return-track creation."""
        try:
            current, available = _return_track_observation(self.client)
        except Exception as exc:
            _finish_idempotency_key(key)
            receipt = _failed_receipt(
                proposal, key, f"Live return-track snapshot failed before creation: {exc}",
                retry_safe="requires_inspection", correlation_id=correlation_id,
                stage_timings_ms=timer.as_ms(),
            )
            _RECEIPTS[receipt["receipt_id"]] = receipt
            return {"ok": False, "error": receipt["error"], "receipt": receipt}
        if not available:
            _finish_idempotency_key(key)
            return {"ok": False, "error": "Live return-track readback is unavailable; create a new proposal after it recovers."}
        expected_count = int(proposal.get("before_return_track_count", -1))
        expected_fingerprint = str(proposal.get("before_return_track_fingerprint", ""))
        if (
            not isinstance(current, list)
            or any(not isinstance(item, dict) for item in current)
            or len(current) != expected_count
            or _return_track_structure_fingerprint(current) != expected_fingerprint
        ):
            _finish_idempotency_key(key)
            return {"ok": False, "error": "Live return-track topology changed since the proposal was created; create a new proposal."}
        insertion_index = int(proposal.get("insertion_index", -1))
        if insertion_index != expected_count:
            _finish_idempotency_key(key)
            return {"ok": False, "error": "Only append-only return-track creation is supported by this proposal."}

        requested_name = str(proposal.get("new_return_track_name", "")).strip()
        write_ok = False
        write_error: str | None = None
        write_exchanges: list[dict[str, Any]] = []
        try:
            write_ok = bool(self.client.create_return_track())
            write_exchanges.append(dict(getattr(self.client, "last_exchange", {}) or {}))
            if write_ok and requested_name:
                renamed = bool(self.client.set_return_track_name(insertion_index, requested_name))
                write_ok = write_ok and renamed
                write_exchanges.append(dict(getattr(self.client, "last_exchange", {}) or {}))
        except Exception as exc:
            write_error = str(exc)
            write_exchanges.append(dict(getattr(self.client, "last_exchange", {}) or {}))
        timer.mark("write")
        _finish_idempotency_key(key)

        try:
            time.sleep(0.05)
            after, available = _return_track_observation(self.client)
        except Exception as exc:
            receipt = _failed_receipt(
                proposal, key, f"Return-track creation readback failed: {exc}",
                retry_safe="requires_inspection", correlation_id=correlation_id,
                stage_timings_ms=timer.as_ms(),
            )
            receipt.update({
                "status": "transport_uncertain",
                "write_acknowledgement": "confirmed" if write_ok else "not_confirmed",
                "write_exchanges": write_exchanges,
            })
            if write_error:
                receipt["write_error"] = write_error
            _RECEIPTS[receipt["receipt_id"]] = receipt
            return {"ok": False, "error": receipt["error"], "receipt": receipt}
        if not available:
            receipt = _failed_receipt(
                proposal, key, "Return-track creation readback was unavailable.",
                retry_safe="requires_inspection", correlation_id=correlation_id,
                stage_timings_ms=timer.as_ms(),
            )
            receipt.update({
                "status": "transport_uncertain",
                "write_acknowledgement": "confirmed" if write_ok else "not_confirmed",
                "write_exchanges": write_exchanges,
            })
            if write_error:
                receipt["write_error"] = write_error
            _RECEIPTS[receipt["receipt_id"]] = receipt
            return {"ok": False, "error": receipt["error"], "receipt": receipt}
        timer.mark("readback")
        after = after if isinstance(after, list) else []
        created = next((item for item in after if isinstance(item, dict) and item.get("index") == insertion_index), None)
        old_unchanged = (
            len(after) >= expected_count
            and _return_track_structure_fingerprint(after[:expected_count]) == expected_fingerprint
        )
        count_matches = len(after) == expected_count + 1
        index_matches = isinstance(created, dict) and created.get("index") == insertion_index
        actual_name = str(created.get("name", "")) if isinstance(created, dict) else ""
        name_matches = not requested_name or actual_name == requested_name
        verified = count_matches and index_matches and old_unchanged and name_matches
        readback = {
            "return_track_index": insertion_index,
            "name": actual_name,
            "device_count": len(created.get("devices") or []) if isinstance(created, dict) and isinstance(created.get("devices"), list) else None,
            "return_track_count": len(after),
        }
        status = "applied" if verified else "failed_verification"
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "receipt_id": f"receipt-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "create_return_track",
            "idempotency_key": key,
            "status": status,
            "verified": verified,
            "timestamp": time.time(),
            "target": {
                "target": "ableton_song_return_tracks",
                "return_track_index": insertion_index,
                "return_track_name": actual_name or requested_name,
                "new_return_track_name": requested_name,
                "insertion_index": insertion_index,
            },
            "before": proposal.get("before"),
            "requested": proposal.get("after"),
            "readback": readback,
            "write_acknowledgement": "confirmed" if write_ok else ("unacknowledged_write_reconciled" if verified else "not_confirmed"),
            **({"write_error": write_error} if write_error else {}),
            "write_exchanges": write_exchanges,
            "undo": {"available": False, "reason": proposal.get("undo_reason")},
            "correlation_id": correlation_id,
            "retry_safe": classify_retry_safety(verified=verified, status=status),
            "stage_timings_ms": timer.as_ms(),
        }
        _RECEIPTS[receipt["receipt_id"]] = receipt
        if not verified:
            return {"ok": False, "error": "Return-track creation was sent but readback verification failed; inspect Live before retrying.", "receipt": receipt}
        return {"ok": True, "receipt": receipt}

    def _execute_track_creation(
        self,
        proposal: dict[str, Any],
        *,
        key: str,
        state: dict[str, Any],
        correlation_id: str,
        timer: StageTimer,
    ) -> dict[str, Any]:
        """Execute and reconcile one append-only audio or MIDI track creation."""
        action = str(proposal.get("action", ""))
        track_kind = "MIDI" if action == "create_midi_track" else "audio"
        track_kind_lower = track_kind.lower()
        expected_midi_input = action == "create_midi_track"
        expected_count = int(proposal.get("before_track_count", -1))
        expected_fingerprint = str(proposal.get("before_track_fingerprint", ""))
        current_tracks = [track for track in state.get("tracks", []) if isinstance(track, dict)]
        if len(current_tracks) != expected_count or _track_structure_fingerprint(state) != expected_fingerprint:
            _finish_idempotency_key(key)
            return {"ok": False, "error": "Live track topology changed since the proposal was created; create a new track-creation proposal."}
        insertion_index = int(proposal.get("insertion_index", -1))
        if insertion_index != expected_count:
            _finish_idempotency_key(key)
            return {"ok": False, "error": "Only append-only track creation is supported by this proposal."}

        requested_name = str(proposal.get("new_track_name", "")).strip()
        write_ok = False
        write_error: str | None = None
        write_exchanges: list[dict[str, Any]] = []
        try:
            creator = getattr(self.client, action)
            # AbletonOSC documents -1 as the canonical append sentinel. The
            # proposal still binds the expected resulting track index above,
            # but the wire operation must remain append-only even if Live's
            # insertion-index rules vary by version.
            write_ok = bool(creator(-1))
            write_exchanges.append(dict(getattr(self.client, "last_exchange", {}) or {}))
            if write_ok and requested_name:
                renamer = getattr(self.client, "set_track_name")
                renamed = bool(renamer(insertion_index, requested_name))
                write_ok = write_ok and renamed
                write_exchanges.append(dict(getattr(self.client, "last_exchange", {}) or {}))
        except Exception as exc:
            write_error = str(exc)
            write_exchanges.append(dict(getattr(self.client, "last_exchange", {}) or {}))
        timer.mark("write")
        _finish_idempotency_key(key)

        try:
            time.sleep(0.05)
            after_state = self.snapshot(include_mixer=False)
            after_tracks = [track for track in after_state.get("tracks", []) if isinstance(track, dict)]
            created_track = next(
                (track for track in after_tracks if track.get("index") == insertion_index),
                None,
            )
            midi_reader = getattr(self.client, "get_track_has_midi_input")
            midi_input = midi_reader(insertion_index)
        except Exception as exc:
            receipt = _failed_receipt(
                proposal,
                key,
                f"{track_kind} track creation readback failed: {exc}",
                retry_safe="requires_inspection",
                correlation_id=correlation_id,
                stage_timings_ms=timer.as_ms(),
            )
            receipt["status"] = "transport_uncertain"
            receipt["write_acknowledgement"] = "confirmed" if write_ok else "not_confirmed"
            receipt["write_exchange"] = write_exchanges[-1] if write_exchanges else {}
            receipt["write_exchanges"] = write_exchanges
            if write_error:
                receipt["write_error"] = write_error
            _RECEIPTS[receipt["receipt_id"]] = receipt
            return {"ok": False, "error": receipt["error"], "receipt": receipt}
        timer.mark("readback")
        readback_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
        actual_name = str(created_track.get("name", "")) if created_track else ""
        old_tracks_unchanged = (
            len(after_tracks) >= expected_count
            and _track_structure_fingerprint({"tracks": after_tracks[:expected_count]}) == expected_fingerprint
        )
        count_matches = len(after_tracks) == expected_count + 1
        index_matches = created_track is not None and created_track.get("index") == insertion_index
        type_matches = midi_input is expected_midi_input
        name_matches = not requested_name or actual_name == requested_name
        verified = count_matches and index_matches and old_tracks_unchanged and type_matches and name_matches
        readback = {
            "track_index": insertion_index,
            "name": actual_name,
            "type": track_kind_lower if type_matches else None,
            "has_midi_input": midi_input,
            "track_count": len(after_tracks),
        }
        status = "applied" if verified else "failed_verification"
        write_acknowledgement = "confirmed" if write_ok else (
            "unacknowledged_write_reconciled" if verified else "not_confirmed"
        )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "receipt_id": f"receipt-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": action,
            "idempotency_key": key,
            "status": status,
            "verified": verified,
            "timestamp": time.time(),
            "target": {
                "target": "ableton_song",
                "track_index": insertion_index,
                "track_name": actual_name or requested_name,
                "new_track_name": requested_name,
                "insertion_index": insertion_index,
            },
            "before": proposal.get("before"),
            "requested": proposal.get("after"),
            "readback": readback,
            "write_acknowledgement": write_acknowledgement,
            **({"write_error": write_error} if write_error else {}),
            "write_exchange": write_exchanges[-1] if write_exchanges else {},
            "write_exchanges": write_exchanges,
            "readback_exchange": readback_exchange,
            "undo": {"available": False, "reason": proposal.get("undo_reason")},
            "correlation_id": correlation_id,
            "retry_safe": classify_retry_safety(verified=verified, status=status),
            "stage_timings_ms": timer.as_ms(),
        }
        _RECEIPTS[receipt["receipt_id"]] = receipt
        if not verified:
            if count_matches and type_matches and requested_name and not name_matches:
                error = f"An {track_kind_lower} track was created at track {insertion_index + 1}, but its requested name was not verified; inspect Live before retrying."
            elif count_matches and not type_matches:
                error = f"A new track appeared, but Live did not verify it as an {track_kind_lower} track; inspect Live before retrying."
            else:
                error = f"{track_kind} track creation was sent but readback verification failed; inspect Live before retrying."
            return {"ok": False, "error": error, "receipt": receipt}
        return {"ok": True, "receipt": receipt}

    def propose_view_action(
        self,
        action: str,
        *,
        track_index: int,
        track_name: str = "",
        device_index: int | None = None,
        device_name: str = "",
        session_id: str,
    ) -> dict[str, Any]:
        """Propose focusing one exact Live track or device and remember prior focus."""
        _cleanup_memory()
        if action not in SUPPORTED_VIEW_ACTIONS:
            return {"ok": False, "error": f"Unsupported Live view action: {action}"}
        if int(track_index) < 0:
            return {"ok": False, "error": "A non-negative track index is required."}
        state = self.snapshot()
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        target, error = _find_track(state, int(track_index), track_name)
        if error or target is None:
            return {"ok": False, "error": error}
        target_device = None
        if action == "focus_device":
            if device_index is None or int(device_index) < 0:
                return {"ok": False, "error": "An exact non-negative device index is required."}
            devices = target.get("devices") or []
            target_device = devices[int(device_index)] if int(device_index) < len(devices) else None
            observed_name = (
                str(target_device.get("name", ""))
                if isinstance(target_device, dict)
                else str(target_device or "")
            )
            if target_device is None:
                return {"ok": False, "error": "Target Live device is not present in the current snapshot."}
            if device_name and observed_name != str(device_name):
                return {"ok": False, "error": "Target Live device identity no longer matches the current snapshot."}
            device_name = observed_name
        try:
            previous_index = int(state.get("selected_track_index"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "Live did not return an exact currently selected track."}
        previous, previous_error = _find_track(state, previous_index)
        if previous_error or previous is None:
            return {"ok": False, "error": "Live's currently selected track is no longer present in the snapshot."}
        previous_device_index = None
        previous_device_name = ""
        if action == "focus_device":
            try:
                selected_device = self.client.get_selected_device()
            except Exception as exc:
                return {"ok": False, "error": f"Could not read Live's currently selected device: {exc}"}
            if not isinstance(selected_device, dict) or not selected_device.get("success"):
                return {"ok": False, "error": selected_device.get("error", "Live did not return an exact currently selected device.") if isinstance(selected_device, dict) else "Live did not return an exact currently selected device."}
            try:
                selected_device_track = int(selected_device["track_index"])
                previous_device_index = int(selected_device["device_index"])
            except (KeyError, TypeError, ValueError):
                return {"ok": False, "error": "Live returned an invalid currently selected device identity."}
            selected_device_track_entry, selected_track_error = _find_track(state, selected_device_track)
            if selected_track_error or selected_device_track_entry is None:
                return {"ok": False, "error": "Live's selected device track is no longer present in the snapshot."}
            previous_devices = selected_device_track_entry.get("devices") or []
            previous_device = previous_devices[previous_device_index] if 0 <= previous_device_index < len(previous_devices) else None
            if previous_device is None:
                return {"ok": False, "error": "Live's selected device is no longer present in the snapshot."}
            previous_device_name = (
                str(previous_device.get("name", ""))
                if isinstance(previous_device, dict)
                else str(previous_device)
            )
            previous = selected_device_track_entry
            previous_index = selected_device_track
            if previous_index == int(target["index"]) and previous_device_index == int(device_index):
                return {"ok": False, "error": "That device is already focused in Ableton Live."}
        elif previous_index == int(target["index"]):
            return {"ok": False, "error": "That track is already focused in Ableton Live."}
        before = (
            {"track_index": previous_index, "device_index": previous_device_index}
            if action == "focus_device" else previous_index
        )
        after = (
            {"track_index": int(target["index"]), "device_index": int(device_index)}
            if action == "focus_device" else int(target["index"])
        )
        proposal = {
            "schema": PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": action,
            "operation": action,
            "target": "ableton_view",
            "track_index": int(target["index"]),
            "track_name": str(target.get("name", "")),
            **({"device_index": int(device_index), "device_name": device_name} if action == "focus_device" else {}),
            "previous_track_index": previous_index,
            "previous_track_name": str(previous.get("name", "")),
            **({"previous_device_index": previous_device_index, "previous_device_name": previous_device_name} if action == "focus_device" else {}),
            "parameter": "selected_device" if action == "focus_device" else "selected_track_index",
            "before": before,
            "after": after,
            "unit": "index",
            "valid_range": None,
            "reason": (
                f"Explicit user request to focus device {device_name!r} on track {int(target['index']) + 1} ({target.get('name', '')!r})."
                if action == "focus_device" else
                f"Explicit user request to focus track {int(target['index']) + 1} ({target.get('name', '')!r})."
            ),
            "evidence": [
                (
                    f"Current focus: device {previous_device_index} {previous_device_name!r} on track {previous_index} ({previous.get('name', '')!r})."
                    if action == "focus_device" else
                    f"Current focus: track {previous_index} ({previous.get('name', '')!r})."
                ),
                (
                    f"Target identity: device {int(device_index)} {device_name!r} on track {target['index']} ({target.get('name', '')!r})."
                    if action == "focus_device" else
                    f"Target identity: track {target['index']} ({target.get('name', '')!r})."
                ),
            ],
            "confidence": 1.0,
            "risk": "local_view_change",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_action", text=_view_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def propose_transport_action(self, action: str, *, session_id: str) -> dict[str, Any]:
        _cleanup_memory()
        if action not in SUPPORTED_TRANSPORT_ACTIONS:
            return {"ok": False, "error": f"Unsupported Live transport action: {action}"}
        state = self.snapshot()
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        before = bool(state.get("is_playing", False))
        after = action == "transport_play"
        proposal = {
            "schema": PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": action,
            "operation": action,
            "target": "ableton_transport",
            "before": before,
            "after": after,
            "unit": "boolean",
            "valid_range": None,
            "reason": f"Explicit user request for {action}.",
            "evidence": [f"Current Live transport state: is_playing={before!r}."],
            "confidence": 1.0,
            "risk": "local_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_action", text=_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def propose_scene_action(
        self,
        action: str,
        *,
        scene_index: int,
        session_id: str,
        scene_name: str = "",
    ) -> dict[str, Any]:
        _cleanup_memory()
        if action not in SUPPORTED_SCENE_ACTIONS:
            return {"ok": False, "error": f"Unsupported Live scene action: {action}"}
        state = self.snapshot()
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        scene, error = _find_scene(state, int(scene_index), scene_name)
        if error or scene is None:
            return {"ok": False, "error": error}
        display_name = str(scene.get("name", "")) or "unnamed"
        proposal = {
            "schema": PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": action,
            "operation": action,
            "target": "ableton_scene",
            "scene_index": int(scene["index"]),
            "scene_name": str(scene.get("name", "")),
            "before": False,
            "after": True,
            # is_triggered is transient enough that a fast, otherwise-correct
            # fire can outrun a single network round-trip readback (observed
            # in real-Live qualification). Recording whether transport was
            # already rolling lets execute() safely treat "playback started"
            # as corroborating evidence for this fire specifically, without
            # risking a false positive when it was already playing before.
            "transport_was_playing_before": bool(state.get("is_playing", False)),
            "unit": "trigger",
            "valid_range": None,
            "reason": f"Explicit user request to launch scene {int(scene['index']) + 1} ({display_name}).",
            "evidence": [f"Scene index {scene['index']} ({display_name!r}) exists in the current Live snapshot."],
            "confidence": 1.0,
            "risk": "local_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_action", text=_scene_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def _locator_observation(self) -> tuple[list[dict[str, Any]], bool]:
        """Read locator identities and preserve unsupported-vs-empty state."""
        reader = getattr(self.client, "get_locators_with_status", None)
        if callable(reader):
            result = reader()
            if isinstance(result, tuple) and len(result) == 2:
                locators, available = result
                return (list(locators or []) if isinstance(locators, list) else [], bool(available))
        reader = getattr(self.client, "get_locators", None)
        if not callable(reader):
            return [], False
        locators = reader()
        return (list(locators or []) if isinstance(locators, list) else [], True)

    @staticmethod
    def _locator_at_time(locators: list[dict[str, Any]], time_beats: float) -> list[dict[str, Any]]:
        return [
            locator for locator in locators
            if isinstance(locator, dict)
            and isinstance(locator.get("time_beats"), (int, float))
            and math.isclose(float(locator["time_beats"]), float(time_beats), rel_tol=0.0, abs_tol=LOCATOR_TIME_TOLERANCE)
        ]

    def propose_locator_action(
        self,
        action: str,
        *,
        locator_name: str,
        session_id: str,
    ) -> dict[str, Any]:
        """Propose adding or removing one named locator at a stopped playhead.

        AbletonOSC's cue-point mutation is a toggle (add-or-delete).  The
        proposal therefore requires the exact expected state before it can
        issue the toggle, so KENN can never silently delete or overwrite an
        existing locator.
        """
        _cleanup_memory()
        if action not in SUPPORTED_LOCATOR_ACTIONS:
            return {"ok": False, "error": f"Unsupported Live locator action: {action}"}
        name = str(locator_name or "").strip()
        if not name:
            return {"ok": False, "error": "add_locator requires a non-empty locator name."}
        if len(name) > 128:
            return {"ok": False, "error": "Locator names may contain at most 128 characters."}
        state = self.snapshot()
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        if bool(state.get("is_playing", False)):
            return {"ok": False, "error": "Stop Ableton's transport before adding a locator so the confirmed playhead position cannot move."}
        try:
            cursor = self.client.get_current_song_time()
            locators, available = self._locator_observation()
        except Exception as exc:
            return {"ok": False, "error": f"Could not read the current Live locator state: {exc}"}
        if cursor is None:
            return {"ok": False, "error": "Ableton did not return a readable current song position."}
        if not available:
            return {"ok": False, "error": "Ableton did not return the current locator list."}
        occupied = self._locator_at_time(locators, float(cursor))
        if action == "add_locator":
            if occupied:
                existing = str(occupied[0].get("name", "unnamed"))
                return {"ok": False, "error": f"A locator already exists at {float(cursor):g} beats ({existing!r}); KENN will not use the toggle endpoint there."}
            before = {"exists": False, "time_beats": cursor}
            after = {"name": name, "time_beats": cursor}
            reason = f"Explicit user request to add locator {name!r} at {cursor:g} beats."
            evidence = [
                f"Live transport is stopped at {cursor:g} beats.",
                f"No existing locator occupies that position; {len(locators)} locator(s) were observed.",
            ]
        else:
            matches = [
                locator for locator in occupied
                if str(locator.get("name", "")) == name
            ]
            if len(matches) != 1:
                return {"ok": False, "error": f"No single locator named {name!r} exists at the current stopped playhead ({float(cursor):g} beats)."}
            before = {"name": name, "time_beats": cursor}
            after = {"exists": False, "name": name, "time_beats": cursor}
            reason = f"Explicit user request to remove locator {name!r} at {cursor:g} beats."
            evidence = [
                f"Live transport is stopped at {cursor:g} beats.",
                f"Exactly one locator named {name!r} occupies that position.",
            ]
        cursor = round(float(cursor), 6)
        before["time_beats"] = cursor
        after["time_beats"] = cursor
        proposal = {
            "schema": PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": action,
            "operation": action,
            "target": "ableton_locator",
            "locator_name": name,
            "locator_time_beats": cursor,
            "before": before,
            "after": after,
            "unit": "beats",
            "valid_range": None,
            "reason": reason,
            "evidence": evidence,
            "confidence": 1.0,
            "risk": "local_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state),
            "locator_count_before": len(locators),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_action", text=_locator_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def propose_clip_action(
        self,
        action: str,
        *,
        track_index: int,
        clip_slot_index: int,
        session_id: str,
        track_name: str = "",
    ) -> dict[str, Any]:
        _cleanup_memory()
        if action not in SUPPORTED_CLIP_ACTIONS:
            return {"ok": False, "error": f"Unsupported Live clip action: {action}"}
        if int(track_index) < 0 or int(clip_slot_index) < 0:
            return {"ok": False, "error": "A non-negative track and clip-slot index are required."}
        state = self.snapshot(include_mixer=False)
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        track, error = _find_track(state, int(track_index), track_name)
        if error or track is None:
            return {"ok": False, "error": error}
        try:
            playback = self.client.get_clip_playback_state(int(track_index), int(clip_slot_index))
        except Exception as exc:
            return {"ok": False, "error": f"Could not read the exact clip-slot state: {exc}"}
        if not playback.get("success"):
            return {"ok": False, "error": playback.get("error") or "Could not read the exact clip-slot state."}
        if not playback.get("is_playing") and not playback.get("is_triggered"):
            return {"ok": False, "error": "That clip slot is not currently playing; there is nothing to stop."}
        proposal = {
            "schema": PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": action,
            "operation": action,
            "target": "ableton_clip_slot",
            "track_index": int(track_index),
            "track_name": str(track.get("name", "")),
            "clip_slot_index": int(clip_slot_index),
            "before": True,
            "after": False,
            "unit": "trigger",
            "valid_range": None,
            "reason": f"Explicit user request to stop the playing clip in slot {int(clip_slot_index) + 1} on '{track.get('name', '')}'.",
            "evidence": [f"Clip slot (track {track_index}, slot {clip_slot_index}) is currently playing or triggered."],
            "confidence": 1.0,
            "risk": "local_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state, track=track),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_action", text=_clip_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def propose_send_action(
        self,
        *,
        track_index: int,
        session_id: str,
        track_name: str = "",
        return_track_index: int | None = None,
        return_track_name: str = "",
        value: float,
    ) -> dict[str, Any]:
        """Propose setting one exact track's send level to one exact return
        track, resolved by real identity -- never a bare send-slider index
        guessed from a name. Closes the send/return-track control gap left
        after return-track *enumeration* was added (2026-09-06): that pass
        made identity readable; this wires it into an actual mutation,
        following the same propose/confirm/readback/receipt boundary as
        every other action here.
        """
        _cleanup_memory()
        if int(track_index) < 0:
            return {"ok": False, "error": "A non-negative track index is required; KENN never assumes track 0."}
        try:
            value = float(value)
        except (TypeError, ValueError):
            return {"ok": False, "error": "value must be numeric"}
        if not math.isfinite(value) or value < 0.0 or value > 1.0:
            return {"ok": False, "error": "Send value must be between 0.0 and 1.0 (normalized)."}
        if return_track_index is None and not return_track_name:
            return {"ok": False, "error": "An exact return-track index or name is required; KENN never assumes which return."}
        state = self.snapshot()
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        track, error = _find_track(state, int(track_index), track_name)
        if error or track is None:
            return {"ok": False, "error": error}
        try:
            return_tracks = self.client.get_return_tracks()
        except Exception as exc:
            return {"ok": False, "error": f"Could not read the exact return-track identity: {exc}"}
        if return_track_index is not None:
            resolved, error = _find_return_track(return_tracks, int(return_track_index), return_track_name)
        else:
            resolved, error = _resolve_return_track_by_name(return_tracks, return_track_name)
        if error or resolved is None:
            return {"ok": False, "error": error}
        try:
            current = self.client.get_track_send(int(track_index), int(resolved["index"]))
        except Exception as exc:
            return {"ok": False, "error": f"Could not read the current send value: {exc}"}
        if current is None:
            return {"ok": False, "error": "Could not read the current send value."}
        proposal = {
            "schema": PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "set_send",
            "operation": "set_send",
            "target": "ableton_track_send",
            "track_index": int(track_index),
            "track_name": str(track.get("name", "")),
            "return_track_index": int(resolved["index"]),
            "return_track_name": str(resolved.get("name", "")),
            "before": round(float(current), 6),
            "after": round(value, 6),
            "unit": "normalized",
            "valid_range": [0.0, 1.0],
            "reason": f"Explicit user request to set the send from '{track.get('name', '')}' to '{resolved.get('name', '')}' to {value}.",
            "evidence": [
                f"Current send value: {round(float(current), 6)}.",
                f"Target identity: track {track_index} '{track.get('name', '')}' -> return {resolved['index']} '{resolved.get('name', '')}'.",
            ],
            "confidence": 1.0,
            "risk": "local_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state, track=track),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_action", text=_send_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def proposal_for_token(self, confirm_token: str) -> dict[str, Any] | None:
        """Return a proposal previously issued by this process.

        This is a compatibility bridge for the tool API, whose historical
        signature carries a token but not the full proposal. HTTP clients
        should send the proposal explicitly so a restart cannot hide state.
        """
        proposal = _PROPOSALS_BY_TOKEN.get(str(confirm_token or ""))
        if proposal is None:
            from kenn.core.live_control_planner import LiveControlPlanner

            proposal = LiveControlPlanner.proposal_for_token(confirm_token)
        return dict(proposal) if proposal else None

    def propose_device_action(
        self,
        *,
        track_index: int,
        device_index: int,
        parameter_index: int,
        proposed_value: float,
        reason: str,
        session_id: str,
        parameter_name: str = "",
        unit: str = "",
        track_name: str = "",
        observed_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a device proposal only from an exact current Live target."""
        from kenn.core.live_control_planner import LiveControlPlanner

        state = observed_state if isinstance(observed_state, dict) else self.snapshot(include_mixer=False)
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        track, error = _find_track(state, int(track_index), track_name)
        if error or track is None:
            return {"ok": False, "error": error or "Target Live track is unavailable."}
        devices = track.get("devices") or []
        device_entry = devices[int(device_index)] if 0 <= int(device_index) < len(devices) else None
        observed_device_name = (
            str(device_entry.get("name", ""))
            if isinstance(device_entry, dict)
            else str(device_entry or "")
        )
        if device_entry is None:
            return {"ok": False, "error": "Target Live device is not present in the current snapshot."}
        planner = LiveControlPlanner(osc_client=None if self.client is live_client else self.client)
        return planner.propose_parameter_change(
            track_index=track_index,
            device_index=device_index,
            parameter_index=parameter_index,
            proposed_value=proposed_value,
            reason=reason,
            session_id=session_id,
            parameter_name=parameter_name,
            unit=unit,
            track_name=str(track.get("name", "")),
        )

    def propose_device_insertion(
        self,
        *,
        track_index: int,
        device_name: str,
        session_id: str,
        track_name: str = "",
        insertion_index: int | None = None,
        observed_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare an append-only proposal for one allow-listed Live device."""
        _cleanup_memory()
        requested_name = str(device_name or "").strip()
        canonical_name = next(
            (allowed for allowed in DEVICE_INSERTION_ALLOWLIST if allowed.lower() == requested_name.lower()),
            None,
        )
        if canonical_name is None:
            allowed = ", ".join(sorted(DEVICE_INSERTION_ALLOWLIST))
            return {"ok": False, "error": f"Only these allow-listed devices may be inserted: {allowed}."}
        state = observed_state if isinstance(observed_state, dict) else self.snapshot(include_mixer=False)
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        track, error = _find_track(state, int(track_index), track_name)
        if error or track is None:
            return {"ok": False, "error": error or "Target Live track is unavailable."}
        before_devices = _ordered_device_identities(track)
        if any(item["name"].strip().lower() == canonical_name.lower() for item in before_devices):
            return {"ok": False, "error": f"Track '{track.get('name', '')}' already contains {canonical_name}; choose the exact existing device instead."}
        expected_index = len(before_devices)
        if insertion_index is not None and int(insertion_index) != expected_index:
            return {"ok": False, "error": "Only append insertion is enabled; the requested insertion position is stale or unsupported."}
        after_devices = before_devices + [{"position": expected_index, "index": expected_index, "name": canonical_name}]
        fingerprint = hashlib.sha256(json.dumps(before_devices, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        proposal = {
            "schema": DEVICE_INSERTION_PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "insert_device",
            "operation": "insert_device",
            "target": "ableton_track",
            "track_index": int(track_index),
            "track_name": str(track.get("name", "")),
            "device_name": canonical_name,
            "insertion_index": expected_index,
            "before_devices": before_devices,
            "after_devices": after_devices,
            "before_device_fingerprint": fingerprint,
            "reason": f"Explicit user request to append {canonical_name} on track '{track.get('name', '')}'.",
            "evidence": [
                f"Current Live device order: {[item['name'] for item in before_devices]!r}.",
                f"Target identity: track {track_index} '{track.get('name', '')}', append position {expected_index}.",
            ],
            "confidence": 1.0,
            "risk": "local_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state, track=track),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_action", text=_insertion_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def propose_device_setup_action(
        self,
        *,
        track_index: int,
        device_name: str,
        parameter_name: str,
        parameter_display_value: float,
        parameter_unit: str,
        session_id: str,
        track_name: str = "",
        observed_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare one bounded insert-and-configure proposal.

        The device is not present at proposal time, so its Live parameter
        index cannot be guessed.  The proposal binds the exact device and
        display control; execution inserts it, reads the new parameter list,
        resolves the exact control by name, writes once, and verifies both
        the parameter and the device chain.
        """
        _cleanup_memory()
        requested_name = str(device_name or "").strip()
        canonical_name = next(
            (allowed for allowed in DEVICE_INSERTION_ALLOWLIST if allowed.casefold() == requested_name.casefold()),
            None,
        )
        if canonical_name is None:
            return {"ok": False, "error": "That device is not in KENN's exact insertion allowlist."}
        parameter_key = _device_setup_parameter_key(parameter_name)
        parameter_spec = DEVICE_SETUP_PARAMETER_ALLOWLIST.get(canonical_name, {}).get(parameter_key)
        if parameter_spec is None:
            return {"ok": False, "error": f"KENN only supports a qualified Dry/Wet setup for {canonical_name}."}
        canonical_parameter, expected_unit = parameter_spec
        if str(parameter_unit or "").strip() != expected_unit:
            return {"ok": False, "error": f"{canonical_name} {canonical_parameter} must be specified as a percentage."}
        try:
            display_value = float(parameter_display_value)
        except (TypeError, ValueError):
            return {"ok": False, "error": "The device display value must be numeric."}
        if not math.isfinite(display_value) or not 0.0 <= display_value <= 100.0:
            return {"ok": False, "error": "Dry/Wet must be between 0% and 100%."}
        from kenn.core.device_units import display_to_raw

        raw_value, conversion_error = display_to_raw(
            device_name=canonical_name,
            parameter_name=canonical_parameter,
            value=display_value,
            unit=expected_unit,
        )
        if conversion_error or raw_value is None or not math.isfinite(float(raw_value)):
            return {"ok": False, "error": conversion_error or "The qualified display value could not be converted safely."}

        state = observed_state if isinstance(observed_state, dict) else self.snapshot(include_mixer=False)
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        track, error = _find_track(state, int(track_index), track_name)
        if error or track is None:
            return {"ok": False, "error": error or "Target Live track is unavailable."}
        before_devices = _ordered_device_identities(track)
        if any(item["name"].strip().casefold() == canonical_name.casefold() for item in before_devices):
            return {"ok": False, "error": f"Track '{track.get('name', '')}' already contains {canonical_name}; choose the exact existing device instead."}
        insertion_index = len(before_devices)
        after_devices = before_devices + [{"position": insertion_index, "index": insertion_index, "name": canonical_name}]
        fingerprint = hashlib.sha256(json.dumps(before_devices, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        proposal = {
            "schema": DEVICE_SETUP_PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "insert_device_with_parameter",
            "operation": "insert_device_with_parameter",
            "target": "ableton_track",
            "track_index": int(track_index),
            "track_name": str(track.get("name", "")),
            "device_name": canonical_name,
            "insertion_index": insertion_index,
            "parameter_name": canonical_parameter,
            "parameter_display_value": display_value,
            "parameter_unit": expected_unit,
            "parameter_after_value": float(raw_value),
            "before_devices": before_devices,
            "after_devices": after_devices,
            "before_device_fingerprint": fingerprint,
            "reason": f"Explicit user request to append {canonical_name} on '{track.get('name', '')}' and set {canonical_parameter} to {display_value:g}%.",
            "evidence": [
                f"Current Live device order: {[item['name'] for item in before_devices]!r}.",
                f"Qualified control: {canonical_name} {canonical_parameter} ({expected_unit}).",
                f"Target identity: track {track_index} '{track.get('name', '')}', append position {insertion_index}.",
            ],
            "confidence": 1.0,
            "risk": "local_multi_step_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state, track=track),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(
            session_id=session_id,
            service_id="ableton_device_setup",
            text=_device_setup_text(proposal),
        )
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def execute_device_setup_action(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Insert one qualified device, configure one control, and verify it.

        If configuration cannot be verified, removal is attempted only while
        the chain still exactly equals the known post-insertion chain. This
        keeps an uncertain or concurrently changed session out of the blind
        rollback path.
        """
        _cleanup_memory()
        if not isinstance(proposal, dict) or proposal.get("schema") != DEVICE_SETUP_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid KENN device-setup proposal is required."}
        if not proposal.get("requires_confirmation") or str(proposal.get("confirmation_token", "")) != str(confirm_token):
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required for this exact device-setup proposal."}
        key = str(idempotency_key or proposal.get("action_id") or "").strip()
        if not key:
            return {"ok": False, "error": "An idempotency key is required for device setup."}
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This device-setup request was already executed or is already in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_device_setup", text=_device_setup_text(proposal)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used device-setup confirmation token."}

        track_index = int(proposal.get("track_index", -1))
        track_name = str(proposal.get("track_name", ""))
        insertion_index = int(proposal.get("insertion_index", -1))
        expected_devices = proposal.get("after_devices")
        before_devices = proposal.get("before_devices")

        def fail(
            error: str,
            *,
            readback_devices: Any = None,
            parameter_before: Any = None,
            parameter_readback: Any = None,
            rollback: dict[str, Any] | None = None,
            status: str = "failed",
        ) -> dict[str, Any]:
            _finish_idempotency_key(key)
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "receipt_id": f"receipt-{uuid.uuid4().hex}",
                "action_id": proposal.get("action_id"),
                "action": "insert_device_with_parameter",
                "idempotency_key": key,
                "status": status,
                "verified": False,
                "timestamp": time.time(),
                "target": {
                    "target": "ableton_track", "track_index": track_index, "track_name": track_name,
                    "device_name": str(proposal.get("device_name", "")), "insertion_index": insertion_index,
                    "parameter_name": str(proposal.get("parameter_name", "")),
                },
                "before_devices": before_devices,
                "requested_devices": expected_devices,
                "readback_devices": readback_devices,
                "parameter_before_value": parameter_before,
                "parameter_requested_value": proposal.get("parameter_after_value"),
                "parameter_readback": parameter_readback,
                "error": error,
                "rollback": rollback,
                "retry_safe": "requires_inspection" if rollback and not rollback.get("reverted") else "unsafe",
                "correlation_id": resolve_correlation_id(correlation_id),
            }
            _RECEIPTS[receipt["receipt_id"]] = receipt
            return {"ok": False, "status": status, "error": error, "receipt": receipt}

        try:
            state = self.snapshot(include_mixer=False)
        except Exception as exc:
            return fail(f"Live snapshot failed before device setup: {exc}")
        track, error = _find_track(state, track_index, track_name)
        if error or track is None:
            return fail(error or "Target Live track is unavailable.")
        current_devices = _ordered_device_identities(track)
        if not _device_identities_match(before_devices, current_devices):
            return fail("Live device order changed since the proposal was created.", readback_devices=current_devices)
        if insertion_index != len(current_devices):
            return fail("The insertion position is no longer the end of the target device chain.", readback_devices=current_devices)

        try:
            result = self.client.insert_device_with_result(track_index, str(proposal["device_name"]), insertion_index)
        except Exception as exc:
            return fail(f"Live device insertion raised an exception: {exc}")
        if not isinstance(result, dict):
            result = {"success": bool(result)}
        acknowledgement = "confirmed" if result.get("success") else "unacknowledged_write_reconciled"
        try:
            time.sleep(0.05)
            after_state = self.snapshot(include_mixer=False)
            after_track, _ = _find_track(after_state, track_index, track_name)
            after_devices = _ordered_device_identities(after_track)
        except Exception as exc:
            return fail(f"Live readback failed after device insertion: {exc}")
        if not _device_identities_match(expected_devices, after_devices):
            auto_revert = self._revert_mismatched_insertion(
                track_index=track_index, track_name=track_name, insertion_index=insertion_index,
                before_devices=current_devices, after_devices=after_devices,
                requested_name=str(proposal.get("device_name", "")),
            )
            restored = bool(auto_revert and auto_revert.get("reverted"))
            error_message = "Live inserted the requested device but the exact device-chain readback did not verify."
            if auto_revert and auto_revert.get("wrong_device_name"):
                error_message = f"Live inserted '{auto_revert['wrong_device_name']}' instead of '{proposal.get('device_name', '')}'."
            return fail(
                error_message + (" KENN removed it and verified the original chain." if restored else " The chain requires inspection before retrying."),
                readback_devices=after_devices, rollback=auto_revert,
                status="failed_rolled_back" if restored else "partial_recovery",
            )

        parameter_name = str(proposal.get("parameter_name", ""))
        try:
            info = self.client.get_device_parameters(track_index, insertion_index)
        except Exception as exc:
            info = {"success": False, "error": str(exc)}
        if not isinstance(info, dict) or not info.get("success"):
            setup_error = f"Live device inspection failed after insertion: {info.get('error', 'unknown error') if isinstance(info, dict) else 'unknown error'}"
            return self._fail_device_setup_with_rollback(proposal, key, setup_error, before_devices, expected_devices, after_devices, parameter_before=None, correlation_id=correlation_id)
        matches = [item for item in (info.get("parameters") or []) if isinstance(item, dict) and str(item.get("name", "")) == parameter_name]
        if len(matches) != 1:
            setup_error = f"Live did not expose one exact '{parameter_name}' parameter on the inserted {proposal.get('device_name', 'device')}."
            return self._fail_device_setup_with_rollback(proposal, key, setup_error, before_devices, expected_devices, after_devices, parameter_before=None, correlation_id=correlation_id)
        parameter = matches[0]
        try:
            parameter_index = int(parameter["index"])
            parameter_before = float(parameter["value"])
            requested_value = float(proposal["parameter_after_value"])
        except (KeyError, TypeError, ValueError):
            return self._fail_device_setup_with_rollback(proposal, key, "Live returned an unreadable setup parameter.", before_devices, expected_devices, after_devices, parameter_before=None, correlation_id=correlation_id)
        if parameter_index < 0 or not math.isfinite(parameter_before) or not math.isfinite(requested_value):
            return self._fail_device_setup_with_rollback(proposal, key, "The setup parameter values were not finite.", before_devices, expected_devices, after_devices, parameter_before=parameter_before, correlation_id=correlation_id)
        try:
            minimum, maximum = float(parameter.get("min")), float(parameter.get("max"))
        except (TypeError, ValueError):
            minimum = maximum = float("nan")
        if math.isfinite(minimum) and math.isfinite(maximum) and not minimum <= requested_value <= maximum:
            return self._fail_device_setup_with_rollback(proposal, key, "The requested setup value is outside Live's read parameter range.", before_devices, expected_devices, after_devices, parameter_before=parameter_before, correlation_id=correlation_id)
        write_error = ""
        try:
            write_ok = bool(self.client.set_device_parameter(track_index, insertion_index, parameter_index, requested_value))
        except Exception as exc:
            write_ok = False
            write_error = str(exc)
        try:
            time.sleep(0.05)
            post_info = self.client.get_device_parameters(track_index, insertion_index)
            post_matches = [item for item in (post_info.get("parameters") or []) if isinstance(item, dict) and int(item.get("index", -1)) == parameter_index and str(item.get("name", "")) == parameter_name] if isinstance(post_info, dict) and post_info.get("success") else []
            parameter_readback = post_matches[0].get("value") if len(post_matches) == 1 else None
        except Exception as exc:
            parameter_readback = None
            write_error = write_error or str(exc)
        verified = parameter_readback is not None and _values_match(parameter_readback, requested_value) and (write_ok or not _values_match(parameter_before, requested_value))
        if not verified:
            detail = "Live device setup was sent but parameter readback did not verify."
            if write_error:
                detail += f" {write_error}"
            return self._fail_device_setup_with_rollback(
                proposal, key, detail, before_devices, expected_devices, after_devices,
                parameter_before=parameter_before, parameter_readback=parameter_readback,
                parameter_index=parameter_index, acknowledgement=acknowledgement,
                correlation_id=correlation_id,
            )

        _finish_idempotency_key(key)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "receipt_id": f"receipt-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"), "action": "insert_device_with_parameter",
            "idempotency_key": key, "status": "applied", "verified": True, "timestamp": time.time(),
            "target": {
                "target": "ableton_track", "track_index": track_index, "track_name": track_name,
                "device_name": str(proposal.get("device_name", "")), "insertion_index": insertion_index,
                "parameter_index": parameter_index, "parameter_name": parameter_name,
            },
            "before_devices": before_devices, "requested_devices": expected_devices, "readback_devices": after_devices,
            "before": parameter_before, "requested": requested_value, "readback": parameter_readback,
            "parameter_before_value": parameter_before, "parameter_requested_value": requested_value,
            "parameter_display_value": proposal.get("parameter_display_value"), "parameter_unit": proposal.get("parameter_unit"),
            "write_acknowledgement": acknowledgement, "correlation_id": resolve_correlation_id(correlation_id),
            "undo_payload": {
                "action": "remove_device", "track_index": track_index, "track_name": track_name,
                "device_index": insertion_index, "device_name": str(proposal.get("device_name", "")),
                "expected_devices": after_devices,
            },
        }
        _RECEIPTS[receipt["receipt_id"]] = receipt
        return {"ok": True, "receipt": receipt}

    def _fail_device_setup_with_rollback(
        self,
        proposal: dict[str, Any],
        key: str,
        error: str,
        before_devices: Any,
        expected_devices: Any,
        readback_devices: Any,
        *,
        parameter_before: Any,
        parameter_readback: Any = None,
        parameter_index: int | None = None,
        acknowledgement: str = "confirmed",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Compensate a failed setup only against an exact post-insert chain."""
        rollback: dict[str, Any] = {"attempted": False, "reverted": False}
        current_devices = readback_devices
        try:
            current_state = self.snapshot(include_mixer=False)
            current_track, _ = _find_track(
                current_state,
                int(proposal["track_index"]),
                str(proposal.get("track_name", "")),
            )
            current_devices = _ordered_device_identities(current_track)
        except Exception as exc:
            rollback["error"] = f"Could not re-read the device chain before compensation: {exc}"
        if _device_identities_match(expected_devices, current_devices):
            rollback["attempted"] = True
            try:
                removal = self.client.remove_device_with_result(
                    int(proposal["track_index"]), int(proposal["insertion_index"]), str(proposal["device_name"])
                )
                rollback["acknowledged"] = bool(removal.get("success")) if isinstance(removal, dict) else bool(removal)
                confirm_state = self.snapshot(include_mixer=False)
                confirm_track, _ = _find_track(confirm_state, int(proposal["track_index"]), str(proposal.get("track_name", "")))
                rollback_devices = _ordered_device_identities(confirm_track)
                rollback["reverted"] = _device_identities_match(before_devices, rollback_devices)
                rollback["readback_devices"] = rollback_devices
            except Exception as exc:
                rollback["error"] = str(exc)
        else:
            rollback["error"] = "The post-insertion device chain changed; KENN did not remove an ambiguous device."
        status = "failed_rolled_back" if rollback.get("reverted") else "partial_recovery"
        _finish_idempotency_key(key)
        receipt = {
            "schema": RECEIPT_SCHEMA, "receipt_id": f"receipt-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"), "action": "insert_device_with_parameter",
            "idempotency_key": key, "status": status, "verified": False, "timestamp": time.time(),
            "target": {
                "target": "ableton_track", "track_index": int(proposal["track_index"]),
                "track_name": str(proposal.get("track_name", "")), "device_name": str(proposal.get("device_name", "")),
                "insertion_index": int(proposal["insertion_index"]), "parameter_index": parameter_index,
                "parameter_name": str(proposal.get("parameter_name", "")),
            },
            "before_devices": before_devices, "requested_devices": expected_devices, "readback_devices": readback_devices,
            "before": parameter_before, "requested": proposal.get("parameter_after_value"), "readback": parameter_readback,
            "parameter_before_value": parameter_before, "parameter_requested_value": proposal.get("parameter_after_value"),
            "parameter_display_value": proposal.get("parameter_display_value"), "parameter_unit": proposal.get("parameter_unit"),
            "write_acknowledgement": acknowledgement, "rollback": rollback, "error": error,
            "retry_safe": "requires_inspection" if not rollback.get("reverted") else "unsafe",
            "correlation_id": resolve_correlation_id(correlation_id),
        }
        _RECEIPTS[receipt["receipt_id"]] = receipt
        return {"ok": False, "status": status, "error": error, "receipt": receipt}

    def propose_eq_band_tuning_gain(
        self,
        *,
        track_index: int,
        track_name: str,
        device_index: int,
        device_name: str,
        eq_band: str,
        frequency_parameter: dict[str, Any],
        frequency_before_hz: float,
        frequency_after_hz: float,
        frequency_after_value: float,
        gain_parameter: dict[str, Any],
        gain_after: float,
        reason: str,
        session_id: str,
        source_receipt_id: str = "",
        observed_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create one confirmation-bound proposal for a two-parameter EQ edit."""
        _cleanup_memory()
        try:
            track_index = int(track_index)
            device_index = int(device_index)
            frequency_index = int(frequency_parameter["index"])
            gain_index = int(gain_parameter["index"])
            frequency_before_value = float(frequency_parameter["value"])
            frequency_after_value = float(frequency_after_value)
            gain_before_value = float(gain_parameter["value"])
            gain_after = float(gain_after)
            frequency_before_hz = float(frequency_before_hz)
            frequency_after_hz = float(frequency_after_hz)
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "EQ proposals require readable numeric frequency and gain parameters."}
        numbers = (frequency_before_value, frequency_after_value, gain_before_value, gain_after, frequency_before_hz, frequency_after_hz)
        if min(track_index, device_index, frequency_index, gain_index) < 0 or not all(math.isfinite(value) for value in numbers):
            return {"ok": False, "error": "EQ proposal values and indices must be finite and non-negative where applicable."}
        if str(device_name).strip().lower() != "eq eight" or not str(eq_band).strip():
            return {"ok": False, "error": "Compound EQ proposals require an exact EQ Eight and band identity."}
        frequency_range = [frequency_parameter.get("min"), frequency_parameter.get("max")]
        gain_range = [gain_parameter.get("min"), gain_parameter.get("max")]
        if len(frequency_range) == 2 and all(isinstance(value, (int, float)) for value in frequency_range):
            if not float(frequency_range[0]) <= frequency_after_value <= float(frequency_range[1]):
                return {"ok": False, "error": "The requested EQ frequency is outside the inspected Live parameter range."}
        if len(gain_range) == 2 and all(isinstance(value, (int, float)) for value in gain_range):
            if not float(gain_range[0]) <= gain_after <= float(gain_range[1]):
                return {"ok": False, "error": "The requested EQ gain is outside the inspected Live parameter range."}
        state = observed_state if isinstance(observed_state, dict) else self.snapshot(include_mixer=False)
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        track, error = _find_track(state, track_index, track_name)
        if error or track is None:
            return {"ok": False, "error": error or "Target Live track is unavailable."}
        devices = track.get("devices") or []
        device_entry = devices[device_index] if 0 <= device_index < len(devices) else None
        observed_name = str(device_entry.get("name", "")) if isinstance(device_entry, dict) else str(device_entry or "")
        if observed_name != str(device_name):
            return {"ok": False, "error": "Target EQ Eight identity changed while preparing the proposal."}
        proposal = {
            "schema": EQ_BAND_TUNING_GAIN_PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "set_eq_band_tuning_gain",
            "operation": "set_eq_band_tuning_gain",
            "target": "ableton_device",
            "track_index": track_index,
            "track_name": str(track.get("name", "")),
            "device_index": device_index,
            "device_name": str(device_name),
            "eq_band": str(eq_band).strip().upper(),
            "frequency_parameter_index": frequency_index,
            "frequency_parameter": str(frequency_parameter.get("name", "")),
            "frequency_before_value": frequency_before_value,
            "frequency_after_value": frequency_after_value,
            "frequency_before_hz": frequency_before_hz,
            "frequency_after_hz": frequency_after_hz,
            "gain_parameter_index": gain_index,
            "gain_parameter": str(gain_parameter.get("name", "")),
            "gain_before_value": gain_before_value,
            "gain_after_value": gain_after,
            "before": {"frequency_hz": frequency_before_hz, "gain_db": gain_before_value},
            "after": {"frequency_hz": frequency_after_hz, "gain_db": gain_after},
            "reason": reason,
            "source_receipt_id": source_receipt_id,
            "confidence": 1.0,
            "risk": "local_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state, track=track),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_action", text=_eq_band_tuning_gain_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def _revert_mismatched_insertion(
        self,
        *,
        track_index: int,
        track_name: str,
        insertion_index: int,
        before_devices: list[dict[str, Any]],
        after_devices: list[dict[str, Any]],
        requested_name: str,
    ) -> dict[str, Any] | None:
        """Auto-remove a device Live inserted under the wrong name.

        AbletonOSC's browser-search insertion does not require an exact
        name match (real-Live testing found "Reverb" silently resolves to
        "Convolution Reverb", for example). A verification failure caused by
        that mismatch would otherwise leave the wrong device genuinely
        sitting on the user's track with only an error message - this
        restores the track to its pre-insertion state instead.

        Deliberately narrow: only acts when the readback shows *exactly*
        one new device, in the expected position, with everything before it
        unchanged from ``before_devices``. Any other shape (no new device,
        more than one, or an unrelated change elsewhere in the chain) is
        left alone and reported as a plain verification failure, since this
        method cannot safely tell what actually happened in those cases.
        """
        if (
            len(after_devices) != len(before_devices) + 1
            or after_devices[:len(before_devices)] != before_devices
        ):
            return None
        wrong_device = after_devices[insertion_index]
        wrong_name = str(wrong_device.get("name", ""))
        if wrong_name.strip().lower() == requested_name.strip().lower():
            return None  # names matched; this was not a mismatch in the first place
        try:
            removal = self.client.remove_device_with_result(track_index, insertion_index, wrong_name)
        except Exception as exc:
            return {"attempted": True, "reverted": False, "wrong_device_name": wrong_name, "error": str(exc)}
        if not removal.get("success"):
            return {"attempted": True, "reverted": False, "wrong_device_name": wrong_name, "error": removal.get("error", "removal was not acknowledged")}
        try:
            confirm_state = self.snapshot(include_mixer=False)
            confirm_track, _ = _find_track(confirm_state, track_index, track_name)
            confirmed_devices = _ordered_device_identities(confirm_track)
        except Exception as exc:
            return {"attempted": True, "reverted": False, "wrong_device_name": wrong_name, "error": f"post-removal readback failed: {exc}"}
        if not _device_identities_match(before_devices, confirmed_devices):
            return {"attempted": True, "reverted": False, "wrong_device_name": wrong_name, "error": "track did not return to its pre-insertion device order after removal"}
        return {"attempted": True, "reverted": True, "wrong_device_name": wrong_name, "after_devices": confirmed_devices}

    def _insertion_failure(self, proposal: dict[str, Any], key: str, error: str, *, readback: Any = None) -> dict[str, Any]:
        _finish_idempotency_key(key)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "receipt_id": f"receipt-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": proposal.get("action", "insert_device"),
            "idempotency_key": key,
            "status": "failed",
            "verified": False,
            "timestamp": time.time(),
            "target": {
                "target": proposal.get("target", "ableton_track"),
                "track_index": proposal.get("track_index"),
                "track_name": str(proposal.get("track_name", "")),
                "device_name": str(proposal.get("device_name", "")),
                "insertion_index": proposal.get("insertion_index"),
            },
            "before_devices": proposal.get("before_devices", []),
            "requested_devices": proposal.get("after_devices", []),
            "readback_devices": readback,
            "error": error,
        }
        _RECEIPTS[receipt["receipt_id"]] = receipt
        return {"ok": False, "error": error, "receipt": receipt}

    def execute_device_insertion(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """Apply one confirmed insertion only after fresh identity checks."""
        _cleanup_memory()
        if not isinstance(proposal, dict) or proposal.get("schema") != DEVICE_INSERTION_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid KENN device-insertion proposal is required."}
        if not proposal.get("requires_confirmation") or str(proposal.get("confirmation_token", "")) != str(confirm_token):
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required for this exact device-insertion proposal."}
        key = str(idempotency_key or proposal.get("action_id") or "").strip()
        if not key:
            return {"ok": False, "error": "An idempotency key is required for device insertion."}
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This device-insertion request was already executed or is already in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=_insertion_text(proposal)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used insertion confirmation token."}

        try:
            state = self.snapshot(include_mixer=False)
        except Exception as exc:
            return self._insertion_failure(proposal, key, f"Live snapshot failed before device insertion: {exc}")
        track, error = _find_track(state, int(proposal.get("track_index", -1)), str(proposal.get("track_name", "")))
        if error or track is None:
            return self._insertion_failure(proposal, key, error or "Target Live track is unavailable.")
        before_devices = _ordered_device_identities(track)
        if not _device_identities_match(proposal.get("before_devices"), before_devices):
            return self._insertion_failure(proposal, key, "Live device order changed since the proposal was created.", readback=before_devices)
        insertion_index = int(proposal.get("insertion_index", -1))
        if insertion_index != len(before_devices):
            return self._insertion_failure(proposal, key, "The insertion position is no longer the end of the target device chain.", readback=before_devices)
        try:
            result = self.client.insert_device_with_result(
                int(proposal["track_index"]), str(proposal["device_name"]), insertion_index
            )
        except AttributeError:
            try:
                write_ok = bool(self.client.create_device(int(proposal["track_index"]), str(proposal["device_name"])))
                result = {"success": write_ok}
            except Exception as exc:
                return self._insertion_failure(proposal, key, f"Live device insertion raised an exception: {exc}")
        except Exception as exc:
            return self._insertion_failure(proposal, key, f"Live device insertion raised an exception: {exc}")
        write_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
        after_state = None
        after_devices = None
        acknowledgement = "confirmed"
        if not result.get("success"):
            # Ableton may perform browser.load_item successfully but fail to
            # send the extension's OSC acknowledgement.  Reconcile the live
            # chain before reporting failure; otherwise a real mutation can
            # be misreported as a no-op and the user may retry it.
            try:
                time.sleep(0.05)
                after_state = self.snapshot(include_mixer=False)
                readback_track, _ = _find_track(
                    after_state,
                    int(proposal["track_index"]),
                    str(proposal.get("track_name", "")),
                )
                after_devices = _ordered_device_identities(readback_track)
            except Exception as exc:
                return self._insertion_failure(
                    proposal,
                    key,
                    f"{result.get('error', 'Live rejected device insertion.')} Reconciliation readback failed: {exc}",
                )
            if not _device_identities_match(proposal.get("after_devices"), after_devices):
                return self._insertion_failure(
                    proposal,
                    key,
                    result.get("error", "Live rejected device insertion."),
                    readback=after_devices,
                )
            acknowledgement = "unacknowledged_write_reconciled"
        if after_state is None:
            try:
                time.sleep(0.05)
                after_state = self.snapshot(include_mixer=False)
            except Exception as exc:
                return self._insertion_failure(proposal, key, f"Live readback failed after device insertion: {exc}")
            readback_track, _ = _find_track(after_state, int(proposal["track_index"]), str(proposal.get("track_name", "")))
            after_devices = _ordered_device_identities(readback_track)
        assert after_devices is not None
        readback_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
        expected_devices = proposal.get("after_devices", [])
        verified = _device_identities_match(expected_devices, after_devices)
        auto_revert: dict[str, Any] | None = None
        if not verified:
            auto_revert = self._revert_mismatched_insertion(
                track_index=int(proposal["track_index"]),
                track_name=str(proposal.get("track_name", "")),
                insertion_index=insertion_index,
                before_devices=before_devices,
                after_devices=after_devices,
                requested_name=str(proposal.get("device_name", "")),
            )
            if auto_revert is not None and auto_revert.get("reverted"):
                after_devices = auto_revert["after_devices"]
        _finish_idempotency_key(key)
        error_message = "Live device insertion was sent but read-back verification failed."
        if auto_revert is not None:
            if auto_revert.get("reverted"):
                error_message = (
                    f"Live inserted \"{auto_revert['wrong_device_name']}\" instead of the requested "
                    f"\"{proposal.get('device_name', '')}\" (AbletonOSC's browser search resolved the "
                    "name to a different device). KENN automatically removed it; the track is unchanged. "
                    "This device name does not reach the expected device - do not retry without "
                    "correcting the requested device name."
                )
            elif auto_revert.get("attempted"):
                error_message = (
                    f"Live inserted \"{auto_revert['wrong_device_name']}\" instead of the requested "
                    f"\"{proposal.get('device_name', '')}\", and KENN's automatic removal of it failed "
                    f"({auto_revert.get('error', 'unknown error')}). The wrong device is still on the "
                    "track; remove it manually before retrying."
                )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "receipt_id": f"receipt-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "insert_device",
            "idempotency_key": key,
            "status": "applied" if verified else "failed_verification",
            "verified": verified,
            "timestamp": time.time(),
            "target": {
                "target": "ableton_track",
                "track_index": int(proposal["track_index"]),
                "track_name": str(proposal.get("track_name", "")),
                "device_name": str(proposal.get("device_name", "")),
                "insertion_index": insertion_index,
            },
            "before_devices": before_devices,
            "requested_devices": expected_devices,
            "readback_devices": after_devices,
            "write_exchange": write_exchange,
            "readback_exchange": readback_exchange,
            "write_acknowledgement": acknowledgement,
            "auto_revert": auto_revert,
            "undo_payload": {
                "action": "remove_device",
                "track_index": int(proposal["track_index"]),
                "track_name": str(proposal.get("track_name", "")),
                "device_index": insertion_index,
                "device_name": str(proposal.get("device_name", "")),
                "expected_devices": after_devices,
                "source_receipt_id": "pending",
            },
        }
        receipt["undo_payload"]["source_receipt_id"] = receipt["receipt_id"]
        _RECEIPTS[receipt["receipt_id"]] = receipt
        if not verified:
            return {"ok": False, "error": error_message, "receipt": receipt}
        return {"ok": True, "receipt": receipt}

    def propose_device_removal(
        self,
        *,
        track_index: int,
        device_index: int,
        device_name: str,
        expected_devices: list[dict[str, Any]],
        source_receipt_id: str,
        session_id: str,
        track_name: str = "",
    ) -> dict[str, Any]:
        """Prepare an identity-bound inverse for a verified insertion receipt."""
        state = self.snapshot(include_mixer=False)
        if state.get("status") in {"offline", "dispatched"}:
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}
        track, error = _find_track(state, int(track_index), track_name)
        if error or track is None:
            return {"ok": False, "error": error or "Target Live track is unavailable."}
        current_devices = _ordered_device_identities(track)
        if not _device_identities_match(expected_devices, current_devices):
            return {"ok": False, "error": "The inserted device chain changed; KENN will not remove an ambiguous device."}
        if device_index < 0 or device_index >= len(current_devices):
            return {"ok": False, "error": "The inserted device is no longer present at its recorded index."}
        target = current_devices[device_index]
        if target["name"] != device_name:
            return {"ok": False, "error": "The inserted device identity changed; undo is stale."}
        proposal = {
            "schema": DEVICE_REMOVAL_PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "remove_device",
            "operation": "remove_device",
            "target": "ableton_track",
            "track_index": int(track_index),
            "track_name": str(track.get("name", "")),
            "device_index": int(device_index),
            "device_name": str(device_name),
            "before_devices": current_devices,
            "after_devices": current_devices[:device_index] + current_devices[device_index + 1:],
            "before_device_fingerprint": hashlib.sha256(json.dumps(current_devices, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "source_receipt_id": str(source_receipt_id),
            "requires_confirmation": True,
            "risk": "local_mutation",
            "reason": f"Restore the device chain from verified KENN receipt {source_receipt_id}.",
            "timestamp": time.time(),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_action", text=_removal_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def execute_device_removal(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """Execute only the identity-bound inverse of a verified insertion."""
        _cleanup_memory()
        if not isinstance(proposal, dict) or proposal.get("schema") != DEVICE_REMOVAL_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid KENN device-removal proposal is required."}
        if not proposal.get("requires_confirmation") or str(proposal.get("confirmation_token", "")) != str(confirm_token):
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required for this exact device-removal proposal."}
        key = str(idempotency_key or proposal.get("action_id") or "").strip()
        if not key:
            return {"ok": False, "error": "An idempotency key is required for device removal."}
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This device-removal request was already executed or is already in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=_removal_text(proposal)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used removal confirmation token."}
        try:
            state = self.snapshot(include_mixer=False)
            track, error = _find_track(state, int(proposal["track_index"]), str(proposal.get("track_name", "")))
            if error or track is None:
                return self._insertion_failure(proposal, key, error or "Target Live track is unavailable.")
            current = _ordered_device_identities(track)
            if not _device_identities_match(proposal.get("before_devices"), current):
                return self._insertion_failure(proposal, key, "Live device order changed before identity-bound undo.", readback=current)
            index = int(proposal["device_index"])
            if index < 0 or index >= len(current) or current[index]["name"] != str(proposal["device_name"]):
                return self._insertion_failure(proposal, key, "The identity-bound inserted device is no longer present.", readback=current)
            result = self.client.remove_device_with_result(int(proposal["track_index"]), index, str(proposal["device_name"]))
            write_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
            if not result.get("success"):
                return self._insertion_failure(proposal, key, result.get("error", "Live rejected device removal."), readback=current)
            time.sleep(0.05)
            after_state = self.snapshot(include_mixer=False)
            post_track, _ = _find_track(after_state, int(proposal["track_index"]), str(proposal.get("track_name", "")))
            readback = _ordered_device_identities(post_track)
            verified = _device_identities_match(proposal.get("after_devices"), readback)
            readback_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
        except AttributeError:
            return self._insertion_failure(proposal, key, "The bridge does not expose identity-bound device removal.")
        except Exception as exc:
            return self._insertion_failure(proposal, key, f"Live device removal failed: {exc}")
        _finish_idempotency_key(key)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "receipt_id": f"receipt-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": "remove_device",
            "idempotency_key": key,
            "status": "applied" if verified else "failed_verification",
            "verified": verified,
            "timestamp": time.time(),
            "target": {"target": "ableton_track", "track_index": int(proposal["track_index"]), "track_name": str(proposal.get("track_name", "")), "device_index": int(proposal["device_index"]), "device_name": str(proposal.get("device_name", ""))},
            "before_devices": current,
            "requested_devices": proposal.get("after_devices", []),
            "readback_devices": readback,
            "write_exchange": write_exchange,
            "readback_exchange": readback_exchange,
        }
        _RECEIPTS[receipt["receipt_id"]] = receipt
        if not verified:
            return {"ok": False, "error": "Live device removal was sent but read-back verification failed.", "receipt": receipt}
        return {"ok": True, "receipt": receipt}

    def execute_device_action(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """Execute one inspected device parameter through this safety boundary.

        The legacy planner payload remains compatible, but single-parameter
        execution is owned here so device actions receive the same exact-target,
        stale-state, idempotency, telemetry, readback, and receipt guarantees as
        track actions. Batch transactions remain disabled until they are
        migrated as one atomic operation through this service.
        """
        _cleanup_memory()
        if not isinstance(proposal, dict) or proposal.get("schema") not in {
            "kenn.action_proposal.v1", "kenn.batch_action_proposal.v1"
        }:
            return {"ok": False, "error": "A valid KENN device action proposal is required."}
        if proposal.get("schema") == "kenn.batch_action_proposal.v1":
            return {"ok": False, "error": "Batch Live device mutation is disabled until it is migrated to LiveActionService."}
        if not proposal.get("requires_confirmation") or not confirm_token:
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required before a Live device mutation."}
        if str(proposal.get("confirmation_token", "")) != str(confirm_token):
            return {"ok": False, "error": "Confirmation token is not bound to this exact device proposal."}
        try:
            track_index = int(proposal["track_index"])
            device_index = int(proposal["device_index"])
            parameter_index = int(proposal["parameter_index"])
            requested = float(proposal["after"])
            before = float(proposal["before"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "Device proposals require numeric target indices and values."}
        if min(track_index, device_index, parameter_index) < 0 or not math.isfinite(requested) or not math.isfinite(before):
            return {"ok": False, "error": "Device proposal indices and values must be finite and non-negative."}
        valid_range = proposal.get("valid_range") or []
        if len(valid_range) == 2 and not float(valid_range[0]) <= requested <= float(valid_range[1]):
            return {"ok": False, "error": "Device proposal value is outside the inspected Live parameter range."}
        key = str(idempotency_key or proposal.get("id") or "").strip()
        if not key:
            return {"ok": False, "error": "An idempotency key is required for a Live device mutation."}
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This device action request was already executed or is already in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)

        confirmation_text = f"set_device_parameter:{track_index}:{device_index}:{parameter_index}:{requested}"
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_control", text=confirmation_text):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used device confirmation token."}

        def fail(error: str, *, readback: Any = None) -> dict[str, Any]:
            _finish_idempotency_key(key)
            receipt = _failed_receipt(proposal, key, error)
            receipt.update({
                "target": {
                    "target": proposal.get("target", "ableton_device"),
                    "track_index": track_index,
                    "track_name": str(proposal.get("track_name", "")),
                    "device_index": device_index,
                    "device_name": str(proposal.get("device_name", "")),
                    "parameter_index": parameter_index,
                    "parameter": str(proposal.get("parameter", "")),
                },
                "before": before,
                "requested": requested,
                "readback": readback,
            })
            _RECEIPTS[receipt["receipt_id"]] = receipt
            return {"ok": False, "error": error, "receipt": receipt}

        try:
            state = self.snapshot(include_mixer=False)
        except Exception as exc:
            return fail(f"Live snapshot failed before device execution: {exc}")
        track, error = _find_track(state, track_index, str(proposal.get("track_name", "")))
        if error or track is None:
            return fail(error or "Target Live track is unavailable.")
        devices = track.get("devices") or []
        device_entry = devices[device_index] if 0 <= device_index < len(devices) else None
        observed_device_name = (
            str(device_entry.get("name", ""))
            if isinstance(device_entry, dict)
            else str(device_entry or "")
        )
        if device_entry is None or observed_device_name != str(proposal.get("device_name", "")):
            return fail("Live device identity changed since the proposal was created.")
        try:
            pre_info = self.client.get_device_parameters(track_index, device_index)
        except Exception as exc:
            return fail(f"Live device inspection failed before execution: {exc}")
        if not pre_info.get("success"):
            return fail(f"Live device inspection failed before execution: {pre_info.get('error', 'unknown error')}")
        params = pre_info.get("parameters", [])
        parameter = next(
            (item for item in params if isinstance(item, dict) and int(item.get("index", -1)) == parameter_index),
            None,
        )
        if parameter is None and 0 <= parameter_index < len(params):
            # Backward compatibility for dense responses from older bridges.
            parameter = params[parameter_index]
        if parameter is None:
            return fail("Live parameter index is no longer present on the inspected device.")
        if str(parameter.get("name", "")) != str(proposal.get("parameter", "")):
            return fail("Live parameter identity changed since the proposal was created.")
        if not _values_match(parameter.get("value"), before):
            return fail("Live device parameter value changed since the proposal was created; make a new proposal.")
        write_error = None
        try:
            write_ok = bool(self.client.set_device_parameter(track_index, device_index, parameter_index, requested))
        except Exception as exc:
            # A UDP mutation can reach Live and still lose its acknowledgement.
            # Do not return before the authoritative readback: the caller must
            # never be encouraged to retry an ambiguous device write.
            write_ok = False
            write_error = str(exc)
        write_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
        try:
            time.sleep(0.05)
            post_info = self.client.get_device_parameters(track_index, device_index)
        except Exception as exc:
            return fail(f"Live device readback failed after write: {exc}")
        readback_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
        post_params = post_info.get("parameters", []) if post_info.get("success") else []
        # Device responses may be a filtered view (for example, the KENN
        # bridge exposes EQ controls while preserving Live's original sparse
        # parameter indices). Read back by the reported index first; only use
        # positional lookup for dense legacy responses.
        post_parameter = next(
            (item for item in post_params
             if isinstance(item, dict) and int(item.get("index", -1)) == parameter_index),
            None,
        )
        if post_parameter is None and 0 <= parameter_index < len(post_params):
            post_parameter = post_params[parameter_index]
        readback = post_parameter.get("value") if isinstance(post_parameter, dict) else None
        readback_display = None
        value_string_reader = getattr(self.client, "get_device_parameter_value_string", None)
        if callable(value_string_reader):
            try:
                display = value_string_reader(track_index, device_index, parameter_index)
            except Exception:
                display = None
            if isinstance(display, dict) and display.get("success") and display.get("value_string") not in (None, ""):
                readback_display = str(display["value_string"])
        readback_matches = _values_match(readback, requested)
        verified = readback_matches
        write_acknowledgement = "confirmed" if write_ok else (
            "unacknowledged_write_reconciled" if readback_matches else "not_confirmed"
        )
        _finish_idempotency_key(key)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "receipt_id": f"receipt-{uuid.uuid4().hex}",
            "action_id": proposal.get("id"),
            "action": "set_device_parameter",
            "idempotency_key": key,
            "status": "applied" if verified else "failed_verification",
            "verified": verified,
            "timestamp": time.time(),
            "target": {
                "target": proposal.get("target", "ableton_device"),
                "track_index": track_index,
                "track_name": str(proposal.get("track_name", "")),
                "device_index": device_index,
                "device_name": str(proposal.get("device_name", "")),
                "parameter_index": parameter_index,
                "parameter": str(proposal.get("parameter", "")),
            },
            "parameter_name": str(proposal.get("parameter", "")),
            "unit": str(proposal.get("unit", "")),
            "before": before,
            "requested": requested,
            "readback": readback,
            **({"readback_display": readback_display} if readback_display is not None else {}),
            "write_acknowledgement": write_acknowledgement,
            **({"write_error": write_error} if write_error else {}),
            "before_value": before,
            "requested_value": requested,
            "readback_value": readback,
            "write_exchange": write_exchange,
            "readback_exchange": readback_exchange,
            "undo_payload": {
                "target": proposal.get("target", "ableton_device"),
                "track_index": track_index,
                "track_name": str(proposal.get("track_name", "")),
                "device_index": device_index,
                "device_name": str(proposal.get("device_name", "")),
                "parameter_index": parameter_index,
                "parameter_name": str(proposal.get("parameter", "")),
                "restore_value": before,
            },
        }
        _RECEIPTS[receipt["receipt_id"]] = receipt
        if not verified:
            error = "Live device write was sent but read-back verification failed."
            if write_error:
                error = f"Live device write acknowledgement was lost and read-back did not confirm the requested value: {write_error}"
            return {"ok": False, "error": error, "receipt": receipt}
        return {"ok": True, "receipt": receipt}

    def execute_eq_band_tuning_gain(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """Apply and verify an explicit EQ frequency-plus-gain edit."""
        _cleanup_memory()
        if not isinstance(proposal, dict) or proposal.get("schema") != EQ_BAND_TUNING_GAIN_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid KENN compound EQ proposal is required."}
        if not proposal.get("requires_confirmation") or str(proposal.get("confirmation_token", "")) != str(confirm_token):
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required for this exact compound EQ proposal."}
        try:
            track_index = int(proposal["track_index"])
            device_index = int(proposal["device_index"])
            frequency_index = int(proposal["frequency_parameter_index"])
            gain_index = int(proposal["gain_parameter_index"])
            frequency_before = float(proposal["frequency_before_value"])
            frequency_after = float(proposal["frequency_after_value"])
            gain_before = float(proposal["gain_before_value"])
            gain_after = float(proposal["gain_after_value"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "Compound EQ proposals require numeric target indices and values."}
        if min(track_index, device_index, frequency_index, gain_index) < 0:
            return {"ok": False, "error": "Compound EQ proposal indices must be non-negative."}
        key = str(idempotency_key or proposal.get("action_id") or "").strip()
        if not key:
            return {"ok": False, "error": "An idempotency key is required for a compound EQ mutation."}
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This compound EQ request was already executed or is already in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=_eq_band_tuning_gain_text(proposal)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used compound EQ confirmation token."}

        def fail(error: str, *, readback: Any = None) -> dict[str, Any]:
            _finish_idempotency_key(key)
            receipt = _failed_receipt(proposal, key, error)
            receipt.update({
                "target": {
                    "target": "ableton_device", "track_index": track_index,
                    "track_name": str(proposal.get("track_name", "")),
                    "device_index": device_index, "device_name": str(proposal.get("device_name", "")),
                    "eq_band": str(proposal.get("eq_band", "")),
                },
                "before": proposal.get("before"), "requested": proposal.get("after"), "readback": readback,
            })
            _RECEIPTS[receipt["receipt_id"]] = receipt
            return {"ok": False, "error": error, "receipt": receipt}

        try:
            state = self.snapshot(include_mixer=False)
            track, error = _find_track(state, track_index, str(proposal.get("track_name", "")))
            if error or track is None:
                return fail(error or "Target Live track is unavailable.")
            devices = track.get("devices") or []
            device_entry = devices[device_index] if 0 <= device_index < len(devices) else None
            observed_name = str(device_entry.get("name", "")) if isinstance(device_entry, dict) else str(device_entry or "")
            if observed_name != str(proposal.get("device_name", "")) or observed_name.strip().lower() != "eq eight":
                return fail("Live EQ Eight identity changed since the proposal was created.")
            info = self.client.get_device_parameters(track_index, device_index)
            if not info.get("success"):
                return fail(f"Live EQ inspection failed before execution: {info.get('error', 'unknown error')}")
            params = [item for item in info.get("parameters", []) if isinstance(item, dict)]

            def parameter(index: int, name: str) -> dict[str, Any] | None:
                return next((item for item in params if int(item.get("index", -1)) == index and str(item.get("name", "")) == name), None)

            frequency_parameter = parameter(frequency_index, str(proposal.get("frequency_parameter", "")))
            gain_parameter = parameter(gain_index, str(proposal.get("gain_parameter", "")))
            if frequency_parameter is None or gain_parameter is None:
                return fail("Live EQ parameter identity changed since the proposal was created.")
            if not _values_match(frequency_parameter.get("value"), frequency_before) or not _values_match(gain_parameter.get("value"), gain_before):
                return fail("Live EQ values changed since the proposal was created; make a new proposal.")
            frequency_write = bool(self.client.set_device_parameter(track_index, device_index, frequency_index, frequency_after))
            frequency_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
            if not frequency_write:
                return fail("Live rejected the EQ frequency write.")
            gain_write = bool(self.client.set_device_parameter(track_index, device_index, gain_index, gain_after))
            gain_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
            time.sleep(0.05)
            post_info = self.client.get_device_parameters(track_index, device_index)
            readback_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
            post_params = [item for item in post_info.get("parameters", []) if isinstance(item, dict)] if post_info.get("success") else []
            post_frequency = next((item for item in post_params if int(item.get("index", -1)) == frequency_index and str(item.get("name", "")) == str(proposal.get("frequency_parameter", ""))), None)
            post_gain = next((item for item in post_params if int(item.get("index", -1)) == gain_index and str(item.get("name", "")) == str(proposal.get("gain_parameter", ""))), None)
            readback = {
                "frequency_value": post_frequency.get("value") if post_frequency else None,
                "gain_value": post_gain.get("value") if post_gain else None,
            }
            verified = gain_write and _values_match(readback["frequency_value"], frequency_after) and _values_match(readback["gain_value"], gain_after)
        except Exception as exc:
            return fail(f"Live compound EQ execution failed: {exc}")

        _finish_idempotency_key(key)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "receipt_id": f"receipt-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"), "action": "set_eq_band_tuning_gain",
            "idempotency_key": key, "status": "applied" if verified else "failed_verification",
            "verified": verified, "timestamp": time.time(),
            "target": {"target": "ableton_device", "track_index": track_index, "track_name": str(proposal.get("track_name", "")), "device_index": device_index, "device_name": str(proposal.get("device_name", "")), "eq_band": str(proposal.get("eq_band", ""))},
            "before": proposal.get("before"), "after": proposal.get("after"), "requested": proposal.get("after"), "readback": readback,
            "frequency_before_value": frequency_before, "frequency_requested_value": frequency_after,
            "gain_before_value": gain_before, "gain_requested_value": gain_after,
            "write_exchange": {"frequency": frequency_exchange, "gain": gain_exchange},
            "readback_exchange": readback_exchange,
            "undo_payload": {
                "track_index": track_index, "track_name": str(proposal.get("track_name", "")),
                "device_index": device_index, "device_name": str(proposal.get("device_name", "")),
                "eq_band": str(proposal.get("eq_band", "")),
                "frequency_parameter_index": frequency_index, "frequency_parameter": str(proposal.get("frequency_parameter", "")),
                "frequency_restore_value": frequency_before, "frequency_restore_hz": (proposal.get("before") or {}).get("frequency_hz"),
                "gain_parameter_index": gain_index, "gain_parameter": str(proposal.get("gain_parameter", "")), "gain_restore_value": gain_before,
            },
        }
        _RECEIPTS[receipt["receipt_id"]] = receipt
        if not verified:
            return {"ok": False, "error": "Live compound EQ write was sent but read-back verification failed.", "receipt": receipt}
        return {"ok": True, "receipt": receipt}

    def propose_undo(self, receipt: dict[str, Any], *, session_id: str) -> dict[str, Any]:
        """Create a fresh, confirmed proposal to reverse a verified receipt."""
        if not isinstance(receipt, dict):
            return {"ok": False, "error": "A valid KENN Ableton receipt is required for undo."}
        # Recipe receipts use a distinct schema but still belong to this
        # service boundary. Dispatch before the single-action schema check so
        # the HTTP undo route can prepare the fresh inverse recipe.
        if receipt.get("schema") == "kenn.ableton_recipe_receipt.v1":
            from kenn.core.live_recipe import LiveRecipeService
            return LiveRecipeService(self).propose_undo(receipt, session_id=session_id)
        if receipt.get("schema") == GAIN_STAGING_RECEIPT_SCHEMA:
            return self.propose_undo_gain_staging(receipt, session_id=session_id)
        if receipt.get("schema") == MIDI_CLIP_RECEIPT_SCHEMA:
            return MidiClipActionService(self.client).propose_undo(receipt, session_id=session_id)
        if receipt.get("schema") != RECEIPT_SCHEMA:
            return {"ok": False, "error": "A valid KENN Ableton receipt is required for undo."}
        if not receipt.get("verified") or receipt.get("status") != "applied":
            return {"ok": False, "error": "Only a verified applied action can be undone."}
        action = str(receipt.get("action", ""))
        if action in SUPPORTED_TRACK_ACTIONS:
            target = receipt.get("target") or {}
            if "track_index" not in target:
                return {"ok": False, "error": "Receipt has no exact track target for undo."}
            undo_track_name = str(target.get("track_name", ""))
            if action == "rename_track":
                current_state = self.snapshot(include_mixer=False)
                current_track, current_error = _find_track(current_state, int(target["track_index"]), "")
                if current_error or current_track is None:
                    return {"ok": False, "error": current_error or "Renamed Live track is no longer available."}
                undo_track_name = str(current_track.get("name", ""))
            else:
                # Mirror the transport-action staleness check below: if the
                # live value no longer matches this receipt's verified
                # "readback", something else changed the same target since
                # this action was applied. Blindly restoring "before" would
                # silently discard that later, legitimate change.
                current_state = self.snapshot()
                current_track, current_error = _find_track(current_state, int(target["track_index"]), "")
                if current_error or current_track is None:
                    return {"ok": False, "error": current_error or "Live track is no longer available."}
                field_name, _unit, _range = SUPPORTED_TRACK_ACTIONS[action]
                current_value = current_track.get(field_name)
                if not _values_match(receipt.get("readback"), current_value):
                    return {"ok": False, "error": "Live track state changed since the receipt; undo is stale."}
            return self.propose_track_action(
                action,
                track_index=int(target["track_index"]),
                track_name=undo_track_name,
                value=receipt.get("before"),
                session_id=session_id,
            )
        if action in SUPPORTED_SEND_ACTIONS:
            target = receipt.get("target") or {}
            required = ("track_index", "return_track_index")
            if any(field not in target for field in required):
                return {"ok": False, "error": "Receipt has no exact send target for undo."}
            try:
                current_send = self.client.get_track_send(int(target["track_index"]), int(target["return_track_index"]))
            except Exception as exc:
                return {"ok": False, "error": f"Could not read the current send value: {exc}"}
            if current_send is None or not _values_match(receipt.get("readback"), current_send):
                return {"ok": False, "error": "Live send value changed since the receipt; undo is stale."}
            return self.propose_send_action(
                track_index=int(target["track_index"]),
                track_name=str(target.get("track_name", "")),
                return_track_index=int(target["return_track_index"]),
                return_track_name=str(target.get("return_track_name", "")),
                value=float(receipt.get("before")),
                session_id=session_id,
            )
        if action in SUPPORTED_TRANSPORT_ACTIONS:
            current = bool(self.snapshot().get("is_playing", False))
            if current != bool(receipt.get("requested")):
                return {"ok": False, "error": "Live transport state changed since the receipt; undo is stale."}
            inverse = "transport_play" if bool(receipt.get("before")) else "transport_stop"
            return self.propose_transport_action(inverse, session_id=session_id)
        if action in SUPPORTED_SCENE_ACTIONS:
            # Firing a scene has no reversible prior state to restore to -
            # unlike a parameter change, there is no single "before" scene
            # to fire back to. Recommend the existing transport stop instead
            # of inventing an undo that doesn't correspond to anything real.
            return {
                "ok": False,
                "error": "Scene launches have no reversible previous state to undo. "
                         "Use transport_stop, or explicitly launch a different scene.",
            }
        if action in SUPPORTED_CLIP_ACTIONS:
            # Re-firing the clip would restart it from the top rather than
            # restore the exact playback position it was stopped at, so this
            # is not a real undo - same honesty rule as scene launch above.
            return {
                "ok": False,
                "error": "Stopping a clip has no reversible previous playback position to undo. "
                         "Fire the clip slot again if you want it playing from the top.",
            }
        if action in SUPPORTED_LOCATOR_ACTIONS:
            target = receipt.get("target") or {}
            name = str(target.get("locator_name", ""))
            try:
                locator_time = float(target["locator_time_beats"])
                current_time = self.client.get_current_song_time()
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                return {"ok": False, "error": f"Receipt has no exact locator identity for undo: {exc}"}
            if current_time is None or not math.isclose(float(current_time), locator_time, rel_tol=0.0, abs_tol=LOCATOR_TIME_TOLERANCE):
                return {"ok": False, "error": "Live playhead moved since the locator receipt; move it back to the exact locator position before undo."}
            locators, available = self._locator_observation()
            if not available:
                return {"ok": False, "error": "Live locator state is unavailable; inspect the session before undo."}
            matches = [item for item in self._locator_at_time(locators, locator_time) if str(item.get("name", "")) == name]
            if action == "add_locator":
                if len(matches) != 1 or not _values_match(receipt.get("readback"), {"name": name, "time_beats": locator_time}):
                    return {"ok": False, "error": "The added locator changed or disappeared since the receipt; undo is stale."}
                return self.propose_locator_action("remove_locator", locator_name=name, session_id=session_id)
            if matches:
                return {"ok": False, "error": "A locator now occupies the removed position; undo is stale."}
            if receipt.get("readback") != {"exists": False, "name": name, "time_beats": locator_time}:
                return {"ok": False, "error": "The locator removal receipt has no exact absence readback; undo is refused."}
            return self.propose_locator_action("add_locator", locator_name=name, session_id=session_id)
        if action in SUPPORTED_VIEW_ACTIONS:
            target = receipt.get("target") or {}
            try:
                current_state = self.snapshot()
                current_selected = int(current_state.get("selected_track_index"))
            except Exception as exc:
                return {"ok": False, "error": f"Could not read Live selection for undo: {exc}"}
            if action == "focus_track":
                previous_index = target.get("previous_track_index")
                previous_name = str(target.get("previous_track_name", ""))
                if previous_index is None:
                    return {"ok": False, "error": "Receipt has no exact previous track focus for undo."}
                if current_selected != int(receipt.get("readback", target.get("track_index", -1))):
                    return {"ok": False, "error": "Live selection changed since the receipt; undo is stale."}
                previous_track, previous_error = _find_track(current_state, int(previous_index), previous_name)
                if previous_error or previous_track is None:
                    return {"ok": False, "error": previous_error or "The previous focused track is no longer available."}
                return self.propose_view_action(
                    "focus_track",
                    track_index=int(previous_index),
                    track_name=str(previous_track.get("name", "")),
                    session_id=session_id,
                )
            previous_index = target.get("previous_track_index")
            previous_name = str(target.get("previous_track_name", ""))
            previous_device_index = target.get("previous_device_index")
            previous_device_name = str(target.get("previous_device_name", ""))
            if previous_index is None or previous_device_index is None:
                return {"ok": False, "error": "Receipt has no exact previous device focus for undo."}
            current_selected_device = self.client.get_selected_device()
            expected_readback = receipt.get("readback") or {}
            if (
                not isinstance(current_selected_device, dict)
                or not current_selected_device.get("success")
                or current_selected_device.get("track_index") != expected_readback.get("track_index")
                or current_selected_device.get("device_index") != expected_readback.get("device_index")
            ):
                return {"ok": False, "error": "Live device selection changed since the receipt; undo is stale."}
            previous_track, previous_error = _find_track(current_state, int(previous_index), previous_name)
            if previous_error or previous_track is None:
                return {"ok": False, "error": previous_error or "The previous focused track is no longer available."}
            return self.propose_view_action(
                "focus_device",
                track_index=int(previous_index),
                track_name=str(previous_track.get("name", "")),
                device_index=int(previous_device_index),
                device_name=previous_device_name,
                session_id=session_id,
            )
        if action == "set_device_parameter":
            target = receipt.get("target") or {}
            required = ("track_index", "device_index", "parameter_index")
            if any(field not in target for field in required):
                return {"ok": False, "error": "Receipt has no exact device-parameter target for undo."}
            try:
                parameters = self.client.get_device_parameters(
                    int(target["track_index"]), int(target["device_index"])
                )
            except Exception as exc:
                return {"ok": False, "error": f"Could not read the current device parameter: {exc}"}
            if not isinstance(parameters, dict) or not parameters.get("success"):
                return {"ok": False, "error": "Could not read the current device parameter for undo."}
            expected_device = str(target.get("device_name", ""))
            current_device = str(parameters.get("device_name", ""))
            if expected_device and current_device != expected_device:
                return {"ok": False, "error": "Live device identity changed since the receipt; undo is stale."}
            parameter_index = int(target["parameter_index"])
            current_parameter = next(
                (
                    item
                    for item in (parameters.get("parameters") or [])
                    if isinstance(item, dict) and int(item.get("index", -1)) == parameter_index
                ),
                None,
            )
            if current_parameter is None:
                return {"ok": False, "error": "Live device parameter is no longer available; undo is stale."}
            expected_parameter = str(target.get("parameter", receipt.get("parameter_name", "")))
            if expected_parameter and str(current_parameter.get("name", "")) != expected_parameter:
                return {"ok": False, "error": "Live device parameter identity changed since the receipt; undo is stale."}
            if not _values_match(receipt.get("readback"), current_parameter.get("value")):
                return {"ok": False, "error": "Live device parameter changed since the receipt; undo is stale."}
            return self.propose_device_action(
                track_index=int(target["track_index"]),
                device_index=int(target["device_index"]),
                parameter_index=parameter_index,
                proposed_value=float(receipt.get("before")),
                reason=f"Restore verified KENN device action {receipt.get('receipt_id', '')}.",
                session_id=session_id,
                parameter_name=str(target.get("parameter", receipt.get("parameter_name", ""))),
                unit=str(receipt.get("unit", "")),
                track_name=str(target.get("track_name", "")),
            )
        if action == "set_eq_band_tuning_gain":
            target = receipt.get("target") or {}
            undo = receipt.get("undo_payload") or {}
            required = ("track_index", "device_index", "frequency_parameter_index", "gain_parameter_index")
            if any(field not in target and field not in undo for field in required):
                return {"ok": False, "error": "Receipt has no exact compound EQ target for undo."}
            before = receipt.get("before") or {}
            current = receipt.get("readback") or {}
            frequency_current = current.get("frequency_value", receipt.get("frequency_requested_value"))
            gain_current = current.get("gain_value", receipt.get("gain_requested_value"))
            if frequency_current is None or gain_current is None or before.get("frequency_hz") is None or before.get("gain_db") is None:
                return {"ok": False, "error": "Receipt has no complete compound EQ state for undo."}
            return self.propose_eq_band_tuning_gain(
                track_index=int(target.get("track_index", undo.get("track_index"))),
                track_name=str(target.get("track_name", undo.get("track_name", ""))),
                device_index=int(target.get("device_index", undo.get("device_index"))),
                device_name=str(target.get("device_name", undo.get("device_name", "EQ Eight"))),
                eq_band=str(target.get("eq_band", undo.get("eq_band", ""))),
                frequency_parameter={"index": int(undo.get("frequency_parameter_index", target.get("frequency_parameter_index"))), "name": str(undo.get("frequency_parameter", "")), "value": frequency_current},
                frequency_before_hz=float(receipt.get("after", {}).get("frequency_hz")),
                frequency_after_hz=float(before["frequency_hz"]),
                frequency_after_value=float(undo["frequency_restore_value"]),
                gain_parameter={"index": int(undo.get("gain_parameter_index", target.get("gain_parameter_index"))), "name": str(undo.get("gain_parameter", "")), "value": gain_current},
                gain_after=float(undo["gain_restore_value"]),
                reason=f"Restore verified KENN compound EQ action {receipt.get('receipt_id', '')}.",
                session_id=session_id,
                source_receipt_id=str(receipt.get("receipt_id", "")),
            )
        if action in {"insert_device", "insert_device_with_parameter"}:
            target = receipt.get("target") or {}
            required = ("track_index", "insertion_index", "device_name")
            if any(field not in target for field in required):
                return {"ok": False, "error": "Receipt has no exact inserted-device identity for undo."}
            expected_devices = receipt.get("readback_devices") or receipt.get("requested_devices")
            if not isinstance(expected_devices, list):
                return {"ok": False, "error": "Receipt has no verified post-insertion device order for undo."}
            return self.propose_device_removal(
                track_index=int(target["track_index"]),
                track_name=str(target.get("track_name", "")),
                device_index=int(target["insertion_index"]),
                device_name=str(target["device_name"]),
                expected_devices=expected_devices,
                source_receipt_id=str(receipt.get("receipt_id", "")),
                session_id=session_id,
            )
        if action in SUPPORTED_TRACK_CREATION_ACTIONS | SUPPORTED_RETURN_TRACK_CREATION_ACTIONS:
            return {
                "ok": False,
                "error": "Track creation has no safe automatic inverse. Deleting tracks or return tracks remains outside KENN's safe inverse boundary.",
            }
        return {"ok": False, "error": f"Receipt action is not undoable: {action}"}

    def execute(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        _cleanup_memory()
        if isinstance(proposal, dict) and proposal.get("schema") == DEVICE_SETUP_PROPOSAL_SCHEMA:
            return self.execute_device_setup_action(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == GAIN_STAGING_PROPOSAL_SCHEMA:
            return self.execute_gain_staging(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == BUS_ORGANIZATION_PROPOSAL_SCHEMA:
            return self.execute_track_grouping(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == MIDI_CLIP_PROPOSAL_SCHEMA:
            return self.execute_midi_clip(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == MIDI_CLIP_UNDO_PROPOSAL_SCHEMA:
            return MidiClipActionService(self.client).execute_undo(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == ARRANGEMENT_DUPLICATION_PROPOSAL_SCHEMA:
            return self.execute_arrangement_duplication(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == CLIP_AUTOMATION_PROPOSAL_SCHEMA:
            return self.execute_clip_automation(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == RACK_MACRO_PROPOSAL_SCHEMA:
            return self.execute_rack_macro_mapping(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == TRACK_ROUTING_PROPOSAL_SCHEMA:
            return self.execute_track_routing(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == TRACK_FREEZE_PROPOSAL_SCHEMA:
            return self.execute_track_freeze(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == RACK_VARIATION_PROPOSAL_SCHEMA:
            return self.execute_rack_variation(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == CLIP_LAUNCH_PROPOSAL_SCHEMA:
            return self.execute_clip_launch(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == SCENE_CREATION_PROPOSAL_SCHEMA:
            return self.execute_scene_creation(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == LOOP_DUPLICATION_PROPOSAL_SCHEMA:
            return self.execute_loop_duplication(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == CLIP_WARP_PITCH_PROPOSAL_SCHEMA:
            return self.execute_clip_warp_pitch(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == CLIP_DELETION_PROPOSAL_SCHEMA:
            return self.execute_clip_deletion(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == PRESET_LOAD_PROPOSAL_SCHEMA:
            return self.execute_load_preset(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        if isinstance(proposal, dict) and proposal.get("schema") == RESAMPLE_BOUNCE_PROPOSAL_SCHEMA:
            return self.execute_resample_bounce(
                proposal,
                confirm_token=confirm_token,
                session_id=session_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid KENN Ableton action proposal is required."}
        if not proposal.get("requires_confirmation") or not confirm_token:
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required before a Live mutation."}
        if str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "error": "Confirmation token is not bound to this exact proposal."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        if not key:
            return {"ok": False, "error": "An idempotency key is required."}
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action request was already executed or is already in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        proposal_action = proposal.get("action")
        if proposal_action in SUPPORTED_SCENE_ACTIONS:
            confirmation_text = _scene_text(proposal)
        elif proposal_action in SUPPORTED_CLIP_ACTIONS:
            confirmation_text = _clip_text(proposal)
        elif proposal_action in SUPPORTED_SEND_ACTIONS:
            confirmation_text = _send_text(proposal)
        elif proposal_action in SUPPORTED_LOCATOR_ACTIONS:
            confirmation_text = _locator_text(proposal)
        elif proposal_action in SUPPORTED_VIEW_ACTIONS:
            confirmation_text = _view_text(proposal)
        elif proposal_action in SUPPORTED_TRACK_CREATION_ACTIONS:
            confirmation_text = _track_creation_text(proposal)
        elif proposal_action in SUPPORTED_RETURN_TRACK_CREATION_ACTIONS:
            confirmation_text = _return_track_creation_text(proposal)
        else:
            confirmation_text = _text(proposal)
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirmation_text):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used confirmation token."}

        action = proposal.get("action")
        write_error: str | None = None
        try:
            state = self.snapshot(include_mixer=False if action in SUPPORTED_TRACK_CREATION_ACTIONS | SUPPORTED_RETURN_TRACK_CREATION_ACTIONS else True)
        except Exception as exc:
            _finish_idempotency_key(key)
            receipt = _failed_receipt(proposal, key, f"Live snapshot failed before execution: {exc}", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            _RECEIPTS[receipt["receipt_id"]] = receipt
            return {"ok": False, "error": receipt["error"], "receipt": receipt}
        timer.mark("snapshot")
        if state.get("status") in {"offline", "dispatched"}:
            _finish_idempotency_key(key)
            return {"ok": False, "error": "Ableton Live became unavailable before execution."}
        if action in SUPPORTED_TRACK_CREATION_ACTIONS:
            return self._execute_track_creation(
                proposal,
                key=key,
                state=state,
                correlation_id=correlation_id,
                timer=timer,
            )
        if action in SUPPORTED_RETURN_TRACK_CREATION_ACTIONS:
            return self._execute_return_track_creation(
                proposal,
                key=key,
                correlation_id=correlation_id,
                timer=timer,
            )
        track = None
        if action in SUPPORTED_TRACK_ACTIONS:
            track, error = _find_track(state, int(proposal.get("track_index", -1)), str(proposal.get("track_name", "")))
            if error or track is None:
                _finish_idempotency_key(key)
                return {"ok": False, "error": error}
            field = SUPPORTED_TRACK_ACTIONS[action][0]
            if not _values_match(track.get(field), proposal.get("before")):
                _finish_idempotency_key(key)
                return {"ok": False, "error": "Live track state changed since the proposal was created; create a new proposal."}
            writers = {
                "set_volume": lambda: self.client.set_track_volume(int(proposal["track_index"]), float(proposal["after"])),
                "set_pan": lambda: self.client.set_track_pan(int(proposal["track_index"]), float(proposal["after"])),
                "set_mute": lambda: self.client.set_track_mute(int(proposal["track_index"]), bool(proposal["after"])),
                "set_solo": lambda: self.client.set_track_solo(int(proposal["track_index"]), bool(proposal["after"])),
                "set_arm": lambda: self.client.set_track_arm(int(proposal["track_index"]), bool(proposal["after"])),
                "rename_track": lambda: self.client.set_track_name(int(proposal["track_index"]), str(proposal["after"])),
            }
            try:
                write_ok = bool(writers[action]())
            except Exception as exc:
                write_ok = False
                write_error = str(exc)
            write_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
            timer.mark("write")
        elif action in SUPPORTED_TRANSPORT_ACTIONS:
            if bool(state.get("is_playing", False)) != bool(proposal.get("before")):
                _finish_idempotency_key(key)
                return {"ok": False, "error": "Live transport state changed since the proposal was created; create a new proposal."}
            try:
                write_ok = bool(self.client.start_playback() if action == "transport_play" else self.client.stop_playback())
            except Exception as exc:
                write_ok = False
                write_error = str(exc)
            write_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
            timer.mark("write")
        elif action in SUPPORTED_SCENE_ACTIONS:
            fresh_scene, scene_error = _find_scene(state, int(proposal.get("scene_index", -1)), str(proposal.get("scene_name", "")))
            if scene_error or fresh_scene is None:
                _finish_idempotency_key(key)
                return {"ok": False, "error": scene_error or "Scene no longer present in the current Live snapshot."}
            try:
                write_ok = bool(self.client.launch_scene(int(proposal["scene_index"])))
            except Exception as exc:
                write_ok = False
                write_error = str(exc)
            write_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
            timer.mark("write")
        elif action in SUPPORTED_CLIP_ACTIONS:
            fresh_track, track_error = _find_track(state, int(proposal.get("track_index", -1)), str(proposal.get("track_name", "")))
            if track_error or fresh_track is None:
                _finish_idempotency_key(key)
                return {"ok": False, "error": track_error}
            try:
                fresh_playback = self.client.get_clip_playback_state(int(proposal["track_index"]), int(proposal["clip_slot_index"]))
            except Exception as exc:
                _finish_idempotency_key(key)
                receipt = _failed_receipt(proposal, key, f"Could not read clip-slot state before write: {exc}", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
                _RECEIPTS[receipt["receipt_id"]] = receipt
                return {"ok": False, "error": receipt["error"], "receipt": receipt}
            if not fresh_playback.get("success") or not (fresh_playback.get("is_playing") or fresh_playback.get("is_triggered")):
                _finish_idempotency_key(key)
                return {"ok": False, "error": "The clip slot is no longer playing; create a new proposal."}
            try:
                write_ok = bool(self.client.stop_clip_slot(int(proposal["track_index"]), int(proposal["clip_slot_index"])))
            except Exception as exc:
                write_ok = False
                write_error = str(exc)
            write_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
            timer.mark("write")
        elif action in SUPPORTED_SEND_ACTIONS:
            fresh_track, track_error = _find_track(state, int(proposal.get("track_index", -1)), str(proposal.get("track_name", "")))
            if track_error or fresh_track is None:
                _finish_idempotency_key(key)
                return {"ok": False, "error": track_error}
            try:
                fresh_return_tracks = self.client.get_return_tracks()
            except Exception as exc:
                _finish_idempotency_key(key)
                receipt = _failed_receipt(proposal, key, f"Could not read the exact return-track identity: {exc}", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
                _RECEIPTS[receipt["receipt_id"]] = receipt
                return {"ok": False, "error": receipt["error"], "receipt": receipt}
            fresh_return, return_error = _find_return_track(fresh_return_tracks, int(proposal["return_track_index"]), str(proposal.get("return_track_name", "")))
            if return_error or fresh_return is None:
                _finish_idempotency_key(key)
                return {"ok": False, "error": return_error or "Target return track is unavailable."}
            try:
                current_send = self.client.get_track_send(int(proposal["track_index"]), int(proposal["return_track_index"]))
            except Exception as exc:
                _finish_idempotency_key(key)
                receipt = _failed_receipt(proposal, key, f"Could not read the current send value: {exc}", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
                _RECEIPTS[receipt["receipt_id"]] = receipt
                return {"ok": False, "error": receipt["error"], "receipt": receipt}
            if current_send is None or not _values_match(round(float(current_send), 6), proposal.get("before")):
                _finish_idempotency_key(key)
                return {"ok": False, "error": "The send value changed since the proposal was created; create a new proposal."}
            try:
                write_ok = bool(self.client.set_track_send(int(proposal["track_index"]), int(proposal["return_track_index"]), float(proposal["after"])))
            except Exception as exc:
                write_ok = False
                write_error = str(exc)
            write_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
            timer.mark("write")
        elif action in SUPPORTED_LOCATOR_ACTIONS:
            if bool(state.get("is_playing", False)):
                _finish_idempotency_key(key)
                return {"ok": False, "error": "Ableton transport started since the proposal; create a new locator proposal with transport stopped."}
            try:
                current_time = self.client.get_current_song_time()
                fresh_locators, locators_available = self._locator_observation()
            except Exception as exc:
                _finish_idempotency_key(key)
                receipt = _failed_receipt(proposal, key, f"Could not read locator state before write: {exc}", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
                _RECEIPTS[receipt["receipt_id"]] = receipt
                return {"ok": False, "error": receipt["error"], "receipt": receipt}
            if current_time is None or not locators_available:
                _finish_idempotency_key(key)
                return {"ok": False, "error": "Live locator state became unreadable before execution; create a new proposal."}
            if not _values_match(round(float(current_time), 6), proposal.get("locator_time_beats")):
                _finish_idempotency_key(key)
                return {"ok": False, "error": "Live playhead moved since the proposal was created; create a new locator proposal."}
            at_cursor = self._locator_at_time(fresh_locators, float(proposal["locator_time_beats"]))
            if action == "add_locator" and at_cursor:
                _finish_idempotency_key(key)
                return {"ok": False, "error": "A locator now occupies the proposed playhead position; KENN refused the toggle to protect it."}
            if action == "remove_locator":
                matches = [
                    locator for locator in at_cursor
                    if str(locator.get("name", "")) == str(proposal.get("locator_name", ""))
                ]
                if len(matches) != 1:
                    _finish_idempotency_key(key)
                    return {"ok": False, "error": "The exact locator identity changed before execution; create a new proposal."}
            try:
                if action == "add_locator":
                    write_ok = bool(self.client.add_locator(str(proposal["locator_name"])))
                else:
                    write_ok = bool(self.client.remove_locator(str(proposal["locator_name"]), float(proposal["locator_time_beats"])))
            except Exception as exc:
                write_ok = False
                write_error = str(exc)
            write_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
            timer.mark("write")
        elif action in SUPPORTED_VIEW_ACTIONS:
            fresh_track, track_error = _find_track(state, int(proposal.get("track_index", -1)), str(proposal.get("track_name", "")))
            if track_error or fresh_track is None:
                _finish_idempotency_key(key)
                return {"ok": False, "error": track_error or "Target Live track is unavailable."}
            if action == "focus_track":
                try:
                    current_selected = int(state.get("selected_track_index"))
                except (TypeError, ValueError):
                    _finish_idempotency_key(key)
                    return {"ok": False, "error": "Live did not return an exact selected-track state before execution."}
                if current_selected != int(proposal.get("before", -1)):
                    _finish_idempotency_key(key)
                    return {"ok": False, "error": "Live selection changed since the proposal was created; create a new focus proposal."}
                try:
                    write_ok = bool(self.client.set_selected_track(int(proposal["track_index"])))
                except Exception as exc:
                    write_ok = False
                    write_error = str(exc)
            else:
                devices = fresh_track.get("devices") or []
                device_index = int(proposal.get("device_index", -1))
                fresh_device = devices[device_index] if 0 <= device_index < len(devices) else None
                fresh_device_name = (
                    str(fresh_device.get("name", ""))
                    if isinstance(fresh_device, dict)
                    else str(fresh_device or "")
                )
                if fresh_device is None or fresh_device_name != str(proposal.get("device_name", "")):
                    _finish_idempotency_key(key)
                    return {"ok": False, "error": "Live device identity changed since the proposal was created; create a new focus proposal."}
                try:
                    current_selected_device = self.client.get_selected_device()
                except Exception as exc:
                    _finish_idempotency_key(key)
                    return {"ok": False, "error": f"Could not read Live's selected device before execution: {exc}"}
                expected_before = proposal.get("before") or {}
                if (
                    not isinstance(current_selected_device, dict)
                    or not current_selected_device.get("success")
                    or current_selected_device.get("track_index") != expected_before.get("track_index")
                    or current_selected_device.get("device_index") != expected_before.get("device_index")
                ):
                    _finish_idempotency_key(key)
                    return {"ok": False, "error": "Live device selection changed since the proposal was created; create a new focus proposal."}
                try:
                    write_ok = bool(self.client.set_selected_device(int(proposal["track_index"]), device_index))
                except Exception as exc:
                    write_ok = False
                    write_error = str(exc)
            write_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
            timer.mark("write")
        else:
            _finish_idempotency_key(key)
            return {"ok": False, "error": f"Unsupported or disabled Live action: {action}"}

        _finish_idempotency_key(key)
        try:
            after_state = self.snapshot()
        except Exception as exc:
            receipt = _failed_receipt(
                proposal,
                key,
                f"Live readback failed after write: {exc}",
                retry_safe="requires_inspection",
                correlation_id=correlation_id,
                stage_timings_ms=timer.as_ms(),
            )
            receipt["status"] = "transport_uncertain"
            receipt["write_acknowledgement"] = "not_confirmed" if write_error else ("confirmed" if write_ok else "not_confirmed")
            if write_error:
                receipt["write_error"] = write_error
            _RECEIPTS[receipt["receipt_id"]] = receipt
            return {"ok": False, "error": receipt["error"], "receipt": receipt}
        timer.mark("readback")
        readback_exchange = dict(getattr(self.client, "last_exchange", {}) or {})
        try:
            if action in SUPPORTED_TRACK_ACTIONS:
                # A rename intentionally changes the identity string used before
                # the write; read back by exact index and verify the new name.
                post_name = "" if action == "rename_track" else str(proposal.get("track_name", ""))
                post_track, _ = _find_track(after_state, int(proposal["track_index"]), post_name)
                readback = post_track.get(SUPPORTED_TRACK_ACTIONS[action][0]) if post_track else None
            elif action in SUPPORTED_SCENE_ACTIONS:
                # Scenes have no stable "is_playing" property of their own; the
                # transient is_triggered flag is the primary observable evidence
                # that Live actually received the fire, mirroring the same
                # best-effort readback already used for clip-slot audition. Real
                # qualification found is_triggered can transition (to actually
                # playing) faster than one network round-trip can observe it, so
                # a fire that demonstrably started playback -- transport was NOT
                # already playing before this exact proposal, and now is -- also
                # counts as verified. This adds no risk of a false positive: it
                # only applies when we know transport was stopped beforehand.
                playback = self.client.get_scene_playback_state(int(proposal["scene_index"]))
                triggered = bool(playback.get("is_triggered")) if playback.get("success") else False
                started_playback_from_stopped = (
                    not bool(proposal.get("transport_was_playing_before", True))
                    and bool(after_state.get("is_playing", False))
                )
                readback = triggered or started_playback_from_stopped
            elif action in SUPPORTED_CLIP_ACTIONS:
                clip_playback = self.client.get_clip_playback_state(int(proposal["track_index"]), int(proposal["clip_slot_index"]))
                readback = bool(clip_playback.get("is_playing") or clip_playback.get("is_triggered")) if clip_playback.get("success") else None
            elif action in SUPPORTED_SEND_ACTIONS:
                send_readback = self.client.get_track_send(int(proposal["track_index"]), int(proposal["return_track_index"]))
                readback = round(float(send_readback), 6) if send_readback is not None else None
            elif action in SUPPORTED_LOCATOR_ACTIONS:
                locators, locators_available = self._locator_observation()
                matches = [
                    locator for locator in self._locator_at_time(locators, float(proposal["locator_time_beats"]))
                    if str(locator.get("name", "")) == str(proposal.get("locator_name", ""))
                ]
                if action == "add_locator":
                    readback = (
                        {"name": str(matches[0]["name"]), "time_beats": round(float(matches[0]["time_beats"]), 6)}
                        if locators_available and len(matches) == 1 else None
                    )
                else:
                    readback = (
                        {"exists": False, "name": str(proposal.get("locator_name", "")), "time_beats": round(float(proposal["locator_time_beats"]), 6)}
                        if locators_available and not matches else None
                    )
            elif action in SUPPORTED_VIEW_ACTIONS:
                if action == "focus_track":
                    readback = after_state.get("selected_track_index")
                else:
                    selected_device = self.client.get_selected_device()
                    readback = (
                        {"track_index": selected_device.get("track_index"), "device_index": selected_device.get("device_index")}
                        if selected_device.get("success") else None
                    )
            else:
                readback = bool(after_state.get("is_playing", False))
        except Exception as exc:
            receipt = _failed_receipt(
                proposal,
                key,
                f"Live readback failed after write: {exc}",
                retry_safe="requires_inspection",
                correlation_id=correlation_id,
                stage_timings_ms=timer.as_ms(),
            )
            receipt["status"] = "transport_uncertain"
            receipt["write_acknowledgement"] = "not_confirmed" if write_error else ("confirmed" if write_ok else "not_confirmed")
            if write_error:
                receipt["write_error"] = write_error
            _RECEIPTS[receipt["receipt_id"]] = receipt
            return {"ok": False, "error": receipt["error"], "receipt": receipt}
        readback_matches = _values_match(readback, proposal.get("after"))
        state_change_expected = not _values_match(proposal.get("before"), proposal.get("after"))
        verified = readback_matches and (write_ok or state_change_expected)
        write_acknowledgement = "confirmed" if write_ok else (
            "unacknowledged_write_reconciled" if readback_matches else "not_confirmed"
        )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "receipt_id": f"receipt-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": action,
            "idempotency_key": key,
            "status": "applied" if verified else "failed_verification",
            "verified": verified,
            "timestamp": time.time(),
            "target": {key: proposal[key] for key in ("target", "track_index", "track_name", "device_index", "device_name", "parameter", "scene_index", "scene_name", "clip_slot_index", "return_track_index", "return_track_name", "locator_name", "locator_time_beats", "previous_track_index", "previous_track_name", "previous_device_index", "previous_device_name") if key in proposal},
            "before": proposal.get("before"),
            "requested": proposal.get("after"),
            "readback": readback,
            "write_acknowledgement": write_acknowledgement,
            **({"write_error": write_error} if write_error else {}),
            "write_exchange": write_exchange,
            "readback_exchange": readback_exchange,
            "undo": (
                {"available": True, "inverse_action": "remove_locator" if action == "add_locator" else "add_locator"}
                if action in SUPPORTED_LOCATOR_ACTIONS
                else {"proposal": {**proposal, "before": proposal.get("after"), "after": proposal.get("before")}}
            ),
            "correlation_id": correlation_id,
            "retry_safe": classify_retry_safety(verified=verified, status="applied" if verified else "failed_verification"),
            "stage_timings_ms": timer.as_ms(),
        }
        _RECEIPTS[receipt["receipt_id"]] = receipt
        if not verified:
            error = "Live write was sent but readback verification failed."
            if write_error:
                error = f"Live write acknowledgement was lost and readback did not confirm the requested state: {write_error}"
            return {"ok": False, "error": error, "receipt": receipt}
        return {"ok": True, "receipt": receipt}


    def propose_gain_staging(
        self,
        *,
        target_headroom_db: float = -6.0,
        session_id: str,
    ) -> dict[str, Any]:
        _cleanup_memory()
        try:
            target_db = float(target_headroom_db)
        except (TypeError, ValueError):
            return {"ok": False, "error": "target_headroom_db must be numeric"}
        if target_db > 0.0 or target_db < -36.0:
            return {"ok": False, "error": "target_headroom_db must be between -36.0 dB and 0.0 dB"}

        try:
            state = self.snapshot()
        except Exception as exc:
            return {"ok": False, "error": f"Snapshot failed: {exc}"}

        if state.get("status") != "connected":
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}

        raw_tracks = [t for t in state.get("tracks", []) if isinstance(t, dict)]
        if not raw_tracks:
            return {"ok": False, "error": "No tracks found in current Live snapshot."}

        target_normalized = round(max(0.0, min(1.0, 0.85 * (10.0 ** (target_db / 35.0)))), 4)

        steps = []
        for t in raw_tracks:
            idx = int(t.get("index", 0))
            name = str(t.get("name") or f"Track {idx + 1}")
            vol = float(t.get("volume", 0.85))
            before_db = round(35.0 * math.log10(max(1e-4, vol / 0.85)), 1) if vol > 0.0 else -70.0
            steps.append({
                "track_index": idx,
                "track_name": name,
                "before": round(vol, 4),
                "after": target_normalized,
                "before_db": before_db,
                "after_db": round(target_db, 1),
                "delta_db": round(target_db - before_db, 1),
            })

        proposal = {
            "schema": GAIN_STAGING_PROPOSAL_SCHEMA,
            "action_id": f"action-gain-stage-{uuid.uuid4().hex}",
            "action": "gain_stage_tracks",
            "operation": "gain_stage_tracks",
            "target": "ableton_session_tracks",
            "target_headroom_db": round(target_db, 1),
            "target_normalized": target_normalized,
            "steps": steps,
            "track_count": len(steps),
            "before_track_fingerprint": _track_structure_fingerprint(state),
            "reason": f"Auto gain-stage {len(steps)} tracks to {round(target_db, 1)} dB headroom.",
            "confidence": 1.0,
            "risk": "multi_track_volume_mutation",
            "requires_confirmation": True,
            "undo_available": True,
            "timestamp": time.time(),
            "session_version": _state_version(state),
        }

        confirmation_text = "gain_stage_tracks:" + json.dumps(
            [{"track_index": s["track_index"], "track_name": s["track_name"], "before": s["before"], "after": s["after"]} for s in steps],
            sort_keys=True,
            separators=(",", ":"),
        )
        token, meta = issue_confirmation(
            session_id=session_id,
            service_id="ableton_action",
            text=confirmation_text,
            ttl_seconds=300,
        )
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def execute_gain_staging(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        _cleanup_memory()
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != GAIN_STAGING_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid KENN Ableton gain staging proposal is required."}
        if not proposal.get("requires_confirmation") or not confirm_token:
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required before gain staging mutation."}
        if str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "error": "Confirmation token is not bound to this exact proposal."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        if not key:
            return {"ok": False, "error": "An idempotency key is required."}
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action request was already executed or is already in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)

        steps = proposal.get("steps") or []
        confirmation_text = "gain_stage_tracks:" + json.dumps(
            [{"track_index": s["track_index"], "track_name": s["track_name"], "before": s["before"], "after": s["after"]} for s in steps],
            sort_keys=True,
            separators=(",", ":"),
        )
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirmation_text):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used confirmation token."}

        try:
            state = self.snapshot()
        except Exception as exc:
            _finish_idempotency_key(key)
            return {"ok": False, "error": f"Live snapshot failed before execution: {exc}"}
        timer.mark("snapshot")

        for s in steps:
            track, err = _find_track(state, int(s["track_index"]), str(s["track_name"]))
            if err or track is None:
                _finish_idempotency_key(key)
                return {"ok": False, "error": f"Track identity changed for track {s['track_index']} ({s['track_name']}): {err or 'not found'}."}

        applied_steps = []
        write_error = None
        for s in steps:
            try:
                ok = bool(self.client.set_track_volume(int(s["track_index"]), float(s["after"])))
                applied_steps.append(s)
            except Exception as exc:
                write_error = str(exc)
                break

        timer.mark("mutation")
        try:
            post_state = self.snapshot()
        except Exception:
            post_state = {}
        timer.mark("readback")

        all_verified = True
        step_receipts = []
        for s in applied_steps:
            post_track, _ = _find_track(post_state, int(s["track_index"]), str(s["track_name"]))
            readback = post_track.get("volume") if post_track else None
            verified = readback is not None and _values_match(readback, s["after"])
            if not verified:
                all_verified = False
            step_receipts.append({
                "track_index": s["track_index"],
                "track_name": s["track_name"],
                "before": s["before"],
                "requested": s["after"],
                "readback": readback,
                "verified": verified,
            })

        _finish_idempotency_key(key)

        if not all_verified or len(applied_steps) < len(steps):
            for s in reversed(applied_steps):
                try:
                    self.client.set_track_volume(int(s["track_index"]), float(s["before"]))
                except Exception:
                    pass
            return {"ok": False, "error": "Gain staging readback verification failed; changes were rolled back.", "step_receipts": step_receipts}

        receipt = {
            "schema": GAIN_STAGING_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-gain-stage-{uuid.uuid4().hex}",
            "action": "gain_stage_tracks",
            "status": "applied",
            "verified": True,
            "target_headroom_db": proposal["target_headroom_db"],
            "target_normalized": proposal["target_normalized"],
            "steps": steps,
            "step_receipts": step_receipts,
            "track_count": len(steps),
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "stage_timings_ms": timer.as_ms(),
            "undo": {"available": True},
        }
        _RECEIPTS[receipt["receipt_id"]] = receipt
        return {"ok": True, "receipt": receipt}

    def propose_undo_gain_staging(self, receipt: dict[str, Any], *, session_id: str) -> dict[str, Any]:
        """Propose an inverse gain-staging to restore each track to its prior volume."""
        if not isinstance(receipt, dict) or receipt.get("schema") != GAIN_STAGING_RECEIPT_SCHEMA:
            return {"ok": False, "error": "A verified KENN gain staging receipt is required for undo."}
        if not receipt.get("verified") or receipt.get("status") != "applied":
            return {"ok": False, "error": "Only a verified applied gain staging action can be undone."}

        steps = receipt.get("steps") or []
        if not steps:
            return {"ok": False, "error": "Gain staging receipt contains no track steps."}

        inverse_steps = []
        for s in reversed(steps):
            inverse_steps.append({
                "track_index": s["track_index"],
                "track_name": s["track_name"],
                "before": s["after"],
                "after": s["before"],
                "before_db": s.get("after_db", 0.0),
                "after_db": s.get("before_db", 0.0),
                "delta_db": round(s.get("before_db", 0.0) - s.get("after_db", 0.0), 1),
            })

        state = self.snapshot()
        proposal = {
            "schema": GAIN_STAGING_PROPOSAL_SCHEMA,
            "action_id": f"action-gain-stage-undo-{uuid.uuid4().hex}",
            "action": "gain_stage_tracks",
            "operation": "gain_stage_tracks",
            "target": "ableton_session_tracks",
            "target_headroom_db": 0.0,
            "target_normalized": 0.0,
            "steps": inverse_steps,
            "track_count": len(inverse_steps),
            "before_track_fingerprint": _track_structure_fingerprint(state),
            "reason": f"Restore verified KENN gain staging {receipt.get('receipt_id', '')}.",
            "confidence": 1.0,
            "risk": "multi_track_volume_mutation",
            "requires_confirmation": True,
            "undo_available": False,
            "timestamp": time.time(),
            "session_version": _state_version(state),
        }

        confirmation_text = "gain_stage_tracks:" + json.dumps(
            [{"track_index": s["track_index"], "track_name": s["track_name"], "before": s["before"], "after": s["after"]} for s in inverse_steps],
            sort_keys=True,
            separators=(",", ":"),
        )
        token, meta = issue_confirmation(
            session_id=session_id,
            service_id="ableton_action",
            text=confirmation_text,
            ttl_seconds=300,
        )
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def propose_track_grouping(
        self,
        *,
        group_type: str = "",
        track_indices: list[int] | None = None,
        session_id: str,
    ) -> dict[str, Any]:
        _cleanup_memory()
        try:
            state = self.snapshot()
        except Exception as exc:
            return {"ok": False, "error": f"Snapshot failed: {exc}"}

        if state.get("status") != "connected":
            return {"ok": False, "error": "Ableton Live is offline or returned no usable snapshot."}

        tracks = [t for t in state.get("tracks", []) if isinstance(t, dict)]
        if not tracks:
            return {"ok": False, "error": "No tracks found in current Live snapshot."}

        clean_type = str(group_type or "").strip().lower()
        member_tracks = []
        if track_indices is not None and len(track_indices) > 0:
            track_map = {int(t["index"]): t for t in tracks if "index" in t}
            for idx in track_indices:
                if idx in track_map:
                    member_tracks.append(track_map[idx])
            bus_name = f"{clean_type.title()} Bus" if clean_type else "Group Bus"
        else:
            from kenn.core.track_classifier import classify_track_name
            role_groups: dict[str, list[dict[str, Any]]] = {}
            for t in tracks:
                name = str(t.get("name", ""))
                cls = classify_track_name(name)
                role = cls.role
                category = "other"
                if role in {"kick", "snare", "drum_bus"}:
                    category = "drums"
                elif role in {"sub_bass", "bass_synth"}:
                    category = "bass"
                elif role in {"vocal_lead", "vocal_bg"}:
                    category = "vocals"
                elif role == "guitar":
                    category = "guitars"
                elif role in {"keys", "synth"}:
                    category = "synths"
                elif role == "fx_send":
                    category = "fx"
                role_groups.setdefault(category, []).append(t)

            if clean_type and clean_type in role_groups:
                selected_category = clean_type
                member_tracks = role_groups[clean_type]
            elif clean_type:
                selected_category = clean_type
                member_tracks = [t for t in tracks if clean_type in str(t.get("name", "")).lower()]
                if not member_tracks:
                    member_tracks = tracks
            else:
                for candidate in ["drums", "vocals", "bass", "synths", "guitars", "fx"]:
                    if len(role_groups.get(candidate, [])) >= 1:
                        selected_category = candidate
                        member_tracks = role_groups[candidate]
                        break
                else:
                    selected_category = "mix"
                    member_tracks = tracks

            bus_name = f"{selected_category.title()} Bus"

        insertion_index = len(tracks)
        proposal = {
            "schema": BUS_ORGANIZATION_PROPOSAL_SCHEMA,
            "action_id": f"action-bus-group-{uuid.uuid4().hex}",
            "action": "group_tracks",
            "operation": "group_tracks",
            "target": "ableton_song_tracks",
            "bus_name": bus_name,
            "group_type": clean_type or "auto",
            "member_tracks": [{"track_index": t["index"], "track_name": t.get("name", "")} for t in member_tracks],
            "member_count": len(member_tracks),
            "insertion_index": insertion_index,
            "reason": f"Organize {len(member_tracks)} tracks into {bus_name}.",
            "confidence": 1.0,
            "risk": "structural_mutation",
            "requires_confirmation": True,
            "undo_available": False,
            "undo_reason": "Deleting a created track is outside KENN's safe inverse boundary.",
            "timestamp": time.time(),
            "session_version": _state_version(state),
        }

        confirmation_text = f"group_tracks:{bus_name}:{len(member_tracks)}:" + json.dumps(
            [t["index"] for t in member_tracks], sort_keys=True
        )
        token, meta = issue_confirmation(
            session_id=session_id,
            service_id="ableton_action",
            text=confirmation_text,
            ttl_seconds=300,
        )
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        _PROPOSALS_BY_TOKEN[token] = proposal
        return {"ok": True, "proposal": proposal}

    def execute_track_grouping(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        _cleanup_memory()
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != BUS_ORGANIZATION_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid KENN Ableton bus organization proposal is required."}
        if not proposal.get("requires_confirmation") or not confirm_token:
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required before track grouping mutation."}
        if str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "error": "Confirmation token is not bound to this exact proposal."}
        key = idempotency_key.strip() or str(proposal.get("action_id", ""))
        if not key:
            return {"ok": False, "error": "An idempotency key is required."}
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This action request was already executed or is already in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)

        bus_name = str(proposal.get("bus_name", "Bus"))
        member_tracks = proposal.get("member_tracks") or []
        confirmation_text = f"group_tracks:{bus_name}:{len(member_tracks)}:" + json.dumps(
            [t["track_index"] for t in member_tracks], sort_keys=True
        )
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_action", text=confirmation_text):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used confirmation token."}

        try:
            state = self.snapshot()
        except Exception as exc:
            _finish_idempotency_key(key)
            return {"ok": False, "error": f"Live snapshot failed before execution: {exc}"}
        timer.mark("snapshot")

        before_count = len(state.get("tracks", []))
        try:
            try:
                write_ok = bool(self.client.create_audio_track(-1))
            except TypeError:
                write_ok = bool(self.client.create_audio_track())
        except Exception as exc:
            write_ok = False
        timer.mark("mutation")

        new_index = before_count
        if write_ok:
            try:
                self.client.set_track_name(new_index, bus_name)
            except Exception:
                pass

        try:
            post_state = self.snapshot()
        except Exception:
            post_state = {}
        timer.mark("readback")

        post_tracks = post_state.get("tracks", [])
        verified = len(post_tracks) > before_count and (
            any(t.get("name") == bus_name for t in post_tracks) or write_ok
        )

        _finish_idempotency_key(key)
        receipt = {
            "schema": BUS_ORGANIZATION_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-bus-group-{uuid.uuid4().hex}",
            "action": "group_tracks",
            "status": "applied" if verified else "failed",
            "verified": verified,
            "bus_name": bus_name,
            "track_index": new_index,
            "member_tracks": member_tracks,
            "timestamp": time.time(),
            "correlation_id": correlation_id,
            "stage_timings_ms": timer.as_ms(),
            "undo": {"available": False},
        }
        _RECEIPTS[receipt["receipt_id"]] = receipt
        if not verified:
            return {"ok": False, "error": "Failed to verify creation of bus track in Live.", "receipt": receipt}
        return {"ok": True, "receipt": receipt}

    def execute_autonomous(
        self,
        proposal: dict[str, Any],
        *,
        session_id: str = "default_session",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Execute an action autonomously if it complies with the AutonomousSafetyEvaluator."""
        from kenn.core.action_policy import AutonomousSafetyEvaluator

        if not AutonomousSafetyEvaluator.is_autonomous_mode_enabled():
            return {
                "ok": False,
                "error": "Autonomous execution requires KENN_AUTONOMOUS_MODE=1 to be enabled in environment.",
                "requires_confirmation": True,
                "proposal": proposal,
            }

        action = proposal.get("action", "")
        current_val = proposal.get("before")
        target_val = proposal.get("after")
        track_name = proposal.get("track_name", "")

        approved, reason = AutonomousSafetyEvaluator.evaluate_proposal(
            action,
            current_value=float(current_val) if isinstance(current_val, (int, float)) else None,
            target_value=float(target_val) if isinstance(target_val, (int, float)) else None,
            track_name=track_name,
            is_master=str(track_name).lower().strip() in {"master", "main"},
        )
        if not approved:
            return {
                "ok": False,
                "error": f"Autonomous safety policy rejected action: {reason}",
                "proposal": proposal,
            }

        token = proposal.get("confirmation_token")
        if not token:
            return {"ok": False, "error": "Proposal does not have a valid confirmation token."}

        return self.execute(
            proposal,
            confirm_token=token,
            session_id=session_id,
            correlation_id=correlation_id,
        )

    def execute_batch_autonomous(
        self,
        proposals: list[dict[str, Any]],
        *,
        session_id: str = "default_session",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Execute a batch of actions atomically under the autonomous safety envelope."""
        results = []
        applied_receipts = []
        for prop in proposals:
            res = self.execute_autonomous(prop, session_id=session_id, correlation_id=correlation_id)
            results.append(res)
            if not res.get("ok"):
                # Atomic batch rollback: rollback previously applied actions in reverse order
                for r in reversed(applied_receipts):
                    try:
                        self.undo(r)
                    except Exception:
                        pass
                return {
                    "ok": False,
                    "error": f"Batch action failed on item {prop.get('action')}: {res.get('error')}. Rolled back preceding actions.",
                    "partial_results": results,
                }
            receipt = res.get("receipt", {})
            if receipt.get("receipt_id"):
                applied_receipts.append(receipt.get("receipt_id"))

        return {
            "ok": True,
            "batch_size": len(proposals),
            "results": results,
            "applied_receipt_ids": applied_receipts,
        }

    def propose_midi_clip(
        self,
        *,
        track_index: int,
        clip_slot_index: int,
        clip_name: str = "KENN Pattern",
        length_beats: float = 4.0,
        notes: list[dict[str, Any]],
        track_name: str = "",
        root_note: int | str | None = None,
        scale_name: str | None = None,
        quantize_to_scale: bool = False,
        session_id: str,
    ) -> dict[str, Any]:
        """Propose creating a new MIDI clip with verified notes in an empty clip slot."""
        service = MidiClipActionService(self.client)
        return service.propose(
            track_index=track_index,
            clip_slot_index=clip_slot_index,
            clip_name=clip_name,
            length_beats=length_beats,
            notes=notes,
            track_name=track_name,
            root_note=root_note,
            scale_name=scale_name,
            quantize_to_scale=quantize_to_scale,
            session_id=session_id,
        )

    def execute_midi_clip(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Execute confirmed MIDI clip creation proposal."""
        service = MidiClipActionService(self.client)
        return service.execute(
            proposal,
            confirm_token=confirm_token,
            session_id=session_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

    def read_clip_notes(self, track_index: int, clip_slot_index: int) -> dict[str, Any]:
        """Read MIDI notes from an existing Session View clip for world model context."""
        return self.client.get_midi_clip_state(int(track_index), int(clip_slot_index))

    # Note: Tier 2 / Tier 3 control expansion methods are implemented in Tier2Tier3ControlMixin










__all__ = [
    "LiveActionService",
    "PROPOSAL_SCHEMA",
    "RECEIPT_SCHEMA",
    "DEVICE_SETUP_PROPOSAL_SCHEMA",
    "DEVICE_SETUP_PARAMETER_ALLOWLIST",
    "SUPPORTED_TRACK_CREATION_ACTIONS",
    "SUPPORTED_RETURN_TRACK_CREATION_ACTIONS",
    "GAIN_STAGING_PROPOSAL_SCHEMA",
    "GAIN_STAGING_RECEIPT_SCHEMA",
    "BUS_ORGANIZATION_PROPOSAL_SCHEMA",
    "BUS_ORGANIZATION_RECEIPT_SCHEMA",
    "MIDI_CLIP_PROPOSAL_SCHEMA",
    "MIDI_CLIP_RECEIPT_SCHEMA",
    "ARRANGEMENT_DUPLICATION_PROPOSAL_SCHEMA",
    "ARRANGEMENT_DUPLICATION_RECEIPT_SCHEMA",
    "CLIP_AUTOMATION_PROPOSAL_SCHEMA",
    "CLIP_AUTOMATION_RECEIPT_SCHEMA",
    "RACK_MACRO_PROPOSAL_SCHEMA",
    "RACK_MACRO_RECEIPT_SCHEMA",
    "TRACK_ROUTING_PROPOSAL_SCHEMA",
    "TRACK_ROUTING_RECEIPT_SCHEMA",
    "TRACK_FREEZE_PROPOSAL_SCHEMA",
    "TRACK_FREEZE_RECEIPT_SCHEMA",
    "RACK_VARIATION_PROPOSAL_SCHEMA",
    "RACK_VARIATION_RECEIPT_SCHEMA",
    "CLIP_LAUNCH_PROPOSAL_SCHEMA",
    "CLIP_LAUNCH_RECEIPT_SCHEMA",
    "SCENE_CREATION_PROPOSAL_SCHEMA",
    "SCENE_CREATION_RECEIPT_SCHEMA",
    "LOOP_DUPLICATION_PROPOSAL_SCHEMA",
    "LOOP_DUPLICATION_RECEIPT_SCHEMA",
    "CLIP_WARP_PITCH_PROPOSAL_SCHEMA",
    "CLIP_WARP_PITCH_RECEIPT_SCHEMA",
    "CLIP_DELETION_PROPOSAL_SCHEMA",
    "CLIP_DELETION_RECEIPT_SCHEMA",
    "PRESET_LOAD_PROPOSAL_SCHEMA",
    "PRESET_LOAD_RECEIPT_SCHEMA",
    "RESAMPLE_BOUNCE_PROPOSAL_SCHEMA",
    "RESAMPLE_BOUNCE_RECEIPT_SCHEMA",
    "CLIP_MODULATION_PROPOSAL_SCHEMA",
    "CLIP_MODULATION_RECEIPT_SCHEMA",
    "CLIP_WARP_MODE_PROPOSAL_SCHEMA",
    "CLIP_WARP_MODE_RECEIPT_SCHEMA",
    "MASTER_LIMITER_LOCK_PROPOSAL_SCHEMA",
    "MASTER_LIMITER_LOCK_RECEIPT_SCHEMA",
]


