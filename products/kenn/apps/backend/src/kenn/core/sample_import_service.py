"""Confirmation-gated sample import from KENN's approved library into Ableton Live.

Follows the exact same shape as ``midi_clip_service.py``: propose (no
mutation), confirm, execute (one exact empty Session View clip slot,
verified by readback), and identity-bound undo. The one addition specific
to this action is that the proposal never carries a raw filesystem path --
only the sample's opaque id (see ``sample_library.py``'s "no raw path is
ever returned to a caller" rule). ``execute_import`` re-resolves the id back
to an absolute path itself, immediately before sending it to AbletonOSC, so
the path never needs to round-trip through an external caller.

This service never replaces an existing clip, and it depends on a real
``/live/browser/import_sample`` OSC endpoint added to the vendored
AbletonOSC fork (see ``docs/ABLETON_ASSISTANT_CURRENT_STATE.md``'s
2026-09-06 research entry for how that was found and proven live).
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

from kenn.ableton_osc_bridge import AbletonOSCClient, live_client
from kenn.core.confirmation import consume_confirmation, issue_confirmation
from kenn.core.idempotency_bounds import prune_if_needed
from kenn.core.receipt_contract import StageTimer, classify_retry_safety, resolve_correlation_id
from kenn.core.sample_library import library_root, resolve_sample, scan_sample_library

IMPORT_PROPOSAL_SCHEMA = "kenn.ableton_sample_import_proposal.v1"
REMOVE_PROPOSAL_SCHEMA = "kenn.ableton_sample_import_removal_proposal.v1"
RECEIPT_SCHEMA = "kenn.ableton_sample_import_receipt.v1"
_USED_IDEMPOTENCY_KEYS: set[str] = set()
_IN_FLIGHT_IDEMPOTENCY_KEYS: set[str] = set()
_ACTION_LOCK = Lock()


def _text(value: Any, limit: int = 512) -> str:
    return str(value or "").strip()[:limit]


def _reserve_idempotency(key: str) -> bool:
    with _ACTION_LOCK:
        if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
            return False
        _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        return True


def _finish_idempotency(key: str) -> None:
    with _ACTION_LOCK:
        _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
        _USED_IDEMPOTENCY_KEYS.add(key)
        prune_if_needed(_USED_IDEMPOTENCY_KEYS)


def _find_track(state: dict[str, Any], track_index: int, track_name: str) -> tuple[dict[str, Any] | None, str | None]:
    tracks = state.get("tracks") or []
    for track in tracks:
        if not isinstance(track, dict):
            continue
        if int(track.get("index", -1)) == track_index:
            if track_name and str(track.get("name", "")) != track_name:
                return None, "The exact Live track identity has changed since this proposal was made."
            return track, None
    return None, "The exact Live track was not found in a fresh snapshot."


def _proposal_text(proposal: dict[str, Any]) -> str:
    return (
        f"Import sample '{proposal.get('sample_filename', '')}' onto "
        f"'{proposal.get('track_name', '')}', clip slot {proposal.get('clip_slot_index')}."
    )


def _resolve_sample_path(sample_id: str) -> tuple[Path | None, str | None, str]:
    """Return (absolute_path, error, filename). Re-resolves fresh every call
    -- the proposal itself never carries a raw path."""
    root = library_root()
    if root is None:
        return None, "No sample library is configured (KENN_SAMPLE_LIBRARY_ROOT is unset or not a directory).", ""
    entries = scan_sample_library(root)
    entry = resolve_sample(entries, sample_id)
    if entry is None:
        return None, "No sample with that id was found in the configured library.", ""
    return root / entry.relative_path, None, entry.filename


class SampleImportService:
    """Import one exact sample into one exact empty Session View clip slot."""

    def __init__(self, client: AbletonOSCClient | Any = None):
        self.client = client or live_client

    def _snapshot(self) -> dict[str, Any]:
        if hasattr(self.client, "query_session_topology"):
            return self.client.query_session_topology()
        return self.client.query_session_state(include_mixer=False)

    def propose_import(
        self,
        *,
        track_index: int,
        track_name: str,
        clip_slot_index: int,
        sample_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        clean_track_name = _text(track_name, 256)
        if not clean_track_name:
            return {"ok": False, "error": "track_name is required for an exact import target"}
        try:
            track_index = int(track_index)
            clip_slot_index = int(clip_slot_index)
        except (TypeError, ValueError):
            return {"ok": False, "error": "track and clip-slot indices must be numeric"}
        if min(track_index, clip_slot_index) < 0:
            return {"ok": False, "error": "track and clip-slot indices must be non-negative"}
        clean_sample_id = _text(sample_id, 64)
        if not clean_sample_id:
            return {"ok": False, "error": "sample_id is required"}
        _, error, filename = _resolve_sample_path(clean_sample_id)
        if error:
            return {"ok": False, "error": error}
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
            clip_state = self.client.get_midi_clip_state(track_index, clip_slot_index)
        except Exception as exc:
            return {"ok": False, "error": f"Clip-slot inspection failed: {exc}"}
        if not clip_state.get("success"):
            return {"ok": False, "error": clip_state.get("error", "Clip-slot inspection failed")}
        if clip_state.get("has_clip"):
            return {"ok": False, "error": "Target clip slot already contains a clip; replacement is not enabled."}
        proposal = {
            "schema": IMPORT_PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "import_sample",
            "operation": "import_sample",
            "target": "ableton_clip_slot",
            "track_index": track_index,
            "track_name": str(track.get("name", "")),
            "clip_slot_index": clip_slot_index,
            "sample_id": clean_sample_id,
            "sample_filename": filename,
            "before": {"has_clip": False},
            "after": {"has_clip": True},
            "reason": f"Explicit request to import sample '{filename}' onto '{track.get('name', '')}', slot {clip_slot_index}.",
            "confidence": 1.0,
            "risk": "local_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
            "snapshot_exchange": dict(getattr(self.client, "last_exchange", {}) or {}),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_sample_import", text=_proposal_text(proposal))
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
            "retry_safe": retry_safe,
            "correlation_id": resolve_correlation_id(correlation_id or proposal.get("correlation_id")),
            "stage_timings_ms": stage_timings_ms or {},
        }
        return {"ok": False, "error": error, "receipt": receipt}

    def execute_import(
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
        if not isinstance(proposal, dict) or proposal.get("schema") != IMPORT_PROPOSAL_SCHEMA:
            return {"ok": False, "error": "A valid KENN sample import proposal is required."}
        if not proposal.get("requires_confirmation") or str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "error": "Explicit confirmation is required for this exact sample import proposal."}
        key = _text(idempotency_key or proposal.get("action_id"), 256)
        if not key or not _reserve_idempotency(key):
            return {"ok": False, "error": "This sample import request was already executed or is already in progress."}
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_sample_import", text=_proposal_text(proposal)):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used sample import confirmation token."}
        try:
            track_index = int(proposal["track_index"])
            clip_slot_index = int(proposal["clip_slot_index"])
            absolute_path, error, filename = _resolve_sample_path(str(proposal.get("sample_id", "")))
            if error or absolute_path is None:
                return self._failed(proposal, key, error or "Sample could not be resolved before import.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            state = self._snapshot()
            if state.get("status") != "connected":
                return self._failed(proposal, key, "Ableton Live became unavailable before sample import.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            timer.mark("snapshot")
            track, error = _find_track(state, track_index, str(proposal.get("track_name", "")))
            if error or track is None:
                return self._failed(proposal, key, error or "Target Live track is unavailable.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            current = self.client.get_midi_clip_state(track_index, clip_slot_index)
            if not current.get("success"):
                return self._failed(proposal, key, current.get("error", "Clip-slot readback failed before import"), readback=current, correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            if current.get("has_clip"):
                return self._failed(proposal, key, "Target clip slot changed and now contains a clip.", readback=current, correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            result = self.client.import_sample_to_clip_slot(track_index, clip_slot_index, str(absolute_path))
            if not result.get("success"):
                return self._failed(proposal, key, result.get("error", "AbletonOSC did not accept the sample import."), correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            timer.mark("write")
            time.sleep(0.1)
            readback = self.client.get_midi_clip_state(track_index, clip_slot_index)
            timer.mark("readback")
            verified = bool(readback.get("success") and readback.get("has_clip"))
            _finish_idempotency(key)
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "receipt_id": f"receipt-{uuid.uuid4().hex}",
                "action_id": proposal.get("action_id"),
                "action": "import_sample",
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
                "sample_id": proposal.get("sample_id", ""),
                "sample_filename": filename,
                "undo_payload": {
                    "action": "remove_sample_clip",
                    "track_index": track_index,
                    "track_name": str(proposal.get("track_name", "")),
                    "clip_slot_index": clip_slot_index,
                    "source_receipt_id": "pending",
                },
                "correlation_id": correlation_id,
                "retry_safe": classify_retry_safety(verified=verified, status="applied" if verified else "failed_verification"),
                "stage_timings_ms": timer.as_ms(),
            }
            receipt["undo_payload"]["source_receipt_id"] = receipt["receipt_id"]
            return {"ok": verified, "error": None if verified else "Sample import was sent but readback verification failed.", "receipt": receipt}
        except Exception as exc:
            return self._failed(proposal, key, f"Sample import failed: {exc}", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())

    def propose_undo(self, receipt: dict[str, Any], *, session_id: str) -> dict[str, Any]:
        if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
            return {"ok": False, "error": "A valid KENN sample import receipt is required for undo."}
        if receipt.get("status") != "applied" or not receipt.get("verified"):
            return {"ok": False, "error": "Only a verified applied sample import can be undone."}
        target = receipt.get("target") or {}
        try:
            track_index = int(target["track_index"])
            clip_slot_index = int(target["clip_slot_index"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "Receipt has no complete clip-slot identity for undo."}
        try:
            state = self.client.query_session_topology() if hasattr(self.client, "query_session_topology") else self.client.query_session_state(include_mixer=False)
            track, track_error = _find_track(state, track_index, str(target.get("track_name", "")))
        except Exception as exc:
            return {"ok": False, "error": f"Undo target inspection failed: {exc}"}
        if track_error or track is None:
            return {"ok": False, "error": track_error or "Undo target track is no longer present; undo is stale."}
        current = self.client.get_midi_clip_state(track_index, clip_slot_index)
        if not current.get("success") or not current.get("has_clip"):
            return {"ok": False, "error": "Imported clip is no longer present as recorded; undo is stale."}
        proposal = {
            "schema": REMOVE_PROPOSAL_SCHEMA,
            "action_id": f"action-{uuid.uuid4().hex}",
            "action": "remove_sample_clip",
            "operation": "remove_sample_clip",
            "target": "ableton_clip_slot",
            "track_index": track_index,
            "track_name": str(target.get("track_name", "")),
            "clip_slot_index": clip_slot_index,
            "source_receipt_id": str(receipt.get("receipt_id", "")),
            "requires_confirmation": True,
            "timestamp": time.time(),
        }
        token, meta = issue_confirmation(session_id=session_id, service_id="ableton_sample_import", text=_proposal_text({**proposal, "sample_filename": "the imported sample"}))
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
            return {"ok": False, "error": "A valid KENN sample import removal proposal is required."}
        if not proposal.get("requires_confirmation") or str(proposal.get("confirmation_token", "")) != confirm_token:
            return {"ok": False, "error": "Explicit confirmation is required for this exact removal."}
        key = _text(idempotency_key or proposal.get("action_id"), 256)
        if not key or not _reserve_idempotency(key):
            return {"ok": False, "error": "This removal was already executed or is already in progress."}
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_sample_import", text=_proposal_text({**proposal, "sample_filename": "the imported sample"})):
            with _ACTION_LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used removal confirmation token."}
        try:
            track_index = int(proposal["track_index"])
            clip_slot_index = int(proposal["clip_slot_index"])
            state = self.client.query_session_topology() if hasattr(self.client, "query_session_topology") else self.client.query_session_state(include_mixer=False)
            track, track_error = _find_track(state, track_index, str(proposal.get("track_name", "")))
            if track_error or track is None:
                return self._failed(proposal, key, track_error or "Undo target track is no longer present; no deletion was sent.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            current = self.client.get_midi_clip_state(track_index, clip_slot_index)
            timer.mark("snapshot")
            if not current.get("success") or not current.get("has_clip"):
                return self._failed(proposal, key, "Clip changed before undo; no deletion was sent.", readback=current, correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            if not self.client.delete_midi_clip(track_index, clip_slot_index):
                return self._failed(proposal, key, "AbletonOSC did not accept clip deletion.", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())
            timer.mark("write")
            time.sleep(0.05)
            readback = self.client.get_midi_clip_state(track_index, clip_slot_index)
            timer.mark("readback")
            verified = bool(readback.get("success") and not readback.get("has_clip"))
            _finish_idempotency(key)
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "receipt_id": f"receipt-{uuid.uuid4().hex}",
                "action_id": proposal.get("action_id"),
                "action": "remove_sample_clip",
                "idempotency_key": key,
                "status": "applied" if verified else "failed_verification",
                "verified": verified,
                "timestamp": time.time(),
                "target": {
                    "track_index": track_index,
                    "track_name": str(proposal.get("track_name", "")),
                    "clip_slot_index": clip_slot_index,
                },
                "before": {"has_clip": True},
                "requested": {"has_clip": False},
                "readback": readback,
                "source_receipt_id": proposal.get("source_receipt_id", ""),
                "correlation_id": correlation_id,
                "retry_safe": classify_retry_safety(verified=verified, status="applied" if verified else "failed_verification"),
                "stage_timings_ms": timer.as_ms(),
            }
            return {"ok": verified, "error": None if verified else "Deletion was sent but readback verification failed.", "receipt": receipt}
        except Exception as exc:
            return self._failed(proposal, key, f"Sample clip removal failed: {exc}", correlation_id=correlation_id, stage_timings_ms=timer.as_ms())


__all__ = [
    "IMPORT_PROPOSAL_SCHEMA",
    "REMOVE_PROPOSAL_SCHEMA",
    "RECEIPT_SCHEMA",
    "SampleImportService",
]
