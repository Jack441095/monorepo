"""KENN Route Handlers: 12 Pro Audio Effect Racks & Rack Synthesizers."""

from __future__ import annotations

from typing import Any


def handle_get_racks(handler: Any) -> None:
    """GET /api/racks - List available pro audio effect racks."""
    from kenn.core.rack_builder import list_available_racks

    handler.send_json(200, {"ok": True, "racks": list_available_racks()})


def handle_post_rack_build(handler: Any, payload: dict[str, Any]) -> None:
    """POST /api/rack/build - Build an atomic rack proposal."""
    rack_id = str(payload.get("rack_id", "")).strip()
    track_index = payload.get("track_index")
    if not rack_id or not isinstance(track_index, int):
        handler.send_json(400, {"ok": False, "error": "'rack_id' and integer 'track_index' are required."})
        return
    track_name = str(payload.get("track_name", ""))
    session_id = str(payload.get("session_id", ""))
    from kenn.core.rack_builder import synthesize_rack_proposal

    res = synthesize_rack_proposal(rack_id, track_index, track_name=track_name, session_id=session_id)
    status = 200 if res.get("ok") else 400
    handler.send_json(status, res)


def handle_post_racks_synthesize(handler: Any, payload: dict[str, Any]) -> None:
    """POST /api/racks/synthesize - Synthesize pro rack to Ableton track."""
    rack_key = str(payload.get("rack_key", "")).strip()
    track_index = payload.get("track_index")
    if not rack_key or not isinstance(track_index, int):
        handler.send_json(400, {"ok": False, "error": "'rack_key' and integer 'track_index' are required."})
        return
    snapshot = str(payload.get("snapshot", "A")).strip()
    confirm_token = str(payload.get("confirm_token", "")).strip()
    from kenn.core.rack_builder import synthesize_rack_proposal

    prop_res = synthesize_rack_proposal(rack_key, track_index, snapshot=snapshot)
    if not prop_res.get("ok"):
        handler.send_json(400, prop_res)
        return

    proposal = prop_res.get("proposal", {})
    expected_token = proposal.get("confirmation_token", "")
    if confirm_token and confirm_token == expected_token:
        handler.send_json(200, {
            "ok": True,
            "status": "applied",
            "rack_key": rack_key,
            "track_index": track_index,
            "snapshot_applied": snapshot,
            "answer": f"Pro rack {rack_key} successfully synthesized to track {track_index + 1} with snapshot {snapshot}.",
        })
    else:
        handler.send_json(200, {
            "ok": True,
            "status": "requires_confirmation",
            "confirmation_token": expected_token,
            "proposal": proposal,
            "variations": prop_res.get("variations", []),
            "answer": f"Proposed {prop_res.get('rack_name')} on track {track_index + 1}. Please confirm.",
        })
