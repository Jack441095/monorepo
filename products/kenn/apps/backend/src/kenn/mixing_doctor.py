"""Read-only Live observer and bounded session-health advisories.

One background poll supplies the card and reviews. Names and faders can
suggest listening checks, but cannot measure masking, clipping or phase.
"""

from __future__ import annotations

import copy
import logging
import math
import threading
import time
from typing import Any, Dict, List

logger = logging.getLogger("kenn.mixing_doctor")
_lock = threading.Lock()
_thread: threading.Thread | None = None
_running = False
_realtime_enabled = True
_poll_generation = 0
_latest_session_state: Dict[str, Any] = {"status": "unknown", "tracks": []}
# Six seconds allows two missed 2 s polls before observations cease to be current.
MAX_SESSION_AGE_SECONDS = 6.0
_POLL_SECONDS = 2.0
_NEAR_CEILING_METER = 0.98  # normalized Live post-fader meter units, not dBFS


def set_realtime_enabled(enabled: bool) -> None:
    """Pause polling and invalidate pending reads; resume requires a new observation."""
    global _realtime_enabled, _poll_generation, _latest_session_state
    with _lock:
        _realtime_enabled = bool(enabled)
        _poll_generation += 1
        _latest_session_state = {"status": "unknown" if enabled else "paused", "tracks": []}


def is_realtime_enabled() -> bool:
    """Return whether the observer may issue read-only queries."""
    with _lock:
        return _realtime_enabled


def get_mixing_alerts() -> List[Dict[str, Any]]:
    """Return detached advisories only while their shared observation is current."""
    return get_latest_session_state().get("mixing_alerts", [])


def get_latest_session_state() -> Dict[str, Any]:
    """Return an expiring, detached observation without querying Live or local logs."""
    with _lock:
        snapshot = copy.deepcopy(_latest_session_state)
        enabled = _realtime_enabled
    started = snapshot.pop("_sampled_at_monotonic", None)
    age = max(0.0, time.monotonic() - started) if started is not None else None
    current = enabled and snapshot.get("status") == "connected" and age is not None and age <= MAX_SESSION_AGE_SECONDS
    snapshot["realtime_enabled"] = enabled
    snapshot["freshness"] = {
        "status": "current" if current else "unavailable",
        "age_seconds": round(age, 3) if age is not None else None,
        "max_current_age_seconds": MAX_SESSION_AGE_SECONDS,
        "current_for_diagnosis": current,
    }
    if not current:
        # Retaining names/meters here would let older consumers use stale facts.
        snapshot["status"] = "paused" if not enabled else "stale" if snapshot.get("status") == "connected" else snapshot.get("status", "unknown")
        snapshot["tracks"] = []
        snapshot["mixing_alerts"] = []
        for key in ("tempo", "is_playing", "selected_track_index", "selected_track_kind", "selected_device_index",
                    "selected_device_track_index", "selected_device_name", "root_note", "scale_name",
                    "session_name", "set_name", "project_dir", "als_path", "return_tracks", "master_track", "scenes"):
            snapshot.pop(key, None)
    return snapshot


def start_mixing_doctor() -> None:
    """Start the single observer; callers must not start a separate Live poller."""
    global _thread, _running
    with _lock:
        if _running or (_thread and _thread.is_alive()):
            # A thread still exiting owns the socket; don't create a competing poller.
            return
        _running = True
        _thread = threading.Thread(target=_audit_loop, daemon=True)
        _thread.start()


def stop_mixing_doctor() -> None:
    """Invalidate cached and in-flight observations before stopping the daemon."""
    global _running, _poll_generation, _latest_session_state
    with _lock:
        _running = False
        _poll_generation += 1
        _latest_session_state = {"status": "unknown", "tracks": []}
    if _thread and _thread.is_alive():
        _thread.join(timeout=1.0)  # seconds: don't hold shutdown on an OSC timeout


def _poll_once(client: Any) -> None:
    """Publish one read and its audits atomically; failures replace old findings."""
    global _latest_session_state
    with _lock:
        if not _realtime_enabled:
            # The producer paused analysis; even a manual refresh must remain cache-only.
            return
        generation = _poll_generation
    started, observed_at = time.monotonic(), time.time()
    try:
        # Force a new read so the timestamp never refreshes a transport-cache entry.
        state = client.query_session_state(include_meters=True, force_refresh=True)
        if not isinstance(state, dict) or not isinstance(state.get("tracks"), list) or state.get("status") != "connected":
            # Dispatch is not a reply, and malformed/offline reads cannot preserve old evidence.
            state = {"status": "offline", "tracks": []}
        else:
            state = copy.deepcopy(state)
        if state.get("status") == "connected" and not state.get("session_name"):
            try:
                from kenn.core.ableton_project_detector import detect_active_ableton_project
                proj = detect_active_ableton_project()
                if proj:
                    state["session_name"] = proj.get("project_name") or "Untitled"
                    state["project_dir"] = proj.get("project_dir", "")
                    state["als_path"] = proj.get("als_path", "")
            except Exception:
                pass
        alerts = _run_session_audits(state["tracks"]) if state["status"] == "connected" else []
        from kenn.core.live_world_model import fingerprint
        state_fingerprint = fingerprint(state)
    except Exception:
        # A failed read means unknown Live state, not a clean mix or continued connection.
        logger.warning("Live observer read failed; cached observations invalidated", exc_info=False)
        state, alerts, state_fingerprint = {"status": "offline", "tracks": []}, [], ""
    with _lock:
        if generation != _poll_generation:
            # Pause/resume or shutdown revoked ownership while the read was in flight.
            return
        previous = _latest_session_state
        revision = int(previous.get("state_revision", 0)) + (previous.get("state_fingerprint") != state_fingerprint)
        _latest_session_state = {
            **state, "mixing_alerts": alerts, "state_fingerprint": state_fingerprint,
            "state_revision": revision, "observed_at_epoch": observed_at, "_sampled_at_monotonic": started,
        }


def _audit_loop() -> None:
    """Read Live every two seconds while enabled; no control actions are issued."""
    from kenn.ableton_osc_bridge import live_client
    while True:
        with _lock:
            if not _running:
                # Shutdown revoked the cache before we leave this thread.
                return
        _poll_once(live_client)
        time.sleep(_POLL_SECONDS)


def _number(value: Any) -> float | None:
    """Accept finite numeric OSC observations; missing or malformed replies stay unknown."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        # Booleans and numeric strings are not meter or fader measurements.
        return None
    return float(value) if math.isfinite(value) else None


def _run_session_audits(tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return advisory checks from supplied fields, without writes or shared-store changes."""
    alerts: List[Dict[str, Any]] = []
    low_end_tracks, soloed_tracks = [], []
    for track in tracks:
        if not isinstance(track, dict) or type(track.get("index")) is not int or track["index"] < 0:
            # A missing host index cannot safely be replaced by this list's position.
            continue
        idx = track["index"]
        name = str(track.get("name") or "").strip()
        vol, pan = _number(track.get("volume")), _number(track.get("pan"))
        if track.get("soloed") is True or track.get("soloed") == 1:
            soloed_tracks.append((idx, name))
        meters = [value for value in (_number(track.get("output_meter_level")), _number(track.get("output_meter_right")))
                  if value is not None and 0.0 <= value <= 1.0]
        if meters and max(meters) >= _NEAR_CEILING_METER:
            alerts.append({
                "id": f"meter-headroom-{idx}", "type": "headroom", "track_index": idx, "track_name": name,
                "severity": "warning", "evidence_kind": "observed",
                "message": f"Track '{name}' latest output-meter reading is {max(meters):.2f} on Ableton's 0.0-1.0 scale, near the meter ceiling.",
                "fix_action": "Play the loudest section and inspect a true-peak meter before changing gain or limiting.",
                "fix_label": "Inspect Track Headroom",
            })
        # Panning is an observed mixer position; it says nothing about mono phase.
        if pan is not None and 0.85 < abs(pan) <= 1.0:  # normalized pan position, near hard left/right
            alerts.append({
                "id": f"pan-{idx}", "type": "panning", "track_index": idx, "track_name": name,
                "severity": "info", "evidence_kind": "observed",
                "message": f"Track '{name}' pan position is {pan:.2f} on Live's -1.0 to 1.0 scale. Phase has not been measured.",
                "fix_action": "Confirm the stereo placement is intentional and compare playback in mono.",
                "fix_label": "Check Stereo Placement",
            })
        name_lower = name.lower()
        # Names only suggest a role. An unknown mute reply cannot mean unmuted.
        if track.get("muted") in (False, 0) and track.get("muted") is not None and any(term in name_lower for term in ("kick", "sub", "bass", "low")):
            if vol is not None and 0.75 < vol <= 1.0:  # normalized fader position, not measured signal level
                low_end_tracks.append((idx, name, vol))
    # Bound the output in large sessions; pairs beyond 64 advisories remain unreported.
    for i, (idx1, name1, vol1) in enumerate(low_end_tracks):
        for idx2, name2, vol2 in low_end_tracks[i + 1:]:
            if len(alerts) >= 64:
                break
            alerts.append({
                "id": f"low-end-overlap-{idx1}-{idx2}", "type": "low_end_overlap_candidate", "track_indices": [idx1, idx2],
                "severity": "info", "evidence_kind": "inferred",
                "message": f"Likely low-end overlap candidates: '{name1}' ({vol1:.2f}) and '{name2}' ({vol2:.2f}) are unmuted and high on the faders. Roles are inferred from names; this is not an audio masking measurement.",
                "fix_action": "Compare time-aligned stems in Mix Review or audition these tracks together before changing EQ or level.",
                "fix_label": "Inspect Low-End Relationship",
            })
    if soloed_tracks:
        names = ", ".join(f"'{name}'" for _idx, name in soloed_tracks)
        alerts.append({
            "id": "solo-left-on", "type": "solo", "track_indices": [idx for idx, _name in soloed_tracks],
            "severity": "warning", "evidence_kind": "observed",
            "message": f"{len(soloed_tracks)} track(s) are soloed ({names}); this can hide parts of the mix.",
            "fix_action": "Confirm these solos are intentional before reviewing the full mix.", "fix_label": "Inspect Solo State",
        })
    return alerts
