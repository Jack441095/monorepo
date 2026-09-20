"""Bounded Live context for AudioGen-generated symbolic MIDI.

AudioGen note positions are expressed in beats.  This module records the
relationship between that symbolic timing and the current Live session without
retiming notes or trusting arbitrary producer metadata.
"""

from __future__ import annotations

import math
from typing import Any


SCHEMA = "kenn.audiogen_live_context.v1"
TIMING_BASIS = "symbolic MIDI positions are expressed in beats; Live project tempo governs playback"


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def build_live_generation_context(
    snapshot: Any,
    *,
    track_index: int,
    track_name: str,
    source_bpm: Any = None,
    source_key: Any = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Build a safe, exact-target context record from a fresh Live snapshot."""
    if not isinstance(snapshot, dict) or snapshot.get("status") != "connected":
        return None, "Ableton Live is offline or returned no usable context snapshot."
    try:
        clean_index = int(track_index)
    except (TypeError, ValueError):
        return None, "AudioGen MIDI target track index is invalid."
    clean_name = str(track_name or "").strip()[:256]
    tracks = [item for item in snapshot.get("tracks", []) if isinstance(item, dict)]
    matches = [item for item in tracks if int(item.get("index", -1)) == clean_index]
    if len(matches) != 1:
        return None, "AudioGen MIDI target track is not present exactly once in Live."
    if clean_name and str(matches[0].get("name", "")) != clean_name:
        return None, "AudioGen MIDI target track name changed before generation."

    live_bpm = _number(snapshot.get("tempo"))
    if live_bpm is None or not 20.0 <= live_bpm <= 999.0:
        return None, "Ableton Live tempo was not readable from the context snapshot."
    producer_bpm = _number(source_bpm)
    limitations: list[str] = []
    if producer_bpm is None:
        limitations.append("AudioGen did not provide a source BPM; tempo relationship is unknown.")
        relationship = "unknown"
    else:
        relationship = "match" if math.isclose(live_bpm, producer_bpm, rel_tol=0.0, abs_tol=0.01) else "different"
        if relationship == "different":
            limitations.append("Source and Live BPM differ; KENN preserved beat positions and did not retime notes.")

    selected = snapshot.get("selected_track_index")
    try:
        selected = int(selected) if selected is not None else None
    except (TypeError, ValueError):
        selected = None
    numerator = snapshot.get("signature_numerator")
    denominator = snapshot.get("signature_denominator")
    try:
        numerator = int(numerator)
        denominator = int(denominator)
    except (TypeError, ValueError):
        numerator = denominator = None
    if numerator is None or denominator is None or not 1 <= numerator <= 32 or not 1 <= denominator <= 64:
        time_signature = None
        limitations.append("Live time signature was not readable; KENN did not infer a meter.")
    else:
        time_signature = {"numerator": numerator, "denominator": denominator}
    root_note = snapshot.get("root_note")
    try:
        root_note = int(root_note)
    except (TypeError, ValueError):
        root_note = None
    if root_note is not None and not 0 <= root_note <= 11:
        root_note = None
    scale_name = str(snapshot.get("scale_name") or "").strip()[:64] or None
    live_key = {"root_note": root_note, "scale_name": scale_name} if root_note is not None or scale_name else None
    clean_source_key = str(source_key or "").strip()[:64] or None
    if live_key is None:
        limitations.append("Live key/scale was not readable; KENN did not infer a key.")
    if not clean_source_key:
        limitations.append("AudioGen did not provide a source key; key relationship is unknown.")
    context = {
        "schema": SCHEMA,
        "target": {"track_index": clean_index, "track_name": str(matches[0].get("name", clean_name))[:256]},
        "live_tempo_bpm": live_bpm,
        "source_tempo_bpm": producer_bpm,
        "tempo_relationship": relationship,
        "timing_basis": TIMING_BASIS,
        "timing_action": "preserve_symbolic_beats",
        "adaptation": "none_required",
        "selected_track_index": selected,
        "time_signature": time_signature,
        "live_key": live_key,
        "source_key": clean_source_key,
        "key_relationship": "unknown" if not clean_source_key else "not_compared",
        "limitations": limitations,
    }
    return context, None


__all__ = ["SCHEMA", "TIMING_BASIS", "build_live_generation_context"]
