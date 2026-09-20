"""Inter-Track Sidechain & Frequency Carving Proposal Planner for KENN.

Generates strongly-typed multi-track macro batch proposals (`kenn.batch_action_proposal.v1`)
for Kick-Bass sidechain ducking and Lead Vocal frequency carving across masking partners.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from kenn.core.live_control_planner import LiveControlPlanner
from kenn.core.track_classifier import classify_track_context

logger = logging.getLogger(__name__)


def find_track_by_role(tracks: List[Dict[str, Any]], target_role: str) -> Optional[int]:
    """Return one unambiguous name-derived role match, never the first of many."""
    matches: list[int] = []
    for idx, trk in enumerate(tracks):
        name = trk.get("name", "")
        context = classify_track_context(
            name,
            track_index=trk.get("index") if isinstance(trk.get("index"), int) else idx,
            track_type=str(trk.get("type") or ""),
            devices=trk.get("devices") if isinstance(trk.get("devices"), list) else [],
        )
        if context["role"] == target_role and context["confidence_band"] != "low":
            matches.append(int(context["track_index"]))
    return matches[0] if len(matches) == 1 else None


def _find_device_by_family(
    tracks: List[Dict[str, Any]], track_index: int, family_token: str,
) -> Optional[int]:
    """Resolve one observed device index on the exact classified track."""
    matches: list[int] = []
    for position, track in enumerate(tracks):
        if not isinstance(track, dict):
            continue
        observed_track_index = track.get("index") if isinstance(track.get("index"), int) else position
        if observed_track_index != track_index:
            continue
        devices = track.get("devices") if isinstance(track.get("devices"), list) else []
        for device_position, device in enumerate(devices):
            if not isinstance(device, dict):
                continue
            name = str(device.get("name") or "").strip()
            index = device.get("index") if isinstance(device.get("index"), int) else device_position
            if index >= 0 and family_token.casefold() in name.casefold():
                matches.append(index)
    return matches[0] if len(matches) == 1 else None


def propose_kick_bass_sidechain(
    planner: LiveControlPlanner,
    session_tracks: List[Dict[str, Any]],
    *,
    session_id: str = "default_session",
) -> Dict[str, Any]:
    """Prepare bass-compressor settings; routing remains a separate verified step."""
    kick_idx = find_track_by_role(session_tracks, "kick")
    bass_idx = find_track_by_role(session_tracks, "sub_bass")
    if bass_idx is None:
        bass_idx = find_track_by_role(session_tracks, "bass_synth")

    if kick_idx is None or bass_idx is None:
        return {
            "ok": False,
            "error": f"Could not find both Kick and Bass tracks in session. (Kick: {kick_idx}, Bass: {bass_idx})",
        }
    compressor_idx = _find_device_by_family(session_tracks, bass_idx, "compressor")
    if compressor_idx is None:
        return {
            "ok": False,
            "error": "Could not uniquely identify an observed compressor on the classified Bass track.",
        }

    # Construct batch parameter change specs for Bass track compressor
    changes = [
        {
            "track_index": bass_idx,
            "device_index": compressor_idx,
            "device_name_contains": "compressor",
            "parameter_index": 0,  # Threshold / Enable
            "proposed_value": -16.0,
            "parameter_name": "Threshold",
            "resolve_parameter_by_name": True,
            "unit": "dB",
            "reason": (
                f"Prepare Bass (Track {bass_idx}) compressor threshold for possible ducking from "
                f"Kick (Track {kick_idx}); this does not configure or verify sidechain routing."
            ),
        },
        {
            "track_index": bass_idx,
            "device_index": compressor_idx,
            "device_name_contains": "compressor",
            "parameter_index": 1,  # Ratio
            "proposed_value": 4.0,
            "parameter_name": "Ratio",
            "resolve_parameter_by_name": True,
            "unit": ":1",
            "reason": f"Set Bass (Track {bass_idx}) compressor ratio to 4:1.",
        },
    ]

    return planner.propose_batch_parameter_changes(
        changes,
        reason=(
            f"Prepare compressor dynamics on Bass (Track {bass_idx}) for Kick (Track {kick_idx}). "
            "Sidechain routing is not configured or verified by this proposal."
        ),
        confidence=0.58,
        session_id=session_id,
    )


def propose_vocal_carving_eq(
    planner: LiveControlPlanner,
    session_tracks: List[Dict[str, Any]],
    *,
    session_id: str = "default_session",
) -> Dict[str, Any]:
    """Generate a multi-parameter batch proposal to dip 2 kHz on masking guitar/keys tracks to carve space for Lead Vocal."""
    vocal_idx = find_track_by_role(session_tracks, "vocal_lead")
    target_idx = find_track_by_role(session_tracks, "guitar")
    if target_idx is None:
        target_idx = find_track_by_role(session_tracks, "keys")
    if target_idx is None:
        target_idx = find_track_by_role(session_tracks, "synth")

    if vocal_idx is None or target_idx is None:
        return {
            "ok": False,
            "error": f"Could not find Lead Vocal and masking target track in session. (Vocal: {vocal_idx}, Target: {target_idx})",
        }
    eq_idx = _find_device_by_family(session_tracks, target_idx, "eq")
    if eq_idx is None:
        return {
            "ok": False,
            "error": "Could not uniquely identify an observed EQ on the classified masking track.",
        }

    changes = [
        {
            "track_index": target_idx,
            "device_index": eq_idx,
            "device_name_contains": "eq",
            "parameter_index": 0,  # EQ Band Frequency / Gain
            "proposed_value": -2.5,
            "parameter_name": "Band 3 Gain",
            "resolve_parameter_by_name": True,
            "unit": "dB",
            "reason": f"Dip 2.0 kHz by -2.5 dB on Track {target_idx} to carve clean vocal pocket for Lead Vocal (Track {vocal_idx}).",
        },
    ]

    return planner.propose_batch_parameter_changes(
        changes,
        reason=f"Carve 2.0 kHz frequency pocket on Track {target_idx} for Lead Vocal on Track {vocal_idx}.",
        confidence=0.58,
        session_id=session_id,
    )
