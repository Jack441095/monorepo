"""Confirmation-gated renaming of one exact Ableton Session View clip."""

from __future__ import annotations

from copy import deepcopy
import time
import uuid
from threading import Lock
from typing import Any

from kenn.ableton_osc_bridge import AbletonOSCClient, live_client
from kenn.core.clip_duplication_service import _clip_fingerprint, _snapshot, _same_clip
from kenn.core.confirmation import consume_confirmation, issue_confirmation
from kenn.core.idempotency_bounds import prune_if_needed
from kenn.core.receipt_contract import StageTimer, classify_retry_safety, resolve_correlation_id


PROPOSAL_SCHEMA = "kenn.ableton_clip_rename_proposal.v1"
UNDO_PROPOSAL_SCHEMA = "kenn.ableton_clip_rename_undo_proposal.v1"
RECEIPT_SCHEMA = "kenn.ableton_clip_rename_receipt.v1"
_USED_IDEMPOTENCY_KEYS: set[str] = set()
_IN_FLIGHT_IDEMPOTENCY_KEYS: set[str] = set()
_ACTION_LOCK = Lock()


def _text(value: Any, limit: int = 512) -> str:
    return str(value or "").strip()[:limit]


def _find_track(state: dict[str, Any], index: int, name: str) -> tuple[dict[str, Any] | None, str | None]:
    matches = [item for item in state.get("tracks", []) if isinstance(item, dict) and int(item.get("index", -1)) == index]
    if len(matches) != 1:
        return None, "track index is not present exactly once in the current Live snapshot"
    if name and str(matches[0].get("name", "")) != name:
        return None, "track name changed since the proposal was created"
    return matches[0], None


def _proposal_text(proposal: dict[str, Any]) -> str:
    return "|".join(str(proposal.get(key, "")) for key in ("action", "track_index", "track_name", "clip_slot_index", "before_clip_fingerprint", "new_name"))


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


class ClipRenameActionService:
    """Rename one existing clip only while its prior identity remains exact."""

    def __init__(self, client: AbletonOSCClient | Any = None):
        self.client = client or live_client

    def _proposal(self, *, action: str, track_index: int, track_name: str, clip_slot_index: int, before_clip: dict[str, Any], new_name: str, session_id: str, source_receipt_id: str = "") -> dict[str, Any]:
        proposal = {
            "schema": PROPOSAL_SCHEMA if action == "rename_clip" else UNDO_PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": action,
            "target": "ableton_clip_slot",
            "track_index": track_index,
            "track_name": track_name,
            "clip_slot_index": clip_slot_index,
            "before_clip": before_clip,
            "before_clip_fingerprint": _clip_fingerprint(before_clip),
            "new_name": new_name,
            "source_receipt_id": source_receipt_id,
            "requires_confirmation": True,
            "timestamp": time.time(),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_clip_rename", text=_proposal_text(proposal))
        proposal["confirmation_token"] = token
        proposal["confirmation_meta"] = meta
        return proposal

    def propose(self, *, track_index: int, track_name: str, clip_slot_index: int, new_name: str, session_id: str) -> dict[str, Any]:
        try:
            track_index, clip_slot_index = int(track_index), int(clip_slot_index)
        except (TypeError, ValueError):
            return {"ok": False, "error": "track and clip-slot indices must be numeric"}
        clean_name = _text(new_name, 128)
        if min(track_index, clip_slot_index) < 0 or not clean_name:
            return {"ok": False, "error": "A non-empty clip name and non-negative target indices are required"}
        try:
            state = _snapshot(self.client)
            if state.get("status") != "connected":
                return {"ok": False, "error": "Ableton Live is offline or returned no usable topology."}
            track, error = _find_track(state, track_index, _text(track_name, 256))
            if error or track is None:
                return {"ok": False, "error": error or "target track is unavailable"}
            clip = self.client.get_clip_slot_state(track_index, clip_slot_index)
        except Exception as exc:
            return {"ok": False, "error": f"Clip inspection failed: {exc}"}
        if not clip.get("success") or not clip.get("has_clip"):
            return {"ok": False, "error": clip.get("error", "target clip is not present")}
        if _text(clip.get("clip_name"), 128) == clean_name:
            return {"ok": False, "error": "The clip already has that name; no proposal is needed."}
        proposal = self._proposal(action="rename_clip", track_index=track_index, track_name=str(track.get("name", "")), clip_slot_index=clip_slot_index, before_clip=clip, new_name=clean_name, session_id=session_id)
        proposal["after_clip"] = {**deepcopy(clip), "clip_name": clean_name}
        return {"ok": True, "proposal": proposal}

    def _failed(self, proposal: dict[str, Any], key: str, error: str, *, readback: Any = None, correlation_id: str = "", timer: StageTimer | None = None) -> dict[str, Any]:
        _finish(key)
        return {"ok": False, "error": error, "receipt": {"schema": RECEIPT_SCHEMA, "receipt_id": f"receipt-{uuid.uuid4().hex}", "action_id": proposal.get("action_id"), "action": proposal.get("action"), "status": "failed", "verified": False, "timestamp": time.time(), "target": {"track_index": proposal.get("track_index"), "track_name": proposal.get("track_name"), "clip_slot_index": proposal.get("clip_slot_index")}, "readback": readback, "error": error, "correlation_id": resolve_correlation_id(correlation_id), "retry_safe": "unsafe", "stage_timings_ms": timer.as_ms() if timer else {}}}

    def execute(self, proposal: dict[str, Any], *, confirm_token: str, session_id: str, idempotency_key: str = "", correlation_id: str = "") -> dict[str, Any]:
        timer = StageTimer()
        if not isinstance(proposal, dict) or proposal.get("schema") != PROPOSAL_SCHEMA or proposal.get("action") != "rename_clip":
            return {"ok": False, "error": "A valid clip rename proposal is required."}
        if str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required for this exact clip rename."}
        key = _text(idempotency_key or proposal.get("action_id"), 256)
        if not key or not _reserve(key):
            return {"ok": False, "error": "This clip rename was already executed or is already in progress."}
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_clip_rename", text=_proposal_text(proposal)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used clip rename confirmation token."}
        try:
            state = _snapshot(self.client)
            track, error = _find_track(state, int(proposal["track_index"]), str(proposal.get("track_name", "")))
            current = self.client.get_clip_slot_state(int(proposal["track_index"]), int(proposal["clip_slot_index"])) if not error and track else {"success": False, "error": error or "target track unavailable"}
            timer.mark("snapshot")
            if not _same_clip(proposal.get("before_clip") or {}, current):
                return self._failed(proposal, key, "Clip changed before rename; no write was sent.", readback=current, correlation_id=correlation_id, timer=timer)
            if not self.client.set_clip_name(int(proposal["track_index"]), int(proposal["clip_slot_index"]), str(proposal["new_name"])):
                return self._failed(proposal, key, "AbletonOSC did not accept clip renaming.", correlation_id=correlation_id, timer=timer)
            timer.mark("write")
            time.sleep(0.05)
            readback = self.client.get_clip_slot_state(int(proposal["track_index"]), int(proposal["clip_slot_index"]))
            timer.mark("readback")
            verified = bool(readback.get("success") and readback.get("clip_name") == proposal.get("new_name") and _same_clip(proposal.get("after_clip") or {}, readback))
            _finish(key)
            receipt = {"schema": RECEIPT_SCHEMA, "receipt_id": f"receipt-{uuid.uuid4().hex}", "action_id": proposal.get("action_id"), "action": "rename_clip", "idempotency_key": key, "status": "applied" if verified else "failed_verification", "verified": verified, "timestamp": time.time(), "target": {"track_index": proposal.get("track_index"), "track_name": proposal.get("track_name"), "clip_slot_index": proposal.get("clip_slot_index")}, "before_clip": proposal.get("before_clip"), "after_clip": proposal.get("after_clip"), "readback": readback, "correlation_id": resolve_correlation_id(correlation_id), "retry_safe": classify_retry_safety(verified=verified, status="applied" if verified else "failed_verification"), "stage_timings_ms": timer.as_ms()}
            return {"ok": verified, "error": None if verified else "Clip rename was sent but readback verification failed.", "receipt": receipt}
        except Exception as exc:
            return self._failed(proposal, key, f"Clip rename failed: {exc}", correlation_id=correlation_id, timer=timer)

    def propose_undo(self, receipt: dict[str, Any], *, session_id: str) -> dict[str, Any]:
        if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("status") != "applied" or not receipt.get("verified"):
            return {"ok": False, "error": "Only a verified applied clip rename can be undone."}
        target = receipt.get("target") or {}
        try:
            state = _snapshot(self.client)
            track, track_error = _find_track(state, int(target["track_index"]), str(target.get("track_name", "")))
        except Exception as exc:
            return {"ok": False, "error": f"Undo target inspection failed: {exc}"}
        if track_error or track is None:
            return {"ok": False, "error": track_error or "Undo target track is no longer present; undo is stale."}
        current = self.client.get_clip_slot_state(int(target["track_index"]), int(target["clip_slot_index"]))
        if not _same_clip(receipt.get("after_clip") or {}, current):
            return {"ok": False, "error": "Clip changed since the rename receipt; undo is stale."}
        before = receipt.get("before_clip")
        if not isinstance(before, dict):
            return {"ok": False, "error": "Rename receipt has no prior clip identity for undo."}
        proposal = self._proposal(action="undo_rename_clip", track_index=int(target["track_index"]), track_name=str(target.get("track_name", "")), clip_slot_index=int(target["clip_slot_index"]), before_clip=current, new_name=_text(before.get("clip_name"), 128), session_id=session_id, source_receipt_id=str(receipt.get("receipt_id", "")))
        proposal["after_clip"] = before
        return {"ok": True, "proposal": proposal}

    def execute_undo(self, proposal: dict[str, Any], *, confirm_token: str, session_id: str, idempotency_key: str = "", correlation_id: str = "") -> dict[str, Any]:
        if not isinstance(proposal, dict) or proposal.get("schema") != UNDO_PROPOSAL_SCHEMA or proposal.get("action") != "undo_rename_clip":
            return {"ok": False, "error": "A valid clip rename undo proposal is required."}
        if str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "status": "requires_confirmation", "error": "Explicit confirmation is required for this exact clip rename undo."}
        key = _text(idempotency_key or proposal.get("action_id"), 256)
        if not key or not _reserve(key):
            return {"ok": False, "error": "This clip rename undo was already executed or is already in progress."}
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_clip_rename", text=_proposal_text(proposal)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used clip rename undo confirmation token."}
        try:
            raw_target = proposal.get("target")
            target = raw_target if isinstance(raw_target, dict) else {
                "track_index": proposal.get("track_index"),
                "track_name": proposal.get("track_name", ""),
                "clip_slot_index": proposal.get("clip_slot_index"),
            }
            state = _snapshot(self.client)
            track, track_error = _find_track(state, int(target["track_index"]), str(target.get("track_name", "")))
            if track_error or track is None:
                return self._failed(proposal, key, track_error or "Undo target track is no longer present; no write was sent.", correlation_id=correlation_id)
            current = self.client.get_clip_slot_state(int(target["track_index"]), int(target["clip_slot_index"]))
            if not _same_clip(proposal.get("before_clip") or {}, current):
                return self._failed(proposal, key, "Clip changed before rename undo; no write was sent.", readback=current, correlation_id=correlation_id)
            if not self.client.set_clip_name(int(target["track_index"]), int(target["clip_slot_index"]), str(proposal["new_name"])):
                return self._failed(proposal, key, "AbletonOSC did not accept clip rename undo.", correlation_id=correlation_id)
            time.sleep(0.05)
            readback = self.client.get_clip_slot_state(int(target["track_index"]), int(target["clip_slot_index"]))
            verified = bool(readback.get("success") and _same_clip(proposal.get("after_clip") or {}, readback))
            _finish(key)
            receipt = {"schema": RECEIPT_SCHEMA, "receipt_id": f"receipt-{uuid.uuid4().hex}", "action_id": proposal.get("action_id"), "action": "undo_rename_clip", "idempotency_key": key, "status": "applied" if verified else "failed_verification", "verified": verified, "timestamp": time.time(), "target": target, "readback": readback, "source_receipt_id": proposal.get("source_receipt_id", ""), "retry_safe": classify_retry_safety(verified=verified, status="applied" if verified else "failed_verification")}
            return {"ok": verified, "error": None if verified else "Clip rename undo was sent but readback verification failed.", "receipt": receipt}
        except Exception as exc:
            return self._failed(proposal, key, f"Clip rename undo failed: {exc}", correlation_id=correlation_id)


__all__ = ["ClipRenameActionService", "PROPOSAL_SCHEMA", "UNDO_PROPOSAL_SCHEMA", "RECEIPT_SCHEMA"]
