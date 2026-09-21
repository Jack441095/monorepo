"""KENN Route Handlers: Session World Model, Acoustic Target Curves & Intelligence."""

from __future__ import annotations

from typing import Any


def handle_get_world_model(handler: Any) -> None:
    """GET /api/session/world_model - Extract live session intelligence graph."""
    try:
        from kenn.mixing_doctor import get_latest_session_state
        from kenn.core.session_world_model import SessionWorldModel

        cached_snapshot = get_latest_session_state() or {"status": "offline", "tracks": []}
        model = SessionWorldModel.build_world_model(cached_snapshot)
        handler.send_json(200, {"ok": True, "world_model": model})
    except Exception as e:
        handler.send_json(500, {"ok": False, "error": str(e)})


def handle_get_genre_curves(handler: Any) -> None:
    """GET /api/genre_curves - Available genre target curves."""
    from kenn.core.target_curves import list_available_genres

    handler.send_json(200, {"ok": True, "genres": list_available_genres()})


def handle_get_guardian_status(handler: Any) -> None:
    """GET /api/guardian/status - Ambient session guardian status."""
    from kenn.core.ambient_guardian import get_ambient_guardian

    guardian = get_ambient_guardian()
    try:
        from kenn.mixing_doctor import get_latest_session_state

        state = get_latest_session_state()
        if isinstance(state, dict) and state.get("tracks"):
            guardian.evaluate_session(state)
    except Exception:
        pass
    handler.send_json(200, {"ok": True, "guardian": guardian.get_status()})


def handle_post_audition_delta(handler: Any, payload: dict[str, Any]) -> None:
    """POST /api/ableton/audition_delta - Loudness matched gain calculation."""
    dry_lufs = payload.get("dry_lufs")
    wet_lufs = payload.get("wet_lufs")
    if not isinstance(dry_lufs, (int, float)) or not isinstance(wet_lufs, (int, float)):
        handler.send_json(400, {"ok": False, "error": "Both 'dry_lufs' and 'wet_lufs' numeric values are required."})
        return
    from kenn.core.target_curves import calculate_loudness_matched_gain_delta

    res = calculate_loudness_matched_gain_delta(float(dry_lufs), float(wet_lufs))
    handler.send_json(200, {"ok": True, **res})
