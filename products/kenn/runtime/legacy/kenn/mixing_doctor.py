"""Mixing Doctor background auditor daemon for KENN.

Periodically queries Ableton Live 12 track structure and parameter levels
to detect clipping, masking, and stereo phase compatibility issues.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Dict, List

logger = logging.getLogger("kenn.mixing_doctor")

# In-memory alert store
_alerts: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
_thread: threading.Thread | None = None
_running = False

# D1.6 (docs/KENN_FUTURE_PLAN.md Phase 1) -- the live session-state card in
# chat needs the same track data this loop already fetches every 2s to run
# its audits. Caching it here instead of running a second independent
# poller avoids doubling the UDP query traffic to Ableton for data this
# loop already has in hand.
_latest_session_state: Dict[str, Any] = {"status": "unknown", "tracks": []}


def get_mixing_alerts() -> List[Dict[str, Any]]:
    """Retrieve all active mixing doctor alerts."""
    with _lock:
        return list(_alerts.values())


def get_latest_session_state() -> Dict[str, Any]:
    """Retrieve the most recent Ableton session state this loop fetched.
    "unknown" status with an empty track list before the loop has polled
    even once (e.g. the daemon was just started, or is disabled)."""
    with _lock:
        return dict(_latest_session_state)


def start_mixing_doctor() -> None:
    """Start the background auditor loop thread."""
    global _thread, _running
    with _lock:
        if _running:
            return
        _running = True
        _thread = threading.Thread(target=_audit_loop, daemon=True)
        _thread.start()
        logger.info("KENN Mixing Doctor background auditor started.")


def stop_mixing_doctor() -> None:
    """Stop the background auditor loop thread."""
    global _running
    with _lock:
        _running = False
    if _thread and _thread.is_alive():
        _thread.join(timeout=1.0)
    logger.info("KENN Mixing Doctor background auditor stopped.")


def _audit_loop() -> None:
    """Periodic audit loop querying Ableton Live session state."""
    while True:
        with _lock:
            if not _running:
                break

        try:
            from kenn.ableton_osc_bridge import live_client
            state = live_client.query_session_state()
            with _lock:
                global _latest_session_state
                _latest_session_state = state
            if state.get("status") in {"connected", "dispatched"}:
                tracks = state.get("tracks") or []
                _run_session_audits(tracks)
        except Exception as exc:
            logger.error("Error in Mixing Doctor audit loop: %s", exc)

        time.sleep(2.0)


def _run_session_audits(tracks: List[Dict[str, Any]]) -> None:
    """Run DSP/Mixing audits on tracks retrieved via OSC."""
    new_alerts: Dict[str, Dict[str, Any]] = {}

    low_end_tracks = []
    soloed_tracks = []

    for idx, track in enumerate(tracks):
        name = str(track.get("name") or "").strip()
        vol = float(track.get("volume") or 0.0)
        pan = float(track.get("pan") or 0.0)

        # Collect soloed tracks for the "left soloed" check below (D2.1,
        # docs/KENN_FUTURE_PLAN.md Phase 2) -- state-based, like every
        # other detector here: this loop only ever sees fader/mixer
        # parameter state over OSC (volume/pan/mute/solo/arm), never
        # actual audio signal, so anything requiring real DSP measurement
        # (dynamic range, a masking heat map, a spectral gap vs. a
        # reference) genuinely isn't buildable on this data without a
        # different capture path -- left honest rather than faked with a
        # volume-only proxy that wouldn't actually measure what it claims to.
        if bool(track.get("soloed")):
            soloed_tracks.append((idx, name))

        # 1. Clipping Audit: Volume level exceeds 1.0 (above 0 dB)
        if vol > 1.0:
            alert_id = f"clip-{idx}"
            new_alerts[alert_id] = {
                "id": alert_id,
                "type": "clipping",
                "track_index": idx,
                "track_name": name,
                "severity": "critical",
                "message": f"Track '{name}' volume ({vol:.2f}) is above 1.0, which will cause digital clipping.",
                "fix_action": f"set_volume on track {idx} to volume 0.85",
                "fix_label": "Reduce Volume to 0.85",
            }

        # 2. Extreme Stereo Panning Audit: Panned hard left/right (potential mono-sum phase cancellation)
        name_lower = name.lower()
        is_essential_mono = any(term in name_lower for term in {"kick", "bass", "sub", "vocal", "lead"})
        if is_essential_mono and abs(pan) > 0.85:
            alert_id = f"pan-{idx}"
            new_alerts[alert_id] = {
                "id": alert_id,
                "type": "phase",
                "track_index": idx,
                "track_name": name,
                "severity": "warning",
                "message": f"Mono element '{name}' is panned extremely wide ({pan:.2f}), risking phase cancellation.",
                "fix_action": f"set_pan on track {idx} to pan 0.0",
                "fix_label": "Center Pan",
            }

        # Collect low-end tracks for masking checks
        if any(term in name_lower for term in {"kick", "sub", "bass", "low"}):
            if vol > 0.75:
                low_end_tracks.append((idx, name, vol))

    # 3. Low-End Frequency Masking Audit: Multiple competing sub-bass elements active at once
    if len(low_end_tracks) >= 2:
        for i in range(len(low_end_tracks)):
            for j in range(i + 1, len(low_end_tracks)):
                idx1, name1, vol1 = low_end_tracks[i]
                idx2, name2, vol2 = low_end_tracks[j]
                alert_id = f"mask-{idx1}-{idx2}"
                new_alerts[alert_id] = {
                    "id": alert_id,
                    "type": "masking",
                    "track_indices": [idx1, idx2],
                    "severity": "warning",
                    "message": f"Low-end masking detected between unmuted tracks '{name1}' ({vol1:.2f}) and '{name2}' ({vol2:.2f}).",
                    "fix_action": f"set_volume on track {idx2} to volume 0.7",
                    "fix_label": f"Dampen {name2} Volume",
                }

    # 4. Left-Soloed Audit: one or more tracks still soloed -- a common,
    # real mixing mistake (auditioning a track, then forgetting to
    # un-solo it) that silently hides the rest of the mix from whoever's
    # listening, including a client on a shared session. State-based
    # (soloed is already reported by get_track_data()), no audio
    # measurement needed.
    if soloed_tracks:
        alert_id = "solo-left-on"
        first_idx, first_name = soloed_tracks[0]
        names = ", ".join(f"'{name}'" for _idx, name in soloed_tracks)
        new_alerts[alert_id] = {
            "id": alert_id,
            "type": "solo",
            "track_indices": [idx for idx, _name in soloed_tracks],
            "severity": "warning",
            "message": (
                f"{len(soloed_tracks)} track(s) still soloed ({names}) -- "
                "the rest of the mix is silenced for anyone listening."
            ),
            "fix_action": f"unsolo track {first_idx}",
            "fix_label": f"Unsolo {first_name}" if first_name else f"Unsolo track {first_idx}",
        }

    # Update global store
    with _lock:
        global _alerts
        _alerts = new_alerts
