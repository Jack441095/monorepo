"""Modular Ableton route handlers for KENN server.

Handles /api/ableton/ping, /api/ableton/watchdog, and /api/ableton/capabilities.
"""

from __future__ import annotations

from typing import Any


def handle_ableton_ping(live_client: Any | None) -> tuple[int, dict[str, Any]]:
    """Return status code and response payload for /api/ableton/ping."""
    if live_client is None:
        return 500, {"ok": False, "error": "Ableton client not available"}
    try:
        success = live_client.ping(timeout=0.5)
        return 200, {
            "ok": True,
            "connected": bool(success),
            "state": getattr(live_client, "connection_state", "unknown"),
        }
    except Exception as exc:
        return 200, {
            "ok": False,
            "connected": False,
            "state": "disconnected",
            "error": str(exc),
        }


def handle_ableton_watchdog(live_client: Any | None) -> tuple[int, dict[str, Any]]:
    """Return status code and response payload for /api/ableton/watchdog."""
    if live_client is None:
        return 500, {"ok": False, "error": "Ableton client not available"}
    try:
        status = live_client.get_connection_status()
        return 200, {
            "ok": True,
            "watchdog": status,
        }
    except Exception as exc:
        return 200, {
            "ok": False,
            "error": str(exc),
        }


def handle_ableton_capabilities(live_client: Any | None) -> tuple[int, dict[str, Any]]:
    """Return status code and response payload for /api/ableton/capabilities."""
    if live_client is None:
        return 500, {"ok": False, "error": "Ableton client not available"}
    try:
        return 200, live_client.capability_report()
    except Exception as exc:
        return 200, {
            "schema": "kenn.abletonosc_capabilities.v1",
            "available": False,
            "host": getattr(live_client, "host", "127.0.0.1"),
            "port": getattr(live_client, "port", 11000),
            "error": str(exc),
            "verified_features": {},
            "supported_parameters": {},
        }


def handle_ableton_device_matrix(
    live_client: Any | None, without_parameters: bool = False,
) -> tuple[int, dict[str, Any]]:
    """Return status code and response payload for /api/ableton/device-matrix."""
    if live_client is None:
        return 500, {"ok": False, "status": "error", "error": "Ableton client not available"}
    try:
        report = live_client.device_matrix_report(include_parameters=not without_parameters)
        return 200, report
    except Exception as exc:
        return 200, {
            "schema": "kenn.ableton_device_matrix.v1",
            "available": False,
            "error": str(exc),
        }


def handle_osc_session(live_client: Any | None, detail: str = "") -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/osc/session."""
    if live_client is None:
        return 500, {"ok": False, "error": "Ableton client not available"}
    try:
        detail_clean = detail.strip().lower()
        topology_only = detail_clean in {"topology", "structure"}
        state = (
            live_client.query_session_topology() if topology_only else
            live_client.query_session_understanding() if detail_clean in {"understanding", "context"} else
            live_client.query_session_state()
        )
        return 200, state
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_osc_song_time(live_client: Any | None) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/osc/song-time."""
    if live_client is None:
        return 503, {"success": False, "current_song_time": None, "error": "Ableton client not available"}
    try:
        value = live_client.get_current_song_time()
        return (200 if value is not None else 503), {
            "success": value is not None,
            "current_song_time": value,
            **({"error": "Ableton did not return a readable current song position."} if value is None else {}),
        }
    except Exception as exc:
        return 503, {"success": False, "current_song_time": None, "error": str(exc)}


def handle_osc_locators(live_client: Any | None) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/osc/locators."""
    if live_client is None:
        return 503, {"success": False, "locators": [], "error": "Ableton client not available"}
    try:
        locators, available = live_client.get_locators_with_status()
        return (200 if available else 503), {
            "success": available,
            "locators": locators if available else [],
            **({"error": "Ableton did not return the current locator list."} if not available else {}),
        }
    except Exception as exc:
        return 503, {"success": False, "locators": [], "error": str(exc)}


def handle_osc_return_tracks(live_client: Any | None) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/osc/return-tracks."""
    if live_client is None:
        return 500, {"ok": False, "error": "Ableton client not available"}
    try:
        return 200, {"ok": True, "return_tracks": live_client.get_return_tracks()}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_osc_midi_clip(
    live_client: Any | None, track_index_raw: str, clip_slot_index_raw: str,
) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/osc/midi-clip."""
    try:
        track_index = int(track_index_raw)
        clip_slot_index = int(clip_slot_index_raw)
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "track_index and clip_slot_index query parameters are required."}
    if min(track_index, clip_slot_index) < 0:
        return 400, {"ok": False, "error": "track_index and clip_slot_index must be non-negative."}
    if live_client is None:
        return 503, {"ok": False, "error": "Ableton client not available"}
    try:
        result = live_client.get_midi_clip_state(track_index, clip_slot_index)
        topology = live_client.query_session_topology()
        tracks = [item for item in topology.get("tracks", []) if isinstance(item, dict)]
        track = next((item for item in tracks if int(item.get("index", -1)) == track_index), None)
        if track is not None:
            result["track_name"] = str(track.get("name", ""))
        return (200 if result.get("success") else 503), result
    except Exception as exc:
        return 503, {"ok": False, "error": str(exc)}


def handle_osc_clip_slot(
    live_client: Any | None, track_index_raw: str, clip_slot_index_raw: str,
) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/osc/clip-slot."""
    try:
        track_index = int(track_index_raw)
        clip_slot_index = int(clip_slot_index_raw)
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "track_index and clip_slot_index query parameters are required."}
    if min(track_index, clip_slot_index) < 0:
        return 400, {"ok": False, "error": "track_index and clip_slot_index must be non-negative."}
    if live_client is None:
        return 503, {"ok": False, "error": "Ableton client not available"}
    try:
        result = live_client.get_clip_slot_state(track_index, clip_slot_index)
        topology = live_client.query_session_topology()
        tracks = [item for item in topology.get("tracks", []) if isinstance(item, dict)]
        track = next((item for item in tracks if int(item.get("index", -1)) == track_index), None)
        if track is not None:
            result["track_name"] = str(track.get("name", ""))
        return (200 if result.get("success") else 503), result
    except Exception as exc:
        return 503, {"ok": False, "error": str(exc)}


def handle_osc_device_parameters(
    live_client: Any | None, track_index_raw: str, device_index_raw: str,
) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/osc/device-parameters."""
    try:
        track_index = int(track_index_raw)
        device_index = int(device_index_raw)
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "track_index and device_index query parameters are required."}
    if min(track_index, device_index) < 0:
        return 400, {"ok": False, "error": "track_index and device_index must be non-negative."}
    if live_client is None:
        return 503, {"ok": False, "error": "Ableton client not available"}
    try:
        result = live_client.get_device_parameters(track_index, device_index)
        return (200 if result.get("success") else 503), result
    except Exception as exc:
        return 503, {"ok": False, "error": str(exc)}


def handle_osc_device_parameter_value_string(
    live_client: Any | None, track_index_raw: str, device_index_raw: str, parameter_index_raw: str,
) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/osc/device-parameter-value-string."""
    try:
        track_index = int(track_index_raw)
        device_index = int(device_index_raw)
        parameter_index = int(parameter_index_raw)
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "track_index, device_index, and parameter_index query parameters are required."}
    if min(track_index, device_index, parameter_index) < 0:
        return 400, {"ok": False, "error": "indices must be non-negative."}
    if live_client is None:
        return 503, {"ok": False, "error": "Ableton client not available"}
    try:
        result = live_client.get_device_parameter_value_string(track_index, device_index, parameter_index)
        return (200 if result.get("success") else 503), result
    except Exception as exc:
        return 503, {"ok": False, "error": str(exc)}


def handle_arrangement_analysis(live_client: Any | None, session_id: str) -> tuple[int, dict[str, Any]]:
    """Return status code and payload for /api/ableton/arrangement-analysis."""
    clean_id = session_id.strip()[:128]
    if not clean_id:
        return 400, {"ok": False, "error": "Missing session_id query param."}
    if live_client is None:
        return 503, {"ok": False, "error": "Ableton client not available", "advisory_only": True, "mutation_authorized": False}
    try:
        from kenn.core.arrangement_analysis import analyze_arrangement_context
        from kenn.core.session_context import build_session_context

        snapshot = live_client.query_session_understanding()
        context = build_session_context(snapshot=snapshot, session_id=clean_id)
        result = analyze_arrangement_context(context)
        return (200 if result.get("status") == "current" else 503), result
    except Exception as exc:
        return 503, {"ok": False, "error": str(exc), "advisory_only": True, "mutation_authorized": False}


