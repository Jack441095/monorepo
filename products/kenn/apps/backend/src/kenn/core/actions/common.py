"""Shared state, locking, and lookup utilities for Ableton action services."""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from threading import Lock
from typing import Any

from kenn.core.idempotency_bounds import prune_if_needed
from kenn.core.receipt_contract import resolve_correlation_id

RECEIPT_SCHEMA = "kenn.ableton_action_receipt.v1"

_USED_IDEMPOTENCY_KEYS: set[str] = set()
_IN_FLIGHT_IDEMPOTENCY_KEYS: set[str] = set()
_RECEIPTS: dict[str, dict[str, Any]] = {}
_PROPOSALS_BY_TOKEN: dict[str, dict[str, Any]] = {}
_ACTION_LOCK = Lock()


def _cleanup_memory() -> None:
    now = time.time()
    with _ACTION_LOCK:
        expired_tokens = [
            token for token, proposal in _PROPOSALS_BY_TOKEN.items()
            if float((proposal.get("confirmation_meta") or {}).get("expires_at", 0)) <= now
        ]
        for token in expired_tokens:
            _PROPOSALS_BY_TOKEN.pop(token, None)
        if len(_PROPOSALS_BY_TOKEN) > 10_000:
            for token in list(_PROPOSALS_BY_TOKEN)[: len(_PROPOSALS_BY_TOKEN) - 10_000]:
                _PROPOSALS_BY_TOKEN.pop(token, None)
        prune_if_needed(_USED_IDEMPOTENCY_KEYS)
        if len(_RECEIPTS) > 10_000:
            for receipt_id in list(_RECEIPTS)[: len(_RECEIPTS) - 10_000]:
                _RECEIPTS.pop(receipt_id, None)


def runtime_state_counts() -> dict[str, int]:
    """Return privacy-safe bounded-state counts for health/soak diagnostics."""
    _cleanup_memory()
    with _ACTION_LOCK:
        return {
            "pending_proposals": len(_PROPOSALS_BY_TOKEN),
            "action_receipts": len(_RECEIPTS),
            "pending_proposals_limit": 10_000,
            "action_receipts_limit": 10_000,
        }


def _finish_idempotency_key(key: str) -> None:
    """Release an in-flight key and consume it after confirmation.

    Once a confirmation has been consumed, a retry must create a new proposal
    even when the Live call failed or raised. Otherwise an uncertain write
    could be repeated after a timeout or exception.
    """
    with _ACTION_LOCK:
        _USED_IDEMPOTENCY_KEYS.add(key)
        _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)


def _failed_receipt(
    proposal: dict[str, Any],
    key: str,
    error: str,
    *,
    retry_safe: str = "unsafe",
    correlation_id: str = "",
    stage_timings_ms: dict[str, float] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": f"receipt-{uuid.uuid4().hex}",
        "action_id": proposal.get("action_id") or proposal.get("id"),
        "action": proposal.get("action") or proposal.get("operation"),
        "idempotency_key": key,
        "status": "failed",
        "verified": False,
        "timestamp": time.time(),
        "target": {
            field: proposal[field]
            for field in (
                "target",
                "track_index",
                "track_name",
                "device_index",
                "device_name",
                "parameter",
                "scene_index",
                "scene_name",
                "clip_slot_index",
                "locator_name",
                "locator_time_beats",
                "previous_track_index",
                "previous_track_name",
                "previous_device_index",
                "previous_device_name",
            )
            if field in proposal
        },
        "before": proposal.get("before"),
        "requested": proposal.get("after"),
        "readback": None,
        "error": error,
        "retry_safe": retry_safe,
        "correlation_id": resolve_correlation_id(correlation_id or proposal.get("correlation_id")),
        "stage_timings_ms": stage_timings_ms or {},
    }


def _state_version(state: dict[str, Any], *, track: dict[str, Any] | None = None) -> str:
    stable = {
        "status": state.get("status"),
        "tempo": state.get("tempo"),
        "is_playing": state.get("is_playing"),
        "track": {
            key: track.get(key)
            for key in ("index", "name", "volume", "pan", "muted", "soloed", "armed", "devices")
        } if track else None,
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _find_track(
    state: dict[str, Any], track_index: int, track_name: str = ""
) -> tuple[dict[str, Any] | None, str | None]:
    tracks = [track for track in state.get("tracks", []) if isinstance(track, dict)]
    matches = [track for track in tracks if track.get("index", track.get("track_index")) == track_index]
    if len(matches) != 1:
        return None, "track index is not present exactly once in the current Live snapshot"
    track = matches[0]
    if track_name and str(track.get("name", "")) != track_name:
        return None, "track name changed since the proposal was created"
    return track, None


def _find_scene(
    state: dict[str, Any], scene_index: int, scene_name: str = ""
) -> tuple[dict[str, Any] | None, str | None]:
    scenes = [scene for scene in state.get("scenes", []) if isinstance(scene, dict)]
    matches = [scene for scene in scenes if scene.get("index") == scene_index]
    if len(matches) != 1:
        return None, "scene index is not present exactly once in the current Live snapshot"
    scene = matches[0]
    if scene_name and str(scene.get("name", "")) != scene_name:
        return None, "scene name changed since the proposal was created"
    return scene, None


def _find_return_track(
    return_tracks: list[dict[str, Any]], return_track_index: int, return_track_name: str = ""
) -> tuple[dict[str, Any] | None, str | None]:
    matches = [rt for rt in return_tracks if rt.get("index") == return_track_index]
    if len(matches) != 1:
        return None, "return-track index is not present exactly once in the current Live session"
    return_track = matches[0]
    if return_track_name and str(return_track.get("name", "")) != return_track_name:
        return None, "return-track name changed since the proposal was created"
    return return_track, None


def _resolve_return_track_by_name(
    return_tracks: list[dict[str, Any]], name: str
) -> tuple[dict[str, Any] | None, str | None]:
    lowered = name.strip().lower()
    exact = [rt for rt in return_tracks if str(rt.get("name", "")).strip().lower() == lowered]
    if len(exact) == 1:
        return exact[0], None
    if len(exact) > 1:
        return None, f"More than one return track is named {name!r}; specify the exact return-track index."
    if re.fullmatch(r"[a-l]", lowered):
        # "send A", "send B": Live letters sends by the return's position, whatever it's called. A substring match
        # would find the "a" in "B-Delay" too.
        by_letter = [rt for rt in return_tracks if rt.get("index") == ord(lowered) - ord("a")]
        if len(by_letter) == 1:
            return by_letter[0], None
    # "b delay" for "B-Delay": compare words, not punctuation.
    words = " ".join(re.findall(r"[a-z0-9]+", lowered))
    substring = [rt for rt in return_tracks
                 if words and words in " ".join(re.findall(r"[a-z0-9]+", str(rt.get("name", "")).lower()))]
    if len(substring) == 1:
        return substring[0], None
    if len(substring) > 1:
        return None, f"More than one return track's name contains {name!r}; specify the exact return-track index."
    return None, f"No return track matching {name!r} exists in the current Live session."


def _text(proposal: dict[str, Any]) -> str:
    return "|".join(
        str(proposal.get(key, ""))
        for key in ("action", "track_index", "track_name", "before", "after", "session_version")
    )
