"""Confirmation-gated duplication of an existing Ableton Session View clip.

The service is deliberately narrower than Live's raw API: it duplicates only
into a freshly verified empty slot, binds source and target track identity,
reads the result back, and makes undo conditional on the duplicate remaining
unchanged. MIDI notes are verified when available; audio bytes are not exposed
by AbletonOSC and are therefore represented by honest metadata only.
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


PROPOSAL_SCHEMA = "kenn.ableton_clip_duplication_proposal.v1"
UNDO_PROPOSAL_SCHEMA = "kenn.ableton_clip_duplication_undo_proposal.v1"
RECEIPT_SCHEMA = "kenn.ableton_clip_duplication_receipt.v1"
_USED_IDEMPOTENCY_KEYS: set[str] = set()
_IN_FLIGHT_IDEMPOTENCY_KEYS: set[str] = set()
_ACTION_LOCK = Lock()


def _text(value: Any, limit: int = 512) -> str:
    return str(value or "").strip()[:limit]


def _snapshot(client: Any) -> dict[str, Any]:
    if hasattr(client, "query_session_topology"):
        return client.query_session_topology()
    return client.query_session_state(include_mixer=False)


def _find_track(state: dict[str, Any], index: int, name: str) -> tuple[dict[str, Any] | None, str | None]:
    matches = [item for item in state.get("tracks", []) if isinstance(item, dict) and int(item.get("index", -1)) == index]
    if len(matches) != 1:
        return None, "track index is not present exactly once in the current Live snapshot"
    if name and str(matches[0].get("name", "")) != name:
        return None, "track name changed since the proposal was created"
    return matches[0], None


def _normal_notes(notes: Any) -> list[dict[str, Any]] | None:
    if not isinstance(notes, list):
        return None
    result: list[dict[str, Any]] = []
    for note in notes:
        if not isinstance(note, dict):
            return None
        try:
            pitch = int(note["pitch"])
            start = float(note["start_time"])
            duration = float(note["duration"])
            velocity = int(note["velocity"])
            mute = bool(note.get("mute", False))
        except (KeyError, TypeError, ValueError):
            return None
        if not 0 <= pitch <= 127 or not math.isfinite(start) or start < 0 or not math.isfinite(duration) or duration <= 0 or not 1 <= velocity <= 127:
            return None
        result.append({"pitch": pitch, "start_time": start, "duration": duration, "velocity": velocity, "mute": mute})
    return sorted(result, key=lambda item: (item["pitch"], item["start_time"], item["duration"], item["velocity"], item["mute"]))


def _clip_fingerprint(clip: dict[str, Any]) -> str:
    stable = {
        "has_clip": bool(clip.get("has_clip")),
        "clip_name": _text(clip.get("clip_name", clip.get("name", "")), 256),
        "is_midi_clip": bool(clip.get("is_midi_clip")),
        "length": round(float(clip.get("length", 0.0)), 6),
        "notes": _normal_notes(clip.get("notes", [])) if clip.get("is_midi_clip") else [],
    }
    return "sha256:" + hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _same_clip(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return bool(actual.get("success") and actual.get("has_clip") and _clip_fingerprint(expected) == _clip_fingerprint(actual))


def _proposal_text(proposal: dict[str, Any]) -> str:
    fields = ("action", "source_track_index", "source_track_name", "source_clip_slot_index", "target_track_index", "target_track_name", "target_clip_slot_index", "source_clip_fingerprint")
    return "|".join(str(proposal.get(key, "")) for key in fields)


def _reserve(key: str) -> bool:
    with _ACTION_LOCK:
        if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
            return False
        _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        return True


def _finish(key: str) -> None:
    with _ACTION_LOCK:
        _USED_IDEMPOTENCY_KEYS.add(key)
        _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
        prune_if_needed(_USED_IDEMPOTENCY_KEYS)


class ClipDuplicationActionService:
    """Duplicate one exact existing clip with confirmation and readback gates."""

    def __init__(self, client: AbletonOSCClient | Any = None):
        self.client = client or live_client

    def propose(
        self,
        *,
        source_track_index: int,
        source_track_name: str,
        source_clip_slot_index: int,
        target_track_index: int,
        target_track_name: str,
        target_clip_slot_index: int,
        session_id: str,
    ) -> dict[str, Any]:
        try:
            source_track_index = int(source_track_index)
            source_slot = int(source_clip_slot_index)
            target_track_index = int(target_track_index)
            target_slot = int(target_clip_slot_index)
        except (TypeError, ValueError):
            return {"ok": False, "error": "source/target track and clip-slot indices must be numeric"}
        if min(source_track_index, source_slot, target_track_index, target_slot) < 0:
            return {"ok": False, "error": "source/target track and clip-slot indices must be non-negative"}
        if (source_track_index, source_slot) == (target_track_index, target_slot):
            return {"ok": False, "error": "source and target clip slots must be different"}
        source_name = _text(source_track_name, 256)
        target_name = _text(target_track_name, 256)
        if not source_name or not target_name or not _text(session_id, 128):
            return {"ok": False, "error": "session_id and both exact track names are required"}
        try:
            state = _snapshot(self.client)
            if state.get("status") != "connected":
                return {"ok": False, "error": "Ableton Live is offline or returned no usable topology."}
            source_track, error = _find_track(state, source_track_index, source_name)
            if error or source_track is None:
                return {"ok": False, "error": error or "source track is unavailable"}
            target_track, error = _find_track(state, target_track_index, target_name)
            if error or target_track is None:
                return {"ok": False, "error": error or "target track is unavailable"}
            source = self.client.get_clip_slot_state(source_track_index, source_slot)
            target = self.client.get_clip_slot_state(target_track_index, target_slot)
        except Exception as exc:
            return {"ok": False, "error": f"Clip-slot inspection failed: {exc}"}
        if not source.get("success") or not source.get("has_clip"):
            return {"ok": False, "error": source.get("error", "source clip is not available")}
        if not target.get("success"):
            return {"ok": False, "error": target.get("error", "target clip-slot inspection failed")}
        if target.get("has_clip"):
            return {"ok": False, "error": "target clip slot already contains a clip; replacement is disabled"}
        if source.get("is_midi_clip") and _normal_notes(source.get("notes")) is None:
            return {"ok": False, "error": "source MIDI clip returned invalid note data"}
        fingerprint = _clip_fingerprint(source)
        proposal = {
            "schema": PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "duplicate_clip",
            "operation": "duplicate_clip_to",
            "source": {"track_index": source_track_index, "track_name": source_name, "clip_slot_index": source_slot},
            "target": {"track_index": target_track_index, "track_name": target_name, "clip_slot_index": target_slot},
            "source_track_index": source_track_index,
            "source_track_name": source_name,
            "source_clip_slot_index": source_slot,
            "target_track_index": target_track_index,
            "target_track_name": target_name,
            "target_clip_slot_index": target_slot,
            "source_clip": source,
            "source_clip_fingerprint": fingerprint,
            "before": {"target_has_clip": False},
            "after": {"target_has_clip": True, "source_clip_fingerprint": fingerprint, "is_midi_clip": bool(source.get("is_midi_clip"))},
            "reason": f"Duplicate '{source.get('clip_name', 'clip')}' into empty slot {target_slot} on '{target_name}'.",
            "risk": "local_mutation",
            "confidence": 1.0,
            "requires_confirmation": True,
            "timestamp": time.time(),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_clip_duplication", text=_proposal_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        return {"ok": True, "proposal": proposal}

    def _failed(self, proposal: dict[str, Any], key: str, error: str, *, readback: Any = None, correlation_id: str = "", timer: StageTimer | None = None) -> dict[str, Any]:
        _finish(key)
        return {"ok": False, "error": error, "receipt": {
            "schema": RECEIPT_SCHEMA, "receipt_id": f"receipt-{uuid.uuid4().hex}", "action_id": proposal.get("action_id"),
            "action": proposal.get("action"), "status": "failed", "verified": False, "timestamp": time.time(),
            "target": proposal.get("target"), "before": proposal.get("before"), "requested": proposal.get("after"),
            "readback": readback, "error": error, "correlation_id": resolve_correlation_id(correlation_id),
            "retry_safe": "unsafe", "stage_timings_ms": timer.as_ms() if timer else {},
        }}

    def execute(self, proposal: dict[str, Any], *, confirm_token: str, session_id: str, idempotency_key: str = "", correlation_id: str = "") -> dict[str, Any]:
        timer = StageTimer()
        correlation_id = resolve_correlation_id(correlation_id)
        if not isinstance(proposal, dict) or proposal.get("schema") != PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid clip duplication proposal is required."}
        if not proposal.get("requires_confirmation") or str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required for this exact clip duplication."}
        key = _text(idempotency_key or proposal.get("action_id"), 256)
        if not key or not _reserve(key):
            return {"ok": False, "error": "This clip duplication was already executed or is already in progress."}
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_clip_duplication", text=_proposal_text(proposal)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used clip duplication confirmation token."}
        try:
            state = _snapshot(self.client)
            if state.get("status") != "connected":
                return self._failed(proposal, key, "Ableton Live became unavailable before clip duplication.", correlation_id=correlation_id, timer=timer)
            source_track, error = _find_track(state, int(proposal["source_track_index"]), str(proposal.get("source_track_name", "")))
            if error or source_track is None:
                return self._failed(proposal, key, error or "source track changed", correlation_id=correlation_id, timer=timer)
            target_track, error = _find_track(state, int(proposal["target_track_index"]), str(proposal.get("target_track_name", "")))
            if error or target_track is None:
                return self._failed(proposal, key, error or "target track changed", correlation_id=correlation_id, timer=timer)
            source = self.client.get_clip_slot_state(int(proposal["source_track_index"]), int(proposal["source_clip_slot_index"]))
            target = self.client.get_clip_slot_state(int(proposal["target_track_index"]), int(proposal["target_clip_slot_index"]))
            timer.mark("snapshot")
            if not _same_clip(proposal.get("source_clip", {}), source):
                return self._failed(proposal, key, "source clip changed since the proposal; no duplication was sent", readback=source, correlation_id=correlation_id, timer=timer)
            if not target.get("success") or target.get("has_clip"):
                return self._failed(proposal, key, "target clip slot changed and is no longer empty; no duplication was sent", readback=target, correlation_id=correlation_id, timer=timer)
            if not self.client.duplicate_clip_to(int(proposal["source_track_index"]), int(proposal["source_clip_slot_index"]), int(proposal["target_track_index"]), int(proposal["target_clip_slot_index"])):
                return self._failed(proposal, key, "AbletonOSC did not accept clip duplication", correlation_id=correlation_id, timer=timer)
            timer.mark("write")
            time.sleep(0.05)
            readback = self.client.get_clip_slot_state(int(proposal["target_track_index"]), int(proposal["target_clip_slot_index"]))
            timer.mark("readback")
            verified = _same_clip(proposal.get("source_clip", {}), readback)
            _finish(key)
            receipt = {
                "schema": RECEIPT_SCHEMA, "receipt_id": f"receipt-{uuid.uuid4().hex}", "action_id": proposal.get("action_id"),
                "action": "duplicate_clip", "idempotency_key": key, "status": "applied" if verified else "failed_verification", "verified": verified, "timestamp": time.time(),
                "source": proposal.get("source"), "target": proposal.get("target"), "before": proposal.get("before"), "requested": proposal.get("after"),
                "source_clip": proposal.get("source_clip"), "readback": readback, "correlation_id": correlation_id,
                "retry_safe": classify_retry_safety(verified=verified, status="applied" if verified else "failed_verification"), "stage_timings_ms": timer.as_ms(),
                "undo_payload": {"target": proposal.get("target"), "expected_clip": proposal.get("source_clip"), "source_receipt_id": "pending"},
            }
            receipt["undo_payload"]["source_receipt_id"] = receipt["receipt_id"]
            return {"ok": verified, "error": None if verified else "Clip duplication was sent but readback verification failed.", "receipt": receipt}
        except Exception as exc:
            return self._failed(proposal, key, f"Clip duplication failed: {exc}", correlation_id=correlation_id, timer=timer)

    def propose_undo(self, receipt: dict[str, Any], *, session_id: str) -> dict[str, Any]:
        if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("status") != "applied" or not receipt.get("verified"):
            return {"ok": False, "error": "Only a verified applied clip duplication can be undone."}
        target = receipt.get("target") or {}
        expected = receipt.get("source_clip") or (receipt.get("undo_payload") or {}).get("expected_clip")
        if not isinstance(expected, dict):
            return {"ok": False, "error": "Receipt has no complete duplicated-clip identity for undo."}
        try:
            state = _snapshot(self.client)
            target_index = int(target["track_index"])
            target_name = str(target.get("track_name", ""))
            target_track, track_error = _find_track(state, target_index, target_name)
            if track_error or target_track is None:
                return {"ok": False, "error": track_error or "Undo target track is no longer present; undo is stale."}
            current = self.client.get_clip_slot_state(int(target["track_index"]), int(target["clip_slot_index"]))
        except Exception as exc:
            return {"ok": False, "error": f"Undo target inspection failed: {exc}"}
        if not _same_clip(expected, current):
            return {"ok": False, "error": "Duplicated clip changed or disappeared; undo is stale."}
        proposal = {
            "schema": UNDO_PROPOSAL_SCHEMA, "action_id": f"action-{uuid.uuid4().hex}", "action": "undo_duplicate_clip",
            "target": target, "expected_clip": expected, "source_receipt_id": receipt.get("receipt_id", ""),
            "requires_confirmation": True, "timestamp": time.time(),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_clip_duplication", text=_proposal_text({**proposal, "target_track_index": target.get("track_index"), "target_track_name": target.get("track_name"), "target_clip_slot_index": target.get("clip_slot_index"), "source_clip_fingerprint": _clip_fingerprint(expected)}))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        return {"ok": True, "proposal": proposal}

    def execute_undo(self, proposal: dict[str, Any], *, confirm_token: str, session_id: str, idempotency_key: str = "", correlation_id: str = "") -> dict[str, Any]:
        if not isinstance(proposal, dict) or proposal.get("schema") != UNDO_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid clip duplication undo proposal is required."}
        if str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required for this exact clip deletion."}
        key = _text(idempotency_key or proposal.get("action_id"), 256)
        if not key or not _reserve(key):
            return {"ok": False, "error": "This clip duplication undo was already executed or is already in progress."}
        token_text = {**proposal, "target_track_index": (proposal.get("target") or {}).get("track_index"), "target_track_name": (proposal.get("target") or {}).get("track_name"), "target_clip_slot_index": (proposal.get("target") or {}).get("clip_slot_index"), "source_clip_fingerprint": _clip_fingerprint(proposal.get("expected_clip") or {})}
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_clip_duplication", text=_proposal_text(token_text)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used clip deletion confirmation token."}
        target = proposal.get("target") or {}
        try:
            state = _snapshot(self.client)
            target_track, track_error = _find_track(
                state,
                int(target["track_index"]),
                str(target.get("track_name", "")),
            )
            if track_error or target_track is None:
                return self._failed(proposal, key, track_error or "Undo target track is no longer present; no deletion was sent.", correlation_id=correlation_id)
            current = self.client.get_clip_slot_state(int(target["track_index"]), int(target["clip_slot_index"]))
            if not _same_clip(proposal.get("expected_clip") or {}, current):
                return self._failed(proposal, key, "Duplicated clip changed before undo; no deletion was sent.", readback=current, correlation_id=correlation_id)
            if not self.client.delete_clip(int(target["track_index"]), int(target["clip_slot_index"])):
                return self._failed(proposal, key, "AbletonOSC did not accept clip deletion.", correlation_id=correlation_id)
            time.sleep(0.05)
            readback = self.client.get_clip_slot_state(int(target["track_index"]), int(target["clip_slot_index"]))
            verified = bool(readback.get("success") and not readback.get("has_clip"))
            _finish(key)
            receipt = {"schema": RECEIPT_SCHEMA, "receipt_id": f"receipt-{uuid.uuid4().hex}", "action_id": proposal.get("action_id"), "action": "undo_duplicate_clip", "idempotency_key": key, "status": "applied" if verified else "failed_verification", "verified": verified, "timestamp": time.time(), "target": target, "before": {"has_clip": True}, "requested": {"has_clip": False}, "readback": readback, "source_receipt_id": proposal.get("source_receipt_id", ""), "correlation_id": resolve_correlation_id(correlation_id), "retry_safe": classify_retry_safety(verified=verified, status="applied" if verified else "failed_verification")}
            return {"ok": verified, "error": None if verified else "Clip deletion was sent but readback verification failed.", "receipt": receipt}
        except Exception as exc:
            return self._failed(proposal, key, f"Clip duplication undo failed: {exc}", correlation_id=correlation_id)


__all__ = ["ClipDuplicationActionService", "PROPOSAL_SCHEMA", "UNDO_PROPOSAL_SCHEMA", "RECEIPT_SCHEMA"]
