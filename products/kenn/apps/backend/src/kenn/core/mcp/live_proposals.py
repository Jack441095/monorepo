"""Proposal-only calls. Nothing here may return an applied receipt.

Every handler here was lifted verbatim out of ``KennMCPFacade._dispatch``.
``facade`` is the facade that called it, so the injected client, coordinator,
and stores stay the single owner of Live and of the task ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking only
    from kenn.core.mcp_facade import KennMCPFacade


def duplicate_clip_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not session_id:
        raise ValueError("session_id is required")
    result = facade.client.post(
        "/api/ableton/clip-duplication/proposal",
        {
            "session_id": session_id,
            "source_track_index": args.get("source_track_index"),
            "source_track_name": str(args.get("source_track_name", ""))[:256],
            "source_clip_slot_index": args.get("source_clip_slot_index"),
            "target_track_index": args.get("target_track_index"),
            "target_track_name": str(args.get("target_track_name", ""))[:256],
            "target_clip_slot_index": args.get("target_clip_slot_index"),
        },
    )
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from a clip duplication proposal-only MCP call")
    return result


def rename_clip_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not session_id:
        raise ValueError("session_id is required")
    result = facade.client.post(
        "/api/ableton/clip-rename/proposal",
        {
            "session_id": session_id,
            "track_index": args.get("track_index"),
            "track_name": str(args.get("track_name", ""))[:256],
            "clip_slot_index": args.get("clip_slot_index"),
            "new_name": str(args.get("new_name", ""))[:128],
        },
    )
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from a clip rename proposal-only MCP call")
    return result


def create_live_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    command = str(args.get("command", "")).strip()
    if not command:
        raise ValueError("command is required")
    session_id = str(args.get("session_id", "mcp-proposal")).strip() or "mcp-proposal"
    facade._assistant_binding_ids(args)
    result = facade.client.post("/api/ableton/command", {"session_id": session_id, "command": command})
    # A proposal call must never be allowed to return an applied receipt.
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from a proposal-only MCP call")
    binding = facade._bind_assistant_proposal(args=args, result=result, session_id=session_id)
    if binding is not None:
        result = {**result, "assistant_task": binding}
    return result


def create_live_recipe_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    steps = args.get("steps")
    facade._assistant_binding_ids(args)
    if not session_id:
        raise ValueError("session_id is required")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
        raise ValueError("steps must contain between 1 and 3 typed actions")
    if any(not isinstance(step, dict) for step in steps):
        raise ValueError("every recipe step must be an object")
    payload = {
        "session_id": session_id,
        "command": str(args.get("reason", "MCP supervised Live recipe"))[:512],
        "recipe_steps": steps,
    }
    result = facade.client.post("/api/ableton/command", payload)
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from a recipe proposal-only MCP call")
    binding = facade._bind_assistant_proposal(args=args, result=result, session_id=session_id)
    if binding is not None:
        result = {**result, "assistant_task": binding}
    return result


def create_mix_review_recipe_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    review_id = str(args.get("review_id", "")).strip()[:128]
    session_id = str(args.get("session_id", "")).strip()[:128]
    steps = args.get("steps")
    if not review_id or not session_id:
        raise ValueError("review_id and session_id are required")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
        raise ValueError("steps must contain between 1 and 3 typed actions")
    if any(not isinstance(step, dict) for step in steps):
        raise ValueError("every recipe step must be an object")
    result = facade.client.post(
        "/api/ableton/command",
        {
            "session_id": session_id,
            "command": str(args.get("reason", "Mix Review evidence-bound Live recipe"))[:512],
            "mix_review_id": review_id,
            "recipe_steps": steps,
        },
    )
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from a Mix Review recipe proposal-only MCP call")
    return result


def launch_clip_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not session_id:
        raise ValueError("session_id is required")
    payload = {
        "session_id": session_id,
        "track_index": args.get("track_index"),
        "clip_slot_index": args.get("clip_slot_index"),
        "stop": bool(args.get("stop", False)),
    }
    return facade.client.post("/api/ableton/command", {
        "session_id": session_id,
        "command": f"propose clip launch track {payload['track_index']} slot {payload['clip_slot_index']}",
        "proposal_action": "launch_clip",
        "payload": payload,
    })


def launch_scene_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not session_id:
        raise ValueError("session_id is required")
    payload = {
        "session_id": session_id,
        "scene_name": str(args.get("scene_name", "")),
    }
    return facade.client.post("/api/ableton/command", {
        "session_id": session_id,
        "command": f"propose create scene {payload['scene_name']}",
        "proposal_action": "create_scene",
        "payload": payload,
    })


def clip_warp_pitch_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not session_id:
        raise ValueError("session_id is required")
    payload = {
        "session_id": session_id,
        "track_index": args.get("track_index"),
        "clip_slot_index": args.get("clip_slot_index"),
        "warp_mode": args.get("warp_mode"),
        "pitch_coarse": args.get("pitch_coarse"),
    }
    return facade.client.post("/api/ableton/command", {
        "session_id": session_id,
        "command": f"propose clip warp pitch track {payload['track_index']} slot {payload['clip_slot_index']}",
        "proposal_action": "set_clip_warp_pitch",
        "payload": payload,
    })


def duplicate_loop_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not session_id:
        raise ValueError("session_id is required")
    payload = {
        "session_id": session_id,
        "track_index": args.get("track_index"),
        "clip_slot_index": args.get("clip_slot_index"),
    }
    return facade.client.post("/api/ableton/command", {
        "session_id": session_id,
        "command": f"propose duplicate loop track {payload['track_index']} slot {payload['clip_slot_index']}",
        "proposal_action": "duplicate_loop",
        "payload": payload,
    })


def create_midi_clip_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not session_id:
        raise ValueError("session_id is required")
    payload = {
        "session_id": session_id,
        "track_index": args.get("track_index"),
        "track_name": str(args.get("track_name", ""))[:256],
        "clip_slot_index": args.get("clip_slot_index"),
        "length": args.get("length"),
        "notes": args.get("notes"),
        "source_artifact_sha256": str(args.get("source_artifact_sha256", ""))[:128],
        "source_artifact_id": str(args.get("source_artifact_id", ""))[:256],
    }
    result = facade.client.post("/api/ableton/midi-clip/proposal", payload)
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from a MIDI proposal-only MCP call")
    return result


def update_midi_clip_proposal(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    if not session_id:
        raise ValueError("session_id is required")
    result = facade.client.post("/api/ableton/midi-clip/update-proposal", {
        "session_id": session_id,
        "track_index": args.get("track_index"),
        "track_name": str(args.get("track_name", ""))[:256],
        "clip_slot_index": args.get("clip_slot_index"),
        "notes": args.get("notes"),
    })
    if result.get("receipt") or result.get("changed") is True:
        raise RuntimeError("KENN returned a mutation from a MIDI clip update proposal-only MCP call")
    return result
