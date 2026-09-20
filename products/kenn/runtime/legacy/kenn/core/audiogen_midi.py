"""Convert AudioGen's symbolic event payload into a typed KENN MIDI artifact.

The adjacent AudioGen producer emits JSON events such as ``midi``,
``start_beats``, ``duration_beats``, and ``velocity``.  This module is the
small, dependency-free boundary between that producer shape and KENN's
digest-bound MIDI artifact contract.  It never opens a file and never talks to
Ableton.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any
from uuid import uuid4

from kenn.core.audiogen_artifacts import MAX_MIDI_LENGTH, MAX_MIDI_NOTES, midi_import_payload


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _event_notes(events: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(events, list) or not events:
        return [], ["AudioGen returned no symbolic MIDI events."]
    if len(events) > MAX_MIDI_NOTES:
        return [], [f"AudioGen returned more than {MAX_MIDI_NOTES} events."]
    notes: list[dict[str, Any]] = []
    errors: list[str] = []
    for event_index, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append(f"AudioGen event {event_index} is not an object.")
            continue
        pitches = event.get("notes")
        if not isinstance(pitches, list) or not pitches:
            pitches = [event.get("midi", event.get("pitch"))]
        start = _number(event.get("start_beats", event.get("start_time")))
        duration = _number(event.get("duration_beats", event.get("duration")))
        velocity = event.get("velocity", 100)
        try:
            velocity = int(velocity)
        except (TypeError, ValueError):
            velocity = -1
        if start is None or start < 0:
            errors.append(f"AudioGen event {event_index} has an invalid start time.")
            continue
        if duration is None or duration <= 0:
            errors.append(f"AudioGen event {event_index} has an invalid duration.")
            continue
        if not 1 <= velocity <= 127:
            errors.append(f"AudioGen event {event_index} has an invalid velocity.")
            continue
        for pitch_value in pitches:
            try:
                pitch = int(pitch_value)
            except (TypeError, ValueError):
                errors.append(f"AudioGen event {event_index} has an invalid MIDI pitch.")
                continue
            if not 0 <= pitch <= 127:
                errors.append(f"AudioGen event {event_index} pitch must be between 0 and 127.")
                continue
            notes.append({
                "pitch": pitch,
                "start_time": float(start),
                "duration": float(duration),
                "velocity": velocity,
                "mute": False,
            })
            if len(notes) > MAX_MIDI_NOTES:
                return [], [f"AudioGen expanded more than {MAX_MIDI_NOTES} MIDI notes."]
    # Ableton's clip API represents one note per pitch/start position.  The
    # producer can emit layered duplicates at the same position; coalesce
    # those deterministically so the proposal describes what Live can verify.
    coalesced: dict[tuple[int, float, bool], dict[str, Any]] = {}
    duplicate_count = 0
    for note in notes:
        key = (note["pitch"], note["start_time"], note["mute"])
        previous = coalesced.get(key)
        if previous is None:
            coalesced[key] = note
            continue
        duplicate_count += 1
        if (note["duration"], note["velocity"]) > (previous["duration"], previous["velocity"]):
            coalesced[key] = note
    notes = list(coalesced.values())
    if duplicate_count:
        errors.append(
            f"AudioGen emitted {duplicate_count} overlapping duplicate note(s); "
            "KENN kept the longest, strongest note at each pitch/start position."
        )
    notes.sort(key=lambda item: (
        item["pitch"], item["start_time"], item["duration"], item["velocity"], item["mute"]
    ))
    return notes, errors


def artifact_from_event_payload(
    payload: Any,
    *,
    artifact_id: str = "",
    generation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and validate a digest-bound MIDI artifact from AudioGen JSON."""
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return {"ok": False, "errors": ["AudioGen did not return a successful event payload."], "artifact": None}
    notes, errors = _event_notes(payload.get("events"))
    length = _number(payload.get("section_duration_beats"))
    if length is None:
        bars = _number(payload.get("bars"), 0.0) or 0.0
        beats_per_bar = _number(payload.get("beats_per_bar"), 4.0) or 4.0
        length = bars * beats_per_bar
    if length is None or not 0.0 < length <= MAX_MIDI_LENGTH:
        errors.append(f"AudioGen clip length must be between 0 and {MAX_MIDI_LENGTH} beats.")
        length = 0.0
    for offset, note in enumerate(notes):
        if note["start_time"] + note["duration"] > length + 1e-9:
            errors.append(f"AudioGen note {offset} extends beyond the generated clip length.")
    identifier = str(artifact_id or "").strip() or f"audiogen-midi-{uuid4().hex}"
    material = {
        "kind": "midi",
        "artifact_id": identifier,
        "length_beats": length,
        "notes": notes,
        "producer": "audiogen",
    }
    digest = "sha256:" + hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    artifact = {
        **material,
        "sha256": digest,
        "note_count": len(notes),
        "lowest_note": min((note["pitch"] for note in notes), default=0),
        "highest_note": max((note["pitch"] for note in notes), default=0),
        "bars": payload.get("bars"),
        "bpm": payload.get("bpm"),
        "key": payload.get("key", ""),
    }
    if isinstance(generation_context, dict):
        artifact["generation_context"] = generation_context
    imported = midi_import_payload(artifact)
    # Duplicate producer events are a representational warning, not a failed
    # artifact: the normalized note list is exactly what Live will receive.
    duplicate_warnings = [item for item in errors if "overlapping duplicate" in item]
    validation_errors = [item for item in errors if item not in duplicate_warnings]
    if validation_errors or not imported.get("ok"):
        return {
            "ok": False,
            "artifact": artifact,
            "errors": validation_errors + list(imported.get("errors", [])),
            "validation": imported.get("validation"),
        }
    return {"ok": True, "artifact": artifact, "import": imported, "warnings": duplicate_warnings}


__all__ = ["artifact_from_event_payload"]
