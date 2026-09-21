"""KENN Route Handlers: Neural MIDI Generation & AudioGen Groove Engine."""

from __future__ import annotations

from typing import Any


def handle_post_midi_detect_scale(handler: Any, payload: dict[str, Any]) -> None:
    """POST /api/midi/detect_scale - Detect scale from note pitches."""
    notes = payload.get("notes", [])
    if not isinstance(notes, list):
        handler.send_json(400, {"ok": False, "error": "'notes' array is required."})
        return
    from kenn.core.generative_midi import detect_scale_from_notes

    try:
        res = detect_scale_from_notes(notes)
    except (TypeError, ValueError) as exc:
        handler.send_json(400, {"ok": False, "error": str(exc)})
        return
    handler.send_json(200, res)


def handle_post_midi_groove(handler: Any, payload: dict[str, Any]) -> None:
    """POST /api/midi/groove - Apply AudioGen micro-timing groove."""
    notes = payload.get("notes", [])
    if not isinstance(notes, list):
        handler.send_json(400, {"ok": False, "error": "'notes' array is required."})
        return
    from kenn.core.generative_midi import apply_audiogen_groove

    template = str(payload.get("template", "lofi_swing"))
    try:
        res = apply_audiogen_groove(
            notes,
            groove_template=template,
            swing_pct=payload.get("swing_pct", 35.0),
            laidback_ms=payload.get("laidback_ms", 6.0),
            velocity_jitter_pct=payload.get("jitter_pct", 15.0),
        )
    except (TypeError, ValueError) as exc:
        handler.send_json(400, {"ok": False, "error": str(exc)})
        return
    handler.send_json(200, {
        "ok": True,
        "notes": res,
        "groove_applied": template,
        "note_count": len(res),
    })


def handle_post_midi_bassline(handler: Any, payload: dict[str, Any]) -> None:
    """POST /api/midi/bassline - Synthesize harmonic bassline."""
    from kenn.core.generative_midi import generate_audiogen_bassline

    scale = str(payload.get("scale", "F:minor"))
    style = str(payload.get("style", "rolling_16th"))
    root, separator, scale_name = scale.partition(":")
    if not separator:
        handler.send_json(400, {"ok": False, "error": "scale must use the '<root>:<mode>' format"})
        return
    try:
        res = generate_audiogen_bassline(
            root=root,
            scale_name=scale_name,
            style=style,
            bars=payload.get("bars", 2),
            octave=2,
            root_pitch=payload.get("root_pitch"),
        )
    except (TypeError, ValueError) as exc:
        handler.send_json(400, {"ok": False, "error": str(exc)})
        return
    handler.send_json(200, {
        "ok": True,
        "notes": res,
        "scale": scale,
        "style": style,
        "note_count": len(res),
    })
