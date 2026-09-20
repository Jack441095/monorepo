"""Confirmation-gated audition of one exact existing Ableton MIDI clip.

Audition is intentionally separate from clip creation.  KENN may start and
stop one identified clip only after a proposal is confirmed, and it verifies
both transitions through AbletonOSC playback readback.  No clip is replaced,
deleted, or launched by a natural-language parser on this path.
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
from kenn.core.confirmation import consume_confirmation, issue_confirmation
from kenn.core.idempotency_bounds import prune_if_needed
from kenn.core.receipt_contract import StageTimer, classify_retry_safety, resolve_correlation_id


PROPOSAL_SCHEMA = "kenn.ableton_clip_audition_proposal.v1"
RECEIPT_SCHEMA = "kenn.ableton_clip_audition_receipt.v1"
_USED_IDEMPOTENCY_KEYS: set[str] = set()
_IN_FLIGHT_IDEMPOTENCY_KEYS: set[str] = set()
_ACTION_LOCK = Lock()


def _text(value: Any, limit: int = 512) -> str:
    return str(value or "").strip()[:limit]


def _find_track(state: dict[str, Any], track_index: int, track_name: str) -> tuple[dict[str, Any] | None, str | None]:
    tracks = [item for item in state.get("tracks", []) if isinstance(item, dict)]
    matches = [item for item in tracks if int(item.get("index", -1)) == track_index]
    if len(matches) != 1:
        return None, "track index is not present exactly once in the current Live snapshot"
    track = matches[0]
    if track_name and str(track.get("name", "")) != track_name:
        return None, "track name changed since the proposal was created"
    return track, None


def _clip_fingerprint(clip: dict[str, Any]) -> str:
    notes = clip.get("notes") if isinstance(clip.get("notes"), list) else []
    stable_notes = sorted(
        (dict(note) for note in notes if isinstance(note, dict)),
        key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
    )
    stable = {
        "has_clip": bool(clip.get("has_clip")),
        "is_midi_clip": bool(clip.get("is_midi_clip")),
        "length": round(float(clip.get("length", 0.0)), 6),
        "notes": stable_notes,
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def clip_fingerprint(clip: dict[str, Any]) -> str:
    """Return the stable identity fingerprint used by audition receipts."""
    return _clip_fingerprint(clip)


def _same_clip(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    if not actual.get("success") or not actual.get("has_clip") or not actual.get("is_midi_clip"):
        return False
    try:
        expected_length = float(expected.get("length", 0.0))
        actual_length = float(actual.get("length", 0.0))
    except (TypeError, ValueError):
        return False
    return (
        math.isclose(expected_length, actual_length, rel_tol=0.0, abs_tol=1e-4)
        and str(expected.get("fingerprint", "")) == _clip_fingerprint(actual)
    )


def _proposal_text(proposal: dict[str, Any]) -> str:
    return "|".join(
        str(proposal.get(key, ""))
        for key in ("action", "track_index", "track_name", "clip_slot_index", "clip_fingerprint", "source_receipt_id")
    )


def _reserve(key: str) -> bool:
    with _ACTION_LOCK:
        if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
            return False
        _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        return True


def _finish(key: str) -> None:
    with _ACTION_LOCK:
        _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
        _USED_IDEMPOTENCY_KEYS.add(key)
        prune_if_needed(_USED_IDEMPOTENCY_KEYS)


class ClipAuditionActionService:
    """Audition and stop one exact existing MIDI clip with verified readback."""

    def __init__(self, client: AbletonOSCClient | Any = None):
        self.client = client or live_client

    def _snapshot(self) -> dict[str, Any]:
        if hasattr(self.client, "query_session_topology"):
            return self.client.query_session_topology()
        return self.client.query_session_state(include_mixer=False)

    def _transport_is_playing(self) -> bool | None:
        """Read transport only when available; unknown is never treated as stopped."""
        getter = getattr(self.client, "get_transport_state", None)
        if not callable(getter):
            return None
        try:
            state = getter()
        except Exception:
            return None
        if not isinstance(state, dict) or not state.get("success") or "is_playing" not in state:
            return None
        return bool(state["is_playing"])

    def _target_state(self, proposal: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str | None]:
        state = self._snapshot()
        if state.get("status") != "connected":
            return state, {}, "Ableton Live became unavailable."
        try:
            track_index = int(proposal["track_index"])
            slot = int(proposal["clip_slot_index"])
        except (KeyError, TypeError, ValueError):
            return state, {}, "The clip audition proposal has invalid target indices."
        track, error = _find_track(state, track_index, str(proposal.get("track_name", "")))
        if error or track is None:
            return state, {}, error or "Target Live track is unavailable."
        clip = self.client.get_midi_clip_state(track_index, slot)
        if not clip.get("success"):
            return state, clip, clip.get("error", "MIDI clip inspection failed.")
        return state, clip, None

    def propose(
        self,
        *,
        track_index: int,
        track_name: str,
        clip_slot_index: int,
        session_id: str,
        source_receipt_id: str = "",
    ) -> dict[str, Any]:
        clean_name = _text(track_name, 256)
        if not clean_name:
            return {"ok": False, "error": "track_name is required for an exact clip audition target"}
        try:
            track_index = int(track_index)
            clip_slot_index = int(clip_slot_index)
        except (TypeError, ValueError):
            return {"ok": False, "error": "track_index and clip_slot_index must be integers"}
        if min(track_index, clip_slot_index) < 0:
            return {"ok": False, "error": "track and clip-slot indices must be non-negative"}
        try:
            state = self._snapshot()
            if state.get("status") != "connected":
                return {"ok": False, "error": "Ableton Live is offline or returned no usable topology."}
            track, error = _find_track(state, track_index, clean_name)
            if error or track is None:
                return {"ok": False, "error": error or "Target Live track is unavailable."}
            clip = self.client.get_midi_clip_state(track_index, clip_slot_index)
        except Exception as exc:
            return {"ok": False, "error": f"MIDI clip inspection failed: {exc}"}
        if not clip.get("success"):
            return {"ok": False, "error": clip.get("error", "MIDI clip inspection failed")}
        if not clip.get("has_clip") or not clip.get("is_midi_clip"):
            return {"ok": False, "error": "The exact target must contain an existing MIDI clip; no audition proposal was created."}
        try:
            playback = self.client.get_clip_playback_state(track_index, clip_slot_index)
        except Exception as exc:
            return {"ok": False, "error": f"Clip playback inspection failed: {exc}"}
        if not playback.get("success"):
            return {"ok": False, "error": playback.get("error", "Clip playback inspection failed")}
        transport_before = self._transport_is_playing()
        proposal = {
            "schema": PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "audition_clip",
            "operation": "audition_clip",
            "target": "ableton_midi_clip_slot",
            "track_index": track_index,
            "track_name": str(track.get("name", "")),
            "clip_slot_index": clip_slot_index,
            "clip_fingerprint": _clip_fingerprint(clip),
            "clip_length": float(clip.get("length", 0.0)),
            "note_count": len(clip.get("notes", [])) if isinstance(clip.get("notes"), list) else 0,
            "source_receipt_id": _text(source_receipt_id, 256),
            "before": {
                "is_playing": bool(playback.get("is_playing")),
                "is_triggered": bool(playback.get("is_triggered")),
            },
            "transport_was_playing_before": transport_before,
            "after": {"playback_started": True},
            "reason": f"Explicit request to audition '{track.get('name', '')}', clip slot {clip_slot_index}.",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "session_version": hashlib.sha256(json.dumps(track, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_clip_audition", text=_proposal_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        return {"ok": True, "proposal": proposal}

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
        _finish(key)
        return {
            "ok": False,
            "error": error,
            "receipt": {
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
                "source_receipt_id": proposal.get("source_receipt_id", ""),
                "retry_safe": retry_safe,
                "correlation_id": resolve_correlation_id(correlation_id or proposal.get("correlation_id")),
                "stage_timings_ms": stage_timings_ms or {},
            },
        }

    def execute(
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
        if not isinstance(proposal, dict) or proposal.get("schema") != PROPOSAL_SCHEMA or proposal.get("action") != "audition_clip":
            return {"ok": False, "error": "A valid KENN clip audition proposal is required."}
        if not proposal.get("requires_confirmation") or str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required for this exact clip audition."}
        key = _text(idempotency_key or proposal.get("action_id"), 256)
        if not key or not _reserve(key):
            return {"ok": False, "error": "This clip audition was already executed or is already in progress."}
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_clip_audition", text=_proposal_text(proposal)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used clip audition confirmation token."}
        try:
            _state, clip, error = self._target_state(proposal)
            timer.mark("snapshot")
            if error:
                return self._failed(proposal, key, error, readback=clip, correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            if not _same_clip({"length": proposal.get("clip_length"), "fingerprint": proposal.get("clip_fingerprint")}, clip):
                return self._failed(proposal, key, "The exact MIDI clip changed before audition; no playback command was sent.", readback=clip, correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            if not self.client.launch_clip(int(proposal["track_index"]), int(proposal["clip_slot_index"])):
                return self._failed(proposal, key, "AbletonOSC did not accept the clip audition command.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            timer.mark("write")
            time.sleep(0.08)
            playback = self.client.get_clip_playback_state(int(proposal["track_index"]), int(proposal["clip_slot_index"]))
            timer.mark("readback")
            verified = bool(playback.get("success") and (playback.get("is_playing") or playback.get("is_triggered")))
            if not verified and proposal.get("transport_was_playing_before") is False:
                # A real Live clip can start the song transport and clear its
                # transient clip flags before this second OSC round trip. The
                # transport is safe corroboration only when this proposal
                # observed Live stopped beforehand; unknown or already-playing
                # transport must never turn a failed clip readback into a
                # success.
                transport_after = self._transport_is_playing()
                verified = bool(transport_after is True)
                if transport_after is not None:
                    playback = {**playback, "transport_is_playing": transport_after}
            _finish(key)
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "receipt_id": f"receipt-{uuid.uuid4().hex}",
                "action_id": proposal.get("action_id"),
                "action": "audition_clip",
                "idempotency_key": key,
                "status": "applied" if verified else "failed_verification",
                "verified": verified,
                "timestamp": time.time(),
                "target": {key: proposal.get(key) for key in ("track_index", "track_name", "clip_slot_index")},
                "clip_identity": {"fingerprint": proposal.get("clip_fingerprint"), "length": proposal.get("clip_length")},
                "before": proposal.get("before"),
                "requested": proposal.get("after"),
                "readback": playback,
                "source_receipt_id": proposal.get("source_receipt_id", ""),
                "undo_payload": {
                    "action": "stop_clip",
                    "track_index": proposal.get("track_index"),
                    "track_name": proposal.get("track_name", ""),
                    "clip_slot_index": proposal.get("clip_slot_index"),
                    "clip_fingerprint": proposal.get("clip_fingerprint"),
                    "clip_length": proposal.get("clip_length"),
                    "source_receipt_id": "pending",
                    "requires_confirmation": True,
                },
                "correlation_id": correlation_id,
                "retry_safe": classify_retry_safety(verified=verified, status="applied" if verified else "failed_verification"),
                "stage_timings_ms": timer.as_ms(),
            }
            receipt["undo_payload"]["source_receipt_id"] = receipt["receipt_id"]
            return {"ok": verified, "error": None if verified else "Clip audition was sent but playback readback was not verified.", "receipt": receipt}
        except Exception as exc:
            return self._failed(proposal, key, f"Clip audition failed: {exc}", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())

    def propose_undo(self, receipt: dict[str, Any], *, session_id: str) -> dict[str, Any]:
        if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
            return {"ok": False, "error": "A valid KENN clip audition receipt is required for undo."}
        if receipt.get("action") != "audition_clip" or receipt.get("status") != "applied" or not receipt.get("verified"):
            return {"ok": False, "error": "Only a verified applied clip audition can be stopped through undo."}
        target = receipt.get("target") or {}
        # The receipt journal deliberately redacts some top-level metadata.
        # Keep the identity in the bounded inverse payload as well so an undo
        # can be recovered after a server restart or an uncertain response.
        identity = receipt.get("clip_identity") or receipt.get("undo_payload") or {}
        proposal = {
            "schema": PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "stop_clip",
            "operation": "stop_clip",
            "target": "ableton_midi_clip_slot",
            "track_index": target.get("track_index"),
            "track_name": _text(target.get("track_name", ""), 256),
            "clip_slot_index": target.get("clip_slot_index"),
            "clip_fingerprint": identity.get("fingerprint", identity.get("clip_fingerprint", "")),
            "clip_length": identity.get("length", identity.get("clip_length")),
            "source_receipt_id": _text(receipt.get("receipt_id", ""), 256),
            "before": receipt.get("readback"),
            "after": {"is_playing": False, "is_triggered": False},
            "requires_confirmation": True,
            "timestamp": time.time(),
        }
        try:
            _state, clip, error = self._target_state(proposal)
        except Exception as exc:
            return {"ok": False, "error": f"MIDI clip inspection failed: {exc}"}
        if error or not _same_clip({"length": proposal.get("clip_length"), "fingerprint": proposal.get("clip_fingerprint")}, clip):
            return {"ok": False, "error": error or "The exact MIDI clip changed; stop proposal is stale."}
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_clip_audition", text=_proposal_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        return {"ok": True, "proposal": proposal}

    def execute_stop(
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
        if not isinstance(proposal, dict) or proposal.get("schema") != PROPOSAL_SCHEMA or proposal.get("action") != "stop_clip":
            return {"ok": False, "error": "A valid KENN clip stop proposal is required."}
        if not proposal.get("requires_confirmation") or str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required for this exact clip stop."}
        key = _text(idempotency_key or proposal.get("action_id"), 256)
        if not key or not _reserve(key):
            return {"ok": False, "error": "This clip stop was already executed or is already in progress."}
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_clip_audition", text=_proposal_text(proposal)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used clip stop confirmation token."}
        try:
            _state, clip, error = self._target_state(proposal)
            timer.mark("snapshot")
            if error:
                return self._failed(proposal, key, error, readback=clip, correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            if not _same_clip({"length": proposal.get("clip_length"), "fingerprint": proposal.get("clip_fingerprint")}, clip):
                return self._failed(proposal, key, "The exact MIDI clip changed before stop; no stop command was sent.", readback=clip, correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            if not self.client.stop_clip(int(proposal["track_index"]), int(proposal["clip_slot_index"])):
                return self._failed(proposal, key, "AbletonOSC did not accept the clip stop command.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            timer.mark("write")
            time.sleep(0.08)
            playback = self.client.get_clip_playback_state(int(proposal["track_index"]), int(proposal["clip_slot_index"]))
            timer.mark("readback")
            verified = bool(playback.get("success") and not playback.get("is_playing") and not playback.get("is_triggered"))
            _finish(key)
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "receipt_id": f"receipt-{uuid.uuid4().hex}",
                "action_id": proposal.get("action_id"),
                "action": "stop_clip",
                "idempotency_key": key,
                "status": "applied" if verified else "failed_verification",
                "verified": verified,
                "timestamp": time.time(),
                "target": {key: proposal.get(key) for key in ("track_index", "track_name", "clip_slot_index")},
                "clip_identity": {"fingerprint": proposal.get("clip_fingerprint"), "length": proposal.get("clip_length")},
                "before": proposal.get("before"),
                "requested": proposal.get("after"),
                "readback": playback,
                "source_receipt_id": proposal.get("source_receipt_id", ""),
                "correlation_id": correlation_id,
                "retry_safe": classify_retry_safety(verified=verified, status="applied" if verified else "failed_verification"),
                "stage_timings_ms": timer.as_ms(),
            }
            return {"ok": verified, "error": None if verified else "Clip stop was sent but stopped-state readback was not verified.", "receipt": receipt}
        except Exception as exc:
            return self._failed(proposal, key, f"Clip stop failed: {exc}", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())


__all__ = ["ClipAuditionActionService", "PROPOSAL_SCHEMA", "RECEIPT_SCHEMA", "clip_fingerprint"]
