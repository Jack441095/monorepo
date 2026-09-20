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

    res = detect_scale_from_notes(notes)
    handler.send_json(200, res)


def handle_post_midi_groove(handler: Any, payload: dict[str, Any]) -> None:
    """POST /api/midi/groove - Apply AudioGen micro-timing groove."""
    notes = payload.get("notes", [])
    if not isinstance(notes, list):
        handler.send_json(400, {"ok": False, "error": "'notes' array is required."})
        return
    template = str(payload.get("template", "lofi_swing"))
    swing_pct = float(payload.get("swing_pct", 35.0))
    laidback_ms = float(payload.get("laidback_ms", 6.0))
    jitter_pct = float(payload.get("jitter_pct", 15.0))
    from kenn.core.generative_midi import apply_audiogen_groove

    res = apply_audiogen_groove(
        notes,
        groove_template=template,
        swing_pct=swing_pct,
        laidback_ms=laidback_ms,
        velocity_jitter_pct=jitter_pct,
    )
    handler.send_json(200, {
        "ok": True,
        "notes": res,
        "groove_applied": template,
        "note_count": len(res),
    })


def handle_post_midi_bassline(handler: Any, payload: dict[str, Any]) -> None:
    """POST /api/midi/bassline - Synthesize harmonic bassline."""
    scale = str(payload.get("scale", "F:minor"))
    style = str(payload.get("style", "rolling_16th"))
    bars = int(payload.get("bars", 2))
    root_pitch = int(payload.get("root_pitch", 41))
    from kenn.core.generative_midi import generate_audiogen_bassline

    res = generate_audiogen_bassline(
        root_pitch=root_pitch,
        scale=scale,
        style=style,
        bars=bars,
    )
    handler.send_json(200, {
        "ok": True,
        "notes": res,
        "scale": scale,
        "style": style,
        "note_count": len(res),
    })

