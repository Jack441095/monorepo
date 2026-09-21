"""Confirmation-gated MIDI clip creation for Ableton Live.

This is intentionally a small, append-only first capability.  It accepts a
validated note list, targets one exact empty Session View slot, and verifies
the resulting clip by reading the clip and notes back through AbletonOSC.
Existing clips are never replaced by this service.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from threading import Lock
from typing import Any

from kenn.ableton_osc_bridge import AbletonOSCClient, live_client
from kenn.core.audiogen_artifacts import safe_generation_context
from kenn.core.confirmation import consume_confirmation, issue_confirmation
from kenn.core.idempotency_bounds import prune_if_needed
from kenn.core.receipt_contract import StageTimer, classify_retry_safety, resolve_correlation_id


CREATE_PROPOSAL_SCHEMA = "kenn.ableton_midi_clip_proposal.v1"
PROPOSAL_SCHEMA = CREATE_PROPOSAL_SCHEMA
UPDATE_PROPOSAL_SCHEMA = "kenn.ableton_midi_clip_update_proposal.v1"
REMOVE_PROPOSAL_SCHEMA = "kenn.ableton_midi_clip_removal_proposal.v1"
PROPOSAL_SCHEMA = CREATE_PROPOSAL_SCHEMA
UNDO_PROPOSAL_SCHEMA = REMOVE_PROPOSAL_SCHEMA
RECEIPT_SCHEMA = "kenn.ableton_midi_clip_receipt.v1"
MAX_NOTES = 4096
MAX_CLIP_LENGTH = 4096.0
_SHA256_PREFIX = "sha256:"
_USED_IDEMPOTENCY_KEYS: set[str] = set()
_IN_FLIGHT_IDEMPOTENCY_KEYS: set[str] = set()
_ACTION_LOCK = Lock()

NOTE_NAME_TO_INT: dict[str, int] = {
    "C": 0, "C#": 1, "DB": 1,
    "D": 2, "D#": 3, "EB": 3,
    "E": 4,
    "F": 5, "F#": 6, "GB": 6,
    "G": 7, "G#": 8, "AB": 8,
    "A": 9, "A#": 10, "BB": 10,
    "B": 11,
}

INT_TO_NOTE_NAME: list[str] = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

SCALE_INTERVALS: dict[str, list[int]] = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "ionian": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "natural minor": [0, 2, 3, 5, 7, 8, 10],
    "aeolian": [0, 2, 3, 5, 7, 8, 10],
    "harmonic minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic minor": [0, 2, 3, 5, 7, 9, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
    "major pentatonic": [0, 2, 4, 7, 9],
    "minor pentatonic": [0, 3, 5, 7, 10],
    "blues": [0, 3, 5, 6, 7, 10],
    "chromatic": list(range(12)),
}


def parse_root_note(root: Any) -> int:
    """Resolve note representation (int 0..11 or str 'C', 'F#') to pitch class 0..11."""
    if isinstance(root, (int, float)):
        return int(root) % 12
    if isinstance(root, str):
        cleaned = root.strip().upper()
        if cleaned in NOTE_NAME_TO_INT:
            return NOTE_NAME_TO_INT[cleaned]
    return 0


def quantize_pitch_to_scale(pitch: int, root_note: int | str = 0, scale_name: str = "minor") -> int:
    """Snap a MIDI pitch (0..127) to the nearest pitch class in the specified musical scale."""
    pitch = max(0, min(127, int(pitch)))
    root = parse_root_note(root_note)
    scale_key = str(scale_name).strip().lower()
    intervals = SCALE_INTERVALS.get(scale_key, SCALE_INTERVALS["minor"])

    scale_pitch_classes = set((root + iv) % 12 for iv in intervals)
    current_pc = pitch % 12

    if current_pc in scale_pitch_classes:
        return pitch

    best_offset = 0
    min_dist = 99
    for dist in [-1, 1, -2, 2, -3, 3]:
        candidate_pc = (current_pc + dist) % 12
        if candidate_pc in scale_pitch_classes:
            if abs(dist) < min_dist:
                min_dist = abs(dist)
                best_offset = dist
                break

    snapped = pitch + best_offset
    return max(0, min(127, snapped))


def _text(value: Any, limit: int = 512) -> str:
    return str(value or "").strip()[:limit]


def _state_version(state: dict[str, Any], track: dict[str, Any]) -> str:
    stable = {
        "status": state.get("status"),
        "tempo": state.get("tempo"),
        "track": {
            key: track.get(key)
            for key in ("index", "name", "devices")
        },
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _find_track(state: dict[str, Any], track_index: int, track_name: str) -> tuple[dict[str, Any] | None, str | None]:
    tracks = [item for item in state.get("tracks", []) if isinstance(item, dict)]
    matches = [item for item in tracks if int(item.get("index", -1)) == track_index]
    if len(matches) != 1:
        return None, "track index is not present exactly once in the current Live snapshot"
    track = matches[0]
    if track_name and str(track.get("name", "")) != track_name:
        return None, "track name changed since the proposal was created"
    return track, None


def _canonical_notes(notes: Any, *, allow_empty: bool = False) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not isinstance(notes, list) or (not allow_empty and not notes):
        return None, "notes must be a non-empty list"
    if len(notes) > MAX_NOTES:
        return None, f"notes may contain at most {MAX_NOTES} entries"
    normalized: list[dict[str, Any]] = []
    for offset, note in enumerate(notes):
        if not isinstance(note, dict):
            return None, f"note {offset} must be an object"
        try:
            pitch = int(note["pitch"])
            start_time = float(note["start_time"])
            duration = float(note["duration"])
            velocity = int(note["velocity"])
            mute = bool(note.get("mute", False))
        except (KeyError, TypeError, ValueError):
            return None, f"note {offset} has invalid fields"
        if not 0 <= pitch <= 127:
            return None, f"note {offset} pitch must be between 0 and 127"
        if not math.isfinite(start_time) or start_time < 0:
            return None, f"note {offset} start_time must be finite and non-negative"
        if not math.isfinite(duration) or duration <= 0:
            return None, f"note {offset} duration must be finite and greater than zero"
        if not 1 <= velocity <= 127:
            return None, f"note {offset} velocity must be between 1 and 127"
        normalized.append({
            "pitch": pitch,
            "start_time": start_time,
            "duration": duration,
            "velocity": velocity,
            "mute": mute,
        })
    normalized.sort(key=lambda item: (
        item["pitch"], item["start_time"], item["duration"], item["velocity"], item["mute"]
    ))
    return normalized, None


def _notes_equal(expected: list[dict[str, Any]], actual: Any) -> bool:
    normalized, error = _canonical_notes(actual, allow_empty=True)
    if error or normalized is None or len(normalized) != len(expected):
        return False
    for left, right in zip(expected, normalized):
        if left["pitch"] != right["pitch"] or left["velocity"] != right["velocity"] or left["mute"] != right["mute"]:
            return False
        if not math.isclose(left["start_time"], right["start_time"], rel_tol=0.0, abs_tol=1e-5):
            return False
        if not math.isclose(left["duration"], right["duration"], rel_tol=0.0, abs_tol=1e-5):
            return False
    return True


def _proposal_text(proposal: dict[str, Any]) -> str:
    fields = (
        "action", "track_index", "track_name", "clip_slot_index", "length",
        "notes_fingerprint", "before_notes_fingerprint", "after_notes_fingerprint",
        "source_artifact_sha256", "source_receipt_id",
    )
    return "|".join([*(str(proposal.get(key, "")) for key in fields), _context_json(proposal.get("source_context"))])


def _context_json(context: Any) -> str:
    safe = safe_generation_context(context) or {}
    return json.dumps(safe, sort_keys=True, separators=(",", ":"))


def _fingerprint_notes(notes: list[dict[str, Any]]) -> str:
    encoded = json.dumps(notes, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _valid_digest(value: str) -> bool:
    clean = _text(value, 128).lower()
    return clean.startswith(_SHA256_PREFIX) and len(clean) == len(_SHA256_PREFIX) + 64 and all(
        char in "0123456789abcdef" for char in clean[len(_SHA256_PREFIX):]
    )


def _finish_idempotency(key: str) -> None:
    with _ACTION_LOCK:
        prune_if_needed(_USED_IDEMPOTENCY_KEYS)
        _USED_IDEMPOTENCY_KEYS.add(key)
        _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)


def _reserve_idempotency(key: str) -> bool:
    with _ACTION_LOCK:
        if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
            return False
        _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        return True


class MidiClipActionService:
    """Create/delete one exact MIDI clip with fresh state and readback gates."""

    def __init__(self, client: AbletonOSCClient | Any = None):
        self.client = client or live_client

    def _snapshot(self) -> dict[str, Any]:
        if hasattr(self.client, "query_session_topology"):
            return self.client.query_session_topology()
        return self.client.query_session_state(include_mixer=False)

    def propose_create(
        self,
        *,
        track_index: int,
        clip_slot_index: int,
        track_name: str = "",
        length: float = 4.0,
        length_beats: float | None = None,
        notes: Any = None,
        session_id: str = "",
        clip_name: str = "KENN Pattern",
        root_note: int | str | None = None,
        scale_name: str | None = None,
        quantize_to_scale: bool = False,
        source_artifact_sha256: str = "",
        source_artifact_id: str = "",
        source_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_track_name = _text(track_name, 256)
        if not clean_track_name:
            return {"ok": False, "error": "track_name is required for an exact MIDI clip target"}
        if length_beats is not None:
            length = float(length_beats)
        try:
            track_index = int(track_index)
            clip_slot_index = int(clip_slot_index)
            length = float(length)
        except (TypeError, ValueError):
            return {"ok": False, "error": "track, clip-slot, and length must be numeric"}
        if min(track_index, clip_slot_index) < 0:
            return {"ok": False, "error": "track and clip-slot indices must be non-negative"}
        if not math.isfinite(length) or length <= 0 or length > MAX_CLIP_LENGTH:
            return {"ok": False, "error": f"clip length must be between 0 and {MAX_CLIP_LENGTH} beats"}

        if quantize_to_scale and scale_name and isinstance(notes, list):
            effective_root = parse_root_note(root_note if root_note is not None else 0)
            quantized = []
            for n in notes:
                if isinstance(n, dict) and "pitch" in n:
                    q_pitch = quantize_pitch_to_scale(n["pitch"], root_note=effective_root, scale_name=scale_name)
                    quantized.append({**n, "pitch": q_pitch})
                else:
                    quantized.append(n)
            notes = quantized

        canonical, error = _canonical_notes(notes)
        if error or canonical is None:
            return {"ok": False, "error": error or "invalid MIDI notes"}
        for offset, note in enumerate(canonical):
            if note["start_time"] + note["duration"] > length + 1e-9:
                return {
                    "ok": False,
                    "error": f"note {offset} extends beyond the {length:g}-beat clip length",
                }
        digest = _text(source_artifact_sha256, 128).lower()
        if digest and not _valid_digest(digest):
            return {"ok": False, "error": "source_artifact_sha256 must be sha256: plus 64 hexadecimal characters"}
        clean_context = safe_generation_context(source_context)
        if source_context and clean_context is None:
            return {"ok": False, "error": "source_context is not a valid KENN AudioGen Live context."}
        try:
            state = self._snapshot()
        except Exception as exc:
            return {"ok": False, "error": f"Live snapshot failed: {exc}"}
        if state.get("status") != "connected":
            return {"ok": False, "error": "Ableton Live is offline or returned no usable topology."}

        clean_track_name = _text(track_name, 256)
        if not clean_track_name:
            tracks = [item for item in state.get("tracks", []) if isinstance(item, dict)]
            matches = [item for item in tracks if int(item.get("index", -1)) == track_index]
            if matches:
                clean_track_name = str(matches[0].get("name", ""))

        track, error = _find_track(state, track_index, clean_track_name)
        if error or track is None:
            return {"ok": False, "error": error or "Target Live track is unavailable."}
        if track.get("has_midi_input") is False:
            return {"ok": False, "error": "The exact Live target is not a MIDI-capable track."}
        if hasattr(self.client, "get_track_has_midi_input"):
            try:
                midi_capable = self.client.get_track_has_midi_input(track_index)
            except Exception as exc:
                return {"ok": False, "error": f"MIDI track capability read failed: {exc}"}
            if midi_capable is False:
                return {"ok": False, "error": "The exact Live target is not a MIDI-capable track."}
        try:
            clip_state = self.client.get_midi_clip_state(track_index, clip_slot_index)
        except Exception as exc:
            return {"ok": False, "error": f"MIDI clip-slot inspection failed: {exc}"}
        if not clip_state.get("success"):
            return {"ok": False, "error": clip_state.get("error", "MIDI clip-slot inspection failed")}
        if clip_state.get("has_clip"):
            return {"ok": False, "error": "Target clip slot already contains a clip; replacement is not enabled."}
        proposal = {
            "schema": CREATE_PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "create_midi_clip",
            "operation": "create_midi_clip",
            "target": "ableton_midi_clip_slot",
            "track_index": track_index,
            "track_name": str(track.get("name", "")),
            "clip_slot_index": clip_slot_index,
            "clip_name": _text(clip_name or "KENN Pattern", 128),
            "length": length,
            "notes": canonical,
            "note_count": len(canonical),
            "notes_fingerprint": _fingerprint_notes(canonical),
            "source_artifact_sha256": digest,
            "source_artifact_id": _text(source_artifact_id, 256),
            "source_context": clean_context,
            "before": {"has_clip": False},
            "after": {"has_clip": True, "is_midi_clip": True, "length": length, "note_count": len(canonical)},
            "reason": f"Explicit request to create a MIDI clip on '{track.get('name', '')}', slot {clip_slot_index}.",
            "confidence": 1.0,
            "risk": "local_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state, track),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_midi_clip", text=_proposal_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        return {"ok": True, "proposal": proposal}

    def propose_update(
        self,
        *,
        track_index: int,
        track_name: str,
        clip_slot_index: int,
        notes: Any,
        session_id: str,
        source_receipt_id: str = "",
        source_artifact_sha256: str = "",
        source_artifact_id: str = "",
        source_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare an exact, confirmation-bound replacement of MIDI notes.

        Live exposes note removal and insertion rather than an atomic note-set
        operation. The proposal therefore binds the complete current clip
        note set and the clip length, then execution verifies the clear and
        replacement readbacks before returning success. Existing clips are
        never replaced implicitly and an empty replacement is allowed only
        through this explicit, typed operation.
        """
        clean_track_name = _text(track_name, 256)
        if not clean_track_name:
            return {"ok": False, "error": "track_name is required for an exact MIDI clip target"}
        try:
            track_index = int(track_index)
            clip_slot_index = int(clip_slot_index)
        except (TypeError, ValueError):
            return {"ok": False, "error": "track and clip-slot indices must be numeric"}
        if min(track_index, clip_slot_index) < 0:
            return {"ok": False, "error": "track and clip-slot indices must be non-negative"}
        canonical_new, new_error = _canonical_notes(notes, allow_empty=True)
        if new_error or canonical_new is None:
            return {"ok": False, "error": new_error or "invalid replacement MIDI notes"}
        digest = _text(source_artifact_sha256, 128).lower()
        if digest and not _valid_digest(digest):
            return {"ok": False, "error": "source_artifact_sha256 must be sha256: plus 64 hexadecimal characters"}
        clean_context = safe_generation_context(source_context)
        if source_context and clean_context is None:
            return {"ok": False, "error": "source_context is not a valid KENN AudioGen Live context."}
        try:
            state = self._snapshot()
        except Exception as exc:
            return {"ok": False, "error": f"Live snapshot failed: {exc}"}
        if state.get("status") != "connected":
            return {"ok": False, "error": "Ableton Live is offline or returned no usable topology."}
        track, error = _find_track(state, track_index, clean_track_name)
        if error or track is None:
            return {"ok": False, "error": error or "Target Live track is unavailable."}
        try:
            current = self.client.get_midi_clip_state(track_index, clip_slot_index)
        except Exception as exc:
            return {"ok": False, "error": f"MIDI clip inspection failed: {exc}"}
        if not current.get("success"):
            return {"ok": False, "error": current.get("error", "MIDI clip inspection failed")}
        if not current.get("has_clip") or not current.get("is_midi_clip"):
            return {"ok": False, "error": "The exact target must contain an existing MIDI clip."}
        canonical_before, before_error = _canonical_notes(current.get("notes"), allow_empty=True)
        if before_error or canonical_before is None:
            return {"ok": False, "error": before_error or "Current MIDI notes are not safely readable."}
        try:
            length = float(current.get("length"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "Current MIDI clip length is invalid."}
        proposal = {
            "schema": UPDATE_PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "update_midi_clip",
            "operation": "replace_midi_notes",
            "target": "ableton_midi_clip_slot",
            "track_index": track_index,
            "track_name": str(track.get("name", "")),
            "clip_slot_index": clip_slot_index,
            "length": length,
            "before_notes": canonical_before,
            "new_notes": canonical_new,
            "before_notes_fingerprint": _fingerprint_notes(canonical_before),
            "after_notes_fingerprint": _fingerprint_notes(canonical_new),
            "source_receipt_id": _text(source_receipt_id, 256),
            "source_artifact_sha256": digest,
            "source_artifact_id": _text(source_artifact_id, 256),
            "source_context": clean_context,
            "before": {
                "has_clip": True,
                "is_midi_clip": True,
                "length": length,
                "note_count": len(canonical_before),
                "notes_fingerprint": _fingerprint_notes(canonical_before),
            },
            "after": {
                "has_clip": True,
                "is_midi_clip": True,
                "length": length,
                "note_count": len(canonical_new),
                "notes_fingerprint": _fingerprint_notes(canonical_new),
            },
            "reason": f"Explicit request to revise MIDI notes on '{track.get('name', '')}', slot {clip_slot_index}.",
            "confidence": 1.0,
            "risk": "clip_content_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": _state_version(state, track),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(
            session_id=session_id,
            service_id="ableton_midi_clip",
            text=_proposal_text(proposal),
        )
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        return {"ok": True, "proposal": proposal}

    def execute_update(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Replace one exact MIDI clip's notes and verify the final state."""
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != UPDATE_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid KENN MIDI clip update proposal is required."}
        if not proposal.get("requires_confirmation") or str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "error": "Explicit confirmation is required for this exact MIDI clip update."}
        key = _text(idempotency_key or proposal.get("action_id"), 256)
        if not key or not _reserve_idempotency(key):
            return {"ok": False, "error": "This MIDI clip update was already executed or is already in progress."}
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_midi_clip", text=_proposal_text(proposal)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used MIDI clip update confirmation token."}
        try:
            state = self._snapshot()
            if state.get("status") != "connected":
                return self._failed(proposal, key, "Ableton Live became unavailable before MIDI clip update.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            track_index = int(proposal["track_index"])
            clip_slot_index = int(proposal["clip_slot_index"])
            track, error = _find_track(state, track_index, str(proposal.get("track_name", "")))
            if error or track is None:
                return self._failed(proposal, key, error or "Target Live track is unavailable.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            current = self.client.get_midi_clip_state(track_index, clip_slot_index)
            timer.mark("snapshot")
            if (
                not current.get("success")
                or not current.get("has_clip")
                or not current.get("is_midi_clip")
                or not _notes_equal(proposal.get("before_notes", []), current.get("notes"))
                or not math.isclose(float(current.get("length", 0.0)), float(proposal.get("length", 0.0)), rel_tol=0.0, abs_tol=1e-4)
            ):
                return self._failed(proposal, key, "MIDI clip changed since the proposal was created; no note replacement was sent.", readback=current, correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            new_notes, note_error = _canonical_notes(proposal.get("new_notes"), allow_empty=True)
            if note_error or new_notes is None:
                return self._failed(proposal, key, note_error or "Proposal contains invalid replacement notes.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())

            try:
                remove_ok = bool(self.client.remove_all_midi_notes(track_index, clip_slot_index))
                remove_error = "" if remove_ok else "AbletonOSC did not accept MIDI note removal."
            except Exception as exc:
                remove_ok = False
                remove_error = f"MIDI note removal acknowledgement was lost: {type(exc).__name__}: {exc}"
            if not remove_ok:
                uncertain = self.client.get_midi_clip_state(track_index, clip_slot_index)
                timer.mark("readback")
                return self._failed(proposal, key, remove_error, readback=uncertain, retry_safe="requires_inspection", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            cleared = self.client.get_midi_clip_state(track_index, clip_slot_index)
            if not cleared.get("success") or not cleared.get("has_clip") or not cleared.get("is_midi_clip") or cleared.get("notes"):
                timer.mark("readback")
                return self._failed(proposal, key, "MIDI note removal did not produce an authoritative empty-note readback; inspect before retrying.", readback=cleared, retry_safe="requires_inspection", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())

            write_acknowledgement = "confirmed"
            add_error = ""
            if new_notes:
                try:
                    add_ok = bool(self.client.add_midi_notes(track_index, clip_slot_index, new_notes))
                    add_error = "" if add_ok else "AbletonOSC did not accept replacement MIDI notes."
                except Exception as exc:
                    add_ok = False
                    add_error = f"Replacement MIDI note acknowledgement was lost: {type(exc).__name__}: {exc}"
                if not add_ok:
                    uncertain = self.client.get_midi_clip_state(track_index, clip_slot_index)
                    timer.mark("readback")
                    exact = bool(uncertain.get("success") and _notes_equal(new_notes, uncertain.get("notes")))
                    if not exact:
                        return self._failed(proposal, key, add_error, readback=uncertain, retry_safe="requires_inspection", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
                    write_acknowledgement = "unacknowledged_write_reconciled"
            timer.mark("write")
            if write_acknowledgement == "confirmed":
                time.sleep(0.05)
                readback = self.client.get_midi_clip_state(track_index, clip_slot_index)
            else:
                readback = uncertain
            timer.mark("readback")
            verified = bool(
                readback.get("success")
                and readback.get("has_clip")
                and readback.get("is_midi_clip")
                and math.isclose(float(readback.get("length", 0.0)), float(proposal.get("length", 0.0)), rel_tol=0.0, abs_tol=1e-4)
                and _notes_equal(new_notes, readback.get("notes"))
            )
            _finish_idempotency(key)
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "receipt_id": f"receipt-{uuid.uuid4().hex}",
                "action_id": proposal.get("action_id"),
                "action": "update_midi_clip",
                "idempotency_key": key,
                "status": "applied" if verified else "failed_verification",
                "verified": verified,
                "timestamp": time.time(),
                "target": {"track_index": track_index, "track_name": str(proposal.get("track_name", "")), "clip_slot_index": clip_slot_index},
                "before": proposal.get("before"),
                "requested": proposal.get("after"),
                "readback": readback,
                "before_notes": proposal.get("before_notes", []),
                "notes": new_notes,
                "source_receipt_id": proposal.get("source_receipt_id", ""),
                "source_artifact_sha256": proposal.get("source_artifact_sha256", ""),
                "source_artifact_id": proposal.get("source_artifact_id", ""),
                "source_context": proposal.get("source_context"),
                "undo_payload": {
                    "action": "update_midi_clip",
                    "track_index": track_index,
                    "track_name": str(proposal.get("track_name", "")),
                    "clip_slot_index": clip_slot_index,
                    "expected_length": float(proposal.get("length", 0.0)),
                    "expected_notes": new_notes,
                    "restore_notes": proposal.get("before_notes", []),
                    "source_receipt_id": "pending",
                },
                "write_acknowledgement": write_acknowledgement,
                "correlation_id": correlation_id,
                "retry_safe": classify_retry_safety(verified=verified, status="applied" if verified else "failed_verification"),
                "stage_timings_ms": timer.as_ms(),
            }
            receipt["undo_payload"]["source_receipt_id"] = receipt["receipt_id"]
            return {"ok": verified, "error": None if verified else "MIDI clip update was sent but readback verification failed.", "receipt": receipt}
        except Exception as exc:
            return self._failed(proposal, key, f"MIDI clip update failed: {exc}", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())

    def _failed(
        self,
        proposal: dict[str, Any],
        key: str,
        error: str,
        *,
        readback: Any = None,
        retry_safe: str = "unsafe",
        correlation_id: str = "",
        stage_timings_ms: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        _finish_idempotency(key)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "receipt_id": f"receipt-{uuid.uuid4().hex}",
            "action_id": proposal.get("action_id"),
            "action": proposal.get("action"),
            "idempotency_key": key,
            "status": "failed",
            "verified": False,
            "timestamp": time.time(),
            "target": {
                "track_index": proposal.get("track_index"),
                "track_name": proposal.get("track_name", ""),
                "clip_slot_index": proposal.get("clip_slot_index"),
            },
            "before": proposal.get("before"),
            "requested": proposal.get("after"),
            "readback": readback,
            "error": error,
            "source_artifact_sha256": proposal.get("source_artifact_sha256", ""),
            "source_artifact_id": proposal.get("source_artifact_id", ""),
            "source_context": proposal.get("source_context"),
            "retry_safe": retry_safe,
            "correlation_id": resolve_correlation_id(correlation_id or proposal.get("correlation_id")),
            "stage_timings_ms": stage_timings_ms or {},
        }
        return {"ok": False, "error": error, "receipt": receipt}

    def execute_create(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != CREATE_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid KENN MIDI clip proposal is required."}
        if not proposal.get("requires_confirmation") or str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "error": "Explicit confirmation is required for this exact MIDI clip proposal."}
        key = _text(idempotency_key or proposal.get("action_id"), 256)
        if not key or not _reserve_idempotency(key):
            return {"ok": False, "error": "This MIDI clip request was already executed or is already in progress."}
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_midi_clip", text=_proposal_text(proposal)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used MIDI clip confirmation token."}
        try:
            state = self._snapshot()
            if state.get("status") != "connected":
                return self._failed(proposal, key, "Ableton Live became unavailable before MIDI clip creation.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            timer.mark("snapshot")
            track, error = _find_track(state, int(proposal["track_index"]), str(proposal.get("track_name", "")))
            if error or track is None:
                return self._failed(proposal, key, error or "Target Live track is unavailable.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            current = self.client.get_midi_clip_state(int(proposal["track_index"]), int(proposal["clip_slot_index"]))
            if not current.get("success"):
                return self._failed(proposal, key, current.get("error", "MIDI clip-slot readback failed before creation"), readback=current, correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            if current.get("has_clip"):
                return self._failed(proposal, key, "Target clip slot changed and now contains a clip.", readback=current, correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            notes = proposal.get("notes")
            canonical, note_error = _canonical_notes(notes)
            if note_error or canonical is None:
                return self._failed(proposal, key, note_error or "Proposal contains invalid notes.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            track_index = int(proposal["track_index"])
            clip_slot_index = int(proposal["clip_slot_index"])
            length = float(proposal["length"])

            def read_after_uncertain_write() -> dict[str, Any]:
                try:
                    return self.client.get_midi_clip_state(track_index, clip_slot_index)
                except Exception as exc:
                    return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

            try:
                create_ok = bool(self.client.create_midi_clip(track_index, clip_slot_index, length))
                create_error = "" if create_ok else "AbletonOSC did not accept MIDI clip creation."
                if create_ok and proposal.get("clip_name") and hasattr(self.client, "set_clip_name"):
                    try:
                        self.client.set_clip_name(track_index, clip_slot_index, str(proposal["clip_name"]))
                    except Exception:
                        pass
            except Exception as exc:
                create_ok = False
                create_error = f"MIDI clip creation acknowledgement was lost: {type(exc).__name__}: {exc}"
            if not create_ok:
                uncertain_readback = read_after_uncertain_write()
                timer.mark("readback")
                retry_safe = "requires_inspection" if uncertain_readback.get("has_clip") else "unsafe"
                return self._failed(
                    proposal,
                    key,
                    create_error,
                    readback=uncertain_readback,
                    retry_safe=retry_safe,
                    correlation_id=correlation_id,
                    stage_timings_ms=timer.as_ms(),
                )

            try:
                add_ok = bool(self.client.add_midi_notes(track_index, clip_slot_index, canonical))
                add_error = "" if add_ok else "AbletonOSC did not accept MIDI notes."
            except Exception as exc:
                add_ok = False
                add_error = f"MIDI note insertion acknowledgement was lost: {type(exc).__name__}: {exc}"
            write_acknowledgement = "confirmed"
            if not add_ok:
                uncertain_readback = read_after_uncertain_write()
                timer.mark("readback")
                # A timeout can happen after Live has applied every note. In
                # that case the exact readback is authoritative and the
                # operation is safe to retain with an explicit acknowledgement
                # class rather than asking the caller to retry blindly.
                exact = bool(
                    uncertain_readback.get("success")
                    and uncertain_readback.get("has_clip")
                    and uncertain_readback.get("is_midi_clip")
                    and math.isclose(float(uncertain_readback.get("length", 0.0)), length, rel_tol=0.0, abs_tol=1e-4)
                    and _notes_equal(canonical, uncertain_readback.get("notes"))
                )
                if not exact:
                    retry_safe = "requires_inspection" if uncertain_readback.get("has_clip") else "unsafe"
                    return self._failed(
                        proposal,
                        key,
                        add_error,
                        readback=uncertain_readback,
                        retry_safe=retry_safe,
                        correlation_id=correlation_id,
                        stage_timings_ms=timer.as_ms(),
                    )
                write_acknowledgement = "unacknowledged_write_reconciled"
            timer.mark("write")
            if write_acknowledgement == "confirmed":
                time.sleep(0.05)
                readback = self.client.get_midi_clip_state(track_index, clip_slot_index)
            else:
                readback = uncertain_readback
            timer.mark("readback")
            verified = bool(
                readback.get("success")
                and readback.get("has_clip")
                and readback.get("is_midi_clip")
                and math.isclose(float(readback.get("length", 0.0)), float(proposal["length"]), rel_tol=0.0, abs_tol=1e-4)
                and _notes_equal(canonical, readback.get("notes"))
            )
            _finish_idempotency(key)
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "receipt_id": f"receipt-{uuid.uuid4().hex}",
                "action_id": proposal.get("action_id"),
                "action": "create_midi_clip",
                "idempotency_key": key,
                "status": "applied" if verified else "failed_verification",
                "verified": verified,
                "timestamp": time.time(),
                    "target": {
                    "track_index": track_index,
                    "track_name": str(proposal.get("track_name", "")),
                    "clip_slot_index": clip_slot_index,
                },
                "before": proposal.get("before"),
                "requested": proposal.get("after"),
                "readback": readback,
                "source_artifact_sha256": proposal.get("source_artifact_sha256", ""),
                "source_artifact_id": proposal.get("source_artifact_id", ""),
                "source_context": proposal.get("source_context"),
                "notes": canonical,
                "notes_written": len(canonical),
                "notes_verified": len(readback.get("notes", [])) if isinstance(readback, dict) else 0,
                "undo_payload": {
                    "action": "remove_midi_clip",
                    "track_index": track_index,
                    "track_name": str(proposal.get("track_name", "")),
                    "clip_slot_index": clip_slot_index,
                    "expected_notes": canonical,
                    "expected_length": float(proposal["length"]),
                    "source_receipt_id": "pending",
                },
                "write_acknowledgement": write_acknowledgement,
                "correlation_id": correlation_id,
                "retry_safe": classify_retry_safety(verified=verified, status="applied" if verified else "failed_verification"),
                "stage_timings_ms": timer.as_ms(),
            }
            receipt["undo_payload"]["source_receipt_id"] = receipt["receipt_id"]
            return {"ok": verified, "error": None if verified else "MIDI clip was sent but readback verification failed.", "receipt": receipt}
        except Exception as exc:
            return self._failed(proposal, key, f"MIDI clip creation failed: {exc}", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())

    def propose_undo(self, receipt: dict[str, Any], *, session_id: str) -> dict[str, Any]:
        if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
            return {"ok": False, "error": "A valid KENN MIDI clip receipt is required for undo."}
        if receipt.get("action") == "update_midi_clip":
            if receipt.get("status") != "applied" or not receipt.get("verified"):
                return {"ok": False, "error": "Only a verified applied MIDI clip update can be undone."}
            target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
            undo = receipt.get("undo_payload") if isinstance(receipt.get("undo_payload"), dict) else {}
            try:
                track_index = int(target["track_index"])
                clip_slot_index = int(target["clip_slot_index"])
            except (KeyError, TypeError, ValueError):
                return {"ok": False, "error": "Receipt has no complete MIDI clip identity for undo."}
            restore_notes, restore_error = _canonical_notes(undo.get("restore_notes"), allow_empty=True)
            if restore_error or restore_notes is None:
                return {"ok": False, "error": "Receipt has no complete original MIDI note set for undo."}
            current = self.client.get_midi_clip_state(track_index, clip_slot_index)
            expected_notes = undo.get("expected_notes")
            if not current.get("success") or not current.get("has_clip") or not current.get("is_midi_clip") or not _notes_equal(expected_notes, current.get("notes")):
                return {"ok": False, "error": "MIDI clip notes changed since the receipt; undo is stale."}
            expected_length = float(undo.get("expected_length", 0.0))
            if not math.isclose(float(current.get("length", 0.0)), expected_length, rel_tol=0.0, abs_tol=1e-4):
                return {"ok": False, "error": "MIDI clip length changed since the receipt; undo is stale."}
            return self.propose_update(
                track_index=track_index,
                track_name=str(target.get("track_name", "")),
                clip_slot_index=clip_slot_index,
                notes=restore_notes,
                session_id=session_id,
                source_receipt_id=str(receipt.get("receipt_id", "")),
            )
        if receipt.get("status") != "applied" or not receipt.get("verified"):
            return {"ok": False, "error": "Only a verified applied MIDI clip creation can be undone."}
        target = receipt.get("target") or {}
        undo = receipt.get("undo_payload") or {}
        try:
            track_index = int(target["track_index"])
            clip_slot_index = int(target["clip_slot_index"])
            expected_length = float(undo["expected_length"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "Receipt has no complete MIDI clip identity for undo."}
        try:
            state = self._snapshot()
        except Exception as exc:
            return {"ok": False, "error": f"Live snapshot failed while preparing undo: {exc}"}
        track, track_error = _find_track(state, track_index, str(target.get("track_name", "")))
        if track_error or track is None:
            return {"ok": False, "error": track_error or "MIDI clip source track is no longer present; undo is stale."}
        current = self.client.get_midi_clip_state(track_index, clip_slot_index)
        if not current.get("success") or not current.get("has_clip") or not current.get("is_midi_clip"):
            return {"ok": False, "error": "MIDI clip is no longer present as recorded; undo is stale."}
        expected_notes = undo.get("expected_notes")
        if not isinstance(expected_notes, list) or not _notes_equal(expected_notes, current.get("notes")):
            return {"ok": False, "error": "MIDI clip notes changed since the receipt; undo is stale."}
        if not math.isclose(float(current.get("length", 0.0)), expected_length, rel_tol=0.0, abs_tol=1e-4):
            return {"ok": False, "error": "MIDI clip length changed since the receipt; undo is stale."}
        proposal = {
            "schema": REMOVE_PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "remove_midi_clip",
            "operation": "remove_midi_clip",
            "target": "ableton_midi_clip_slot",
            "track_index": track_index,
            "track_name": str(target.get("track_name", "")),
            "clip_slot_index": clip_slot_index,
            "expected_length": expected_length,
            "expected_notes": expected_notes,
            "source_receipt_id": str(receipt.get("receipt_id", "")),
            "source_context": receipt.get("source_context"),
            "requires_confirmation": True,
            "timestamp": time.time(),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_midi_clip", text=_proposal_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        return {"ok": True, "proposal": proposal}

    def execute_remove(
        self,
        proposal: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        correlation_id = resolve_correlation_id(correlation_id or (proposal.get("correlation_id") if isinstance(proposal, dict) else None))
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != REMOVE_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid KENN MIDI clip removal proposal is required."}
        if not proposal.get("requires_confirmation") or str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "error": "Explicit confirmation is required for this exact MIDI clip removal."}
        key = _text(idempotency_key or proposal.get("action_id"), 256)
        if not key or not _reserve_idempotency(key):
            return {"ok": False, "error": "This MIDI clip removal was already executed or is already in progress."}
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_midi_clip", text=_proposal_text(proposal)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used MIDI clip removal confirmation token."}
        try:
            state = self._snapshot()
            track, track_error = _find_track(
                state,
                int(proposal["track_index"]),
                str(proposal.get("track_name", "")),
            )
            if track_error or track is None:
                return self._failed(
                    proposal,
                    key,
                    track_error or "MIDI clip source track is no longer present; no deletion was sent.",
                    correlation_id=correlation_id,
                    stage_timings_ms=timer.as_ms(),
                )
            current = self.client.get_midi_clip_state(int(proposal["track_index"]), int(proposal["clip_slot_index"]))
            timer.mark("snapshot")
            if not current.get("success") or not current.get("has_clip") or not _notes_equal(proposal.get("expected_notes", []), current.get("notes")):
                return self._failed(proposal, key, "MIDI clip changed before undo; no deletion was sent.", readback=current, correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            deleter = getattr(self.client, "delete_midi_clip", getattr(self.client, "delete_clip", None))
            if deleter is None or not deleter(int(proposal["track_index"]), int(proposal["clip_slot_index"])):
                return self._failed(proposal, key, "AbletonOSC did not accept MIDI clip deletion.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            timer.mark("write")
            time.sleep(0.05)
            readback = self.client.get_midi_clip_state(int(proposal["track_index"]), int(proposal["clip_slot_index"]))
            timer.mark("readback")
            verified = bool(readback.get("success") and not readback.get("has_clip"))
            _finish_idempotency(key)
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "receipt_id": f"receipt-{uuid.uuid4().hex}",
                "action_id": proposal.get("action_id"),
                "action": "remove_midi_clip",
                "idempotency_key": key,
                "status": "applied" if verified else "failed_verification",
                "verified": verified,
                "timestamp": time.time(),
                "target": {
                    "track_index": int(proposal["track_index"]),
                    "track_name": str(proposal.get("track_name", "")),
                    "clip_slot_index": int(proposal["clip_slot_index"]),
                },
                "before": {"has_clip": True},
                "requested": {"has_clip": False},
                "readback": readback,
                "source_receipt_id": proposal.get("source_receipt_id", ""),
                "source_context": proposal.get("source_context"),
                "correlation_id": correlation_id,
                "retry_safe": classify_retry_safety(verified=verified, status="applied" if verified else "failed_verification"),
                "stage_timings_ms": timer.as_ms(),
            }
            return {"ok": verified, "error": None if verified else "MIDI clip deletion was sent but readback verification failed.", "receipt": receipt}
            return {
                "ok": verified,
                "verified": verified,
                "error": None if verified else "MIDI clip deletion was sent but readback verification failed.",
                "receipt": receipt,
            }
        except Exception as exc:
            return self._failed(proposal, key, f"MIDI clip removal failed: {exc}", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())

    # Aliases for generative composition and undo engines
    propose = propose_create
    execute = execute_create
    execute_undo = execute_remove


__all__ = [
    "CREATE_PROPOSAL_SCHEMA",
    "PROPOSAL_SCHEMA",
    "UPDATE_PROPOSAL_SCHEMA",
    "REMOVE_PROPOSAL_SCHEMA",
    "UNDO_PROPOSAL_SCHEMA",
    "RECEIPT_SCHEMA",
    "MidiClipActionService",
    "RECEIPT_SCHEMA",
    "REMOVE_PROPOSAL_SCHEMA",
    "UPDATE_PROPOSAL_SCHEMA",
    "quantize_pitch_to_scale",
    "parse_root_note",
    "SCALE_INTERVALS",
    "NOTE_NAME_TO_INT",
    "INT_TO_NOTE_NAME",
]
