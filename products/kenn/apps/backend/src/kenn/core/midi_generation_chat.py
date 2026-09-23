"""Chat requests to generate MIDI ideas as confirmable Session clips.

"Write a 4-bar D minor chord progression on the Pads track" becomes generated
notes plus a MidiClipActionService create proposal: nothing is written until
the user applies it, the clip is read back, and its receipt can be undone. The
seed is derived from the request so the preview is exactly what is inserted.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from kenn.core.generative_midi import (
    generate_audiogen_bassline,
    generate_chord_progression,
    generate_drum_pattern,
)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_GENERATE = re.compile(r"^\s*(?:please\s+)?(?:write|generate|make|create|compose|give\s+me|sketch)\b", re.I)
_KINDS = (
    ("drums", re.compile(r"\b(?:drum\s*(?:pattern|loop|groove|beat)?|beat|drums)\b", re.I)),
    ("bassline", re.compile(r"\bbass\s*line\b|\bbassline\b", re.I)),
    ("chords", re.compile(r"\bchords?\b|\bchord\s+progression\b|\bprogression\b", re.I)),
)
_KEY = re.compile(r"\bin\s+([a-g])\s*(#|b|sharp|flat)?\s*(major|minor|maj|min)\b", re.I)
_BARS = re.compile(r"\b(\d{1,2})[\s-]*bars?\b", re.I)
MAX_BARS = 16


def generation_kind(text: str) -> str | None:
    if not _GENERATE.match(str(text or "")):
        return None
    for kind, pattern in _KINDS:
        if pattern.search(text):
            return kind
    return None


def _key(text: str, snapshot: dict[str, Any]) -> tuple[str, str] | None:
    match = _KEY.search(text)
    if match:
        root = match.group(1).upper()
        accidental = (match.group(2) or "").lower()
        if accidental in {"#", "sharp"}:
            root += "#"
        elif accidental in {"b", "flat"}:
            root = NOTE_NAMES[(NOTE_NAMES.index(root) - 1) % 12]
        return root, "major" if match.group(3).lower().startswith("maj") else "minor"
    root_note, scale = snapshot.get("root_note"), str(snapshot.get("scale_name") or "").lower()
    if isinstance(root_note, int) and scale in {"major", "minor"}:
        return NOTE_NAMES[root_note % 12], scale
    return None


def _target_track(text: str, tracks: list[dict[str, Any]], client: Any) -> dict[str, Any] | None:
    midi = [t for t in tracks if client.get_track_has_midi_input(int(t["index"]))]
    lowered = text.casefold()
    named = [t for t in midi if str(t.get("name", "")).casefold() in lowered]
    return (named or midi or [None])[0]


def _first_empty_slot(client: Any, track_index: int, slot_count: int) -> int | None:
    for slot in range(slot_count):
        state = client.get_midi_clip_state(track_index, slot)
        if state.get("success") and not state.get("has_clip"):
            return slot
    return None


def _notes(kind: str, root: str, scale: str, bars: int, tempo: float, seed: int) -> list[dict[str, Any]]:
    if kind == "drums":
        notes = generate_drum_pattern(genre="house", bars=bars, bpm=tempo)
    elif kind == "bassline":
        notes = generate_audiogen_bassline(root=root, scale_name=scale, bars=bars)
    else:
        chords = generate_chord_progression(root=root, scale_name=scale, seed=seed)
        cycle = max(1e-9, max(n["start_time"] + n["duration"] for n in chords))
        notes = []
        repeats = max(1, int(round(bars * 4.0 / cycle)))
        for repeat in range(repeats):
            notes.extend(dict(n, start_time=n["start_time"] + repeat * cycle) for n in chords)
    return [{k: n[k] for k in ("pitch", "start_time", "duration", "velocity", "mute") if k in n}
            for n in notes if n["start_time"] < bars * 4.0]


def propose_generated_clip(question: str, *, session_id: str, service: Any) -> dict[str, Any] | None:
    kind = generation_kind(question)
    if kind is None:
        return None
    client = service.client
    snapshot = client.query_session_state()
    tracks = [t for t in snapshot.get("tracks", []) if isinstance(t, dict)]
    # The response envelope requires a plain-string intent; keep the structured form beside it.
    base = {"schema": "kenn.midi_generation_answer.v1", "changed": False, "intent": f"generate_{kind}",
            "live_intent": {"action": f"generate_{kind}"}}
    track = _target_track(question, tracks, client)
    if track is None:
        return {**base, "status": "clarification_required",
                "answer": "There's no MIDI track in this set to put the idea on. Say \"Create a MIDI track\" first, then ask again."}
    key = (None, None) if kind == "drums" else _key(question, snapshot)
    if key is None:
        return {**base, "status": "clarification_required",
                "answer": "Which key should it be in? For example: \"in D minor\"."}
    bars_match = _BARS.search(question)
    bars = max(1, min(MAX_BARS, int(bars_match.group(1)))) if bars_match else 4
    slot = _first_empty_slot(client, int(track["index"]), len(snapshot.get("scenes") or []))
    if slot is None:
        return {**base, "status": "clarification_required",
                "answer": f"'{track['name']}' has no empty clip slot. Free a slot or add a scene, then ask again."}
    seed = int(hashlib.sha256(f"{kind}|{key}|{bars}|{question}".encode()).hexdigest()[:8], 16)
    tempo = float(snapshot.get("tempo") or 120.0)
    notes = _notes(kind, key[0] or "C", key[1] or "minor", bars, tempo, seed)
    from kenn.core.midi_clip_service import MidiClipActionService

    proposal_result = MidiClipActionService(client).propose_create(
        track_index=int(track["index"]), track_name=str(track["name"]), clip_slot_index=slot,
        length=bars * 4.0, notes=notes, session_id=session_id,
    )
    if not proposal_result.get("ok"):
        return {**base, "status": "clarification_required",
                "answer": f"I couldn't prepare that clip: {proposal_result.get('error', 'unknown reason')}"}
    pitches = [n["pitch"] for n in notes]
    label = {"drums": "drum pattern", "bassline": "bassline", "chords": "chord progression"}[kind]
    key_text = "" if kind == "drums" else f" in {key[0]} {key[1]}"
    answer = (f"I can add a {bars}-bar {label}{key_text} to '{track['name']}', slot {slot + 1}: "
              f"{len(notes)} notes, pitches {NOTE_NAMES[min(pitches) % 12]}{min(pitches) // 12 - 1}–"
              f"{NOTE_NAMES[max(pitches) % 12]}{max(pitches) // 12 - 1}. Nothing has changed. Apply to insert it; Undo removes it.")
    return {**base, "status": "confirmation_required", "answer": answer,
            "proposal": proposal_result["proposal"], "generation": {"kind": kind, "bars": bars, "seed": seed,
                                                                    "key": None if kind == "drums" else " ".join(key)}}


__all__ = ["generation_kind", "propose_generated_clip"]
