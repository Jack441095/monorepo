# composition/song_postprocess/form_polish/chorus_guards.py
# Chorus register/harmony guardrails: caps excessive register jumps between
# choruses and reinforces harmonic motion under the chorus lead.

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from .._common import Event, _lead_pitch, _section_starts


def guard_excessive_chorus_register_jumps(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    beats_per_bar: float = 4.0,
    max_register_delta: int = 12,
    floor_pitch: int = 57,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Prevent a chorus from jumping more than an octave above the verse median."""

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "notes_shifted": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    n = min(len(starts), len(section_bars), len(section_roles or []))
    roles = [str(r or "").strip().lower() for r in list(section_roles or [])]
    replacements: Dict[int, Tuple] = {}
    verse_history: List[int] = []
    sections_shifted = 0

    def _section_indices(sec: int) -> List[int]:
        start = float(starts[sec])
        end = start + float(int(section_bars[sec])) * float(bpb)
        indices: List[int] = []
        for idx, ev in enumerate(out):
            if _lead_pitch(ev) is None:
                continue
            try:
                st = float(ev[3])
            except Exception:
                continue
            if start - 1e-6 <= st < end - 1e-6:
                indices.append(int(idx))
        return indices

    for sec in range(n):
        role = roles[sec]
        indices = _section_indices(sec)
        pitches = sorted(int(p) for idx in indices if (p := _lead_pitch(out[idx])) is not None)
        if not pitches:
            continue
        if role in {"a", "verse"}:
            verse_history.extend(pitches)
            continue
        if role not in {"b", "chorus", "hook"} or not verse_history:
            continue
        verse_sorted = sorted(verse_history)
        verse_med = int(verse_sorted[len(verse_sorted) // 2])
        chorus_med = int(pitches[len(pitches) // 2])
        ceiling = int(verse_med) + int(max_register_delta)
        if int(chorus_med) <= ceiling:
            continue
        local = 0
        for idx in indices:
            ev = out[idx]
            pitch = _lead_pitch(ev)
            if pitch is None or int(pitch) <= ceiling:
                continue
            new_pitch = int(pitch) - 12
            if new_pitch < int(floor_pitch):
                continue
            replacements[int(idx)] = (2, int(new_pitch), int(ev[2]), float(ev[3]), float(ev[4]), [int(new_pitch)])
            local += 1
        if local:
            sections_shifted += 1

    if replacements:
        out = [replacements.get(i, ev) for i, ev in enumerate(out)]
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "sections_shifted": int(sections_shifted),
        "notes_shifted": int(len(replacements)),
    }


def reinforce_chorus_harmonic_motion(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_roots: Sequence[int],
    section_emotions: Sequence[str],
    beats_per_bar: float = 4.0,
    min_changes_per_bar: float = 1.0,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Add quiet in-scale passing chords when a chorus harmonic bed is too static."""

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "added_chords": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    n = min(len(starts), len(section_bars), len(section_roles or []), len(section_roots or []), len(section_emotions or []))
    added: List[Tuple] = []
    sections_repaired = 0

    def _is_chorus(role: str) -> bool:
        return str(role or "").strip().lower() in {"b", "chorus", "hook"}

    for sec in range(n):
        if not _is_chorus(str(section_roles[sec] or "")):
            continue
        bars = max(1, int(section_bars[sec]))
        sec_start = float(starts[sec])
        sec_end = sec_start + float(bars) * float(bpb)
        chord_shapes: List[Tuple[int, ...]] = []
        for ev in sorted(out, key=lambda item: float(item[3])):
            try:
                if int(ev[0]) != 1:
                    continue
                st = float(ev[3])
            except Exception:
                continue
            if not (sec_start - 1e-6 <= st < sec_end - 1e-6):
                continue
            notes = [int(n) for n in list(ev[5] or []) if isinstance(n, int)]
            shape = tuple(sorted({int(p) % 12 for p in notes}))
            if shape and (not chord_shapes or shape != chord_shapes[-1]):
                chord_shapes.append(shape)
        target_changes = max(1, int(round(float(bars) * float(min_changes_per_bar))))
        missing = max(0, int(target_changes) - max(0, len(chord_shapes) - 1))
        if missing <= 0:
            continue
        try:
            from data.emotion_scales import melody_scale_intervals_for_emotion
            from data.music_data import EMOTION_BY_NAME

            emo_name = str(section_emotions[sec] or "").strip().lower()
            scale = list(melody_scale_intervals_for_emotion(EMOTION_BY_NAME.get(emo_name, emo_name)) or [0, 2, 4, 5, 7, 9, 11])
        except Exception:
            scale = [0, 2, 4, 5, 7, 9, 11]
        if len(scale) < 5:
            scale = [0, 2, 4, 5, 7, 9, 11]
        root = int(section_roots[sec])
        candidate_bars = [b for b in range(2, bars - 1)]
        if not candidate_bars:
            candidate_bars = [max(1, bars // 2)]
        local = 0
        for j, bar in enumerate(candidate_bars):
            if local >= missing:
                break
            degrees = [(j + 1) % len(scale), (j + 3) % len(scale), (j + 5) % len(scale)]
            notes = sorted({int(root) + int(scale[d]) + 12 for d in degrees})
            if len(notes) < 3:
                continue
            st = sec_start + float(bar) * float(bpb)
            added.append((1, int(notes[0]), 48, float(st), min(1.5, float(bpb) * 0.5), list(notes[:3])))
            local += 1
        if local:
            sections_repaired += 1

    if added:
        out = sorted(list(out) + list(added), key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))
    return out, {
        "enabled": True,
        "sections_repaired": int(sections_repaired),
        "added_chords": int(len(added)),
    }

