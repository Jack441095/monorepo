# composition/song_postprocess/form_polish/lead_cleanup.py
# Lead-line cleanup passes: thins repeated pitches and caps overly large leaps.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .._common import (
    Event,
    _active_chord_pcs_at,
    _build_chord_windows,
    _clamp_lead_pitch,
    _emotion_scale_pcs_for_section,
    _lead_pitch,
    _section_starts,
)


def reduce_repeated_song_lead_pitches(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roots: Sequence[int],
    section_emotions: Sequence[str],
    section_phrase_spans: Optional[Sequence[Dict[str, Any]]] = None,
    beats_per_bar: float = 4.0,
    max_same_run: int = 1,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Break excessive whole-song exact lead repeats without rewriting motifs."""

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "notes_changed": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=bpb)
    n = min(len(starts), len(section_bars), len(section_roots or []), len(section_emotions or []))
    if n <= 0:
        return out, {"enabled": False, "notes_changed": 0}

    ends = [float(starts[i]) + float(int(section_bars[i])) * bpb for i in range(n)]
    chord_windows = _build_chord_windows(out)
    scale_by_section = [
        _emotion_scale_pcs_for_section(
            emotion_name=str(list(section_emotions)[i]),
            root_note=int(list(section_roots)[i]),
        )
        for i in range(n)
    ]
    phrase_ends_by_section: Dict[int, List[float]] = {}
    for span in list(section_phrase_spans or []):
        if not isinstance(span, dict):
            continue
        try:
            sec_idx = int(span.get("section_index", -1))
            end_abs = float(span.get("absolute_end_beats", span.get("end_beats")))
        except Exception:
            continue
        if 0 <= int(sec_idx) < int(n):
            phrase_ends_by_section.setdefault(int(sec_idx), []).append(float(end_abs))

    def _section_for_start(st: float) -> Optional[int]:
        for sec_i in range(n):
            if float(starts[sec_i]) - 1e-6 <= float(st) < float(ends[sec_i]) - 1e-6:
                return int(sec_i)
        return None

    def _near_phrase_end(sec_i: int, st: float, dur: float) -> bool:
        sec_start = float(starts[sec_i])
        bars = max(1, int(section_bars[sec_i]))
        ends0: List[float] = []
        for bar in range(bars):
            if ((int(bar) + 1) % 4) == 0 or int(bar) == int(bars) - 1:
                ends0.append(float(sec_start) + float(bar + 1) * bpb)
        ends0.extend(float(x) for x in phrase_ends_by_section.get(int(sec_i), []))
        note_end = float(st) + float(dur)
        for end0 in ends0:
            if float(st) <= float(end0) + 1e-6 and float(note_end) >= float(end0) - 0.90:
                return True
        return False

    def _pick_replacement(
        cur: int,
        *,
        sec_i: int,
        st: float,
        prev_pitch: Optional[int],
        next_pitch: Optional[int],
    ) -> int:
        chord_pcs = _active_chord_pcs_at(chord_windows, float(st), beats_per_bar=float(bpb))
        scale_pcs = set(scale_by_section[sec_i] or set())
        target_pcs = set(chord_pcs or set())
        if target_pcs and scale_pcs:
            in_scale = {int(pc) for pc in target_pcs if int(pc) in scale_pcs}
            target_pcs = set(in_scale or target_pcs)
        if not target_pcs:
            target_pcs = set(scale_pcs)
        if not target_pcs:
            return int(cur)
        if len(target_pcs) > 1 and int(cur) % 12 in target_pcs:
            target_pcs.discard(int(cur) % 12)

        cands: List[Tuple[float, int]] = []
        for cand in range(int(cur) - 9, int(cur) + 10):
            c2 = _clamp_lead_pitch(int(cand))
            if int(c2) != int(cand):
                continue
            if int(c2) == int(cur):
                continue
            if int(c2) % 12 not in target_pcs:
                continue
            if prev_pitch is not None and int(c2) == int(prev_pitch):
                continue
            if next_pitch is not None and int(c2) == int(next_pitch):
                continue
            move = abs(int(c2) - int(cur))
            cost = float(move)
            if prev_pitch is not None:
                cost += max(0, abs(int(c2) - int(prev_pitch)) - 7) * 2.2
            if next_pitch is not None:
                cost += max(0, abs(int(next_pitch) - int(c2)) - 7) * 1.4
            cands.append((float(cost), int(c2)))
        if not cands:
            return int(cur)
        cands.sort(key=lambda item: (float(item[0]), abs(int(item[1]) - int(cur))))
        return int(cands[0][1])

    lead_indices = [
        i for i, ev in enumerate(out)
        if isinstance(ev, tuple) and len(ev) == 6 and _lead_pitch(ev) is not None
    ]
    lead_indices.sort(key=lambda i: float(out[i][3]))
    if len(lead_indices) < 2:
        return out, {"enabled": True, "notes_changed": 0}

    sensitive = {
        "love", "caring", "grief", "relief", "fear", "desire", "neutral", "anger", "disgust",
        "confusion", "disappointment", "embarrassment", "remorse", "sadness", "annoyance",
    }
    replaced: Dict[int, Tuple] = {}
    changed = 0
    repeat_run = 0
    prev_pitch: Optional[int] = None
    for pos, idx in enumerate(lead_indices):
        ev = out[idx]
        cur = _lead_pitch(replaced.get(int(idx), ev))
        if cur is None:
            prev_pitch = None
            repeat_run = 0
            continue
        same = prev_pitch is not None and int(cur) == int(prev_pitch)
        repeat_run = int(repeat_run) + 1 if same else 0
        if not same:
            prev_pitch = int(cur)
            continue
        try:
            st = float(ev[3])
            dur = float(ev[4])
        except Exception:
            prev_pitch = int(cur)
            continue
        sec = _section_for_start(float(st))
        if sec is None:
            prev_pitch = int(cur)
            continue
        emotion = str(list(section_emotions)[sec] or "").strip().lower()
        allowed_run = int(max_same_run if emotion in sensitive else max(2, int(max_same_run) + 1))
        if int(repeat_run) < int(allowed_run):
            prev_pitch = int(cur)
            continue
        if float(dur) >= 1.75 or _near_phrase_end(int(sec), float(st), float(dur)):
            prev_pitch = int(cur)
            continue
        next_pitch = None
        if pos + 1 < len(lead_indices):
            next_pitch = _lead_pitch(out[lead_indices[pos + 1]])
        new_pitch = _pick_replacement(
            int(cur),
            sec_i=int(sec),
            st=float(st),
            prev_pitch=prev_pitch,
            next_pitch=next_pitch,
        )
        if int(new_pitch) == int(cur):
            prev_pitch = int(cur)
            continue
        replaced[int(idx)] = (2, int(new_pitch), int(ev[2]), float(st), float(dur), [int(new_pitch)])
        changed += 1
        prev_pitch = int(new_pitch)
        repeat_run = 0

    if replaced:
        out = [replaced.get(i, ev) for i, ev in enumerate(out)]
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {"enabled": True, "notes_changed": int(changed), "max_same_run": int(max_same_run)}


def cap_song_lead_leaps(
    events: Sequence[Event],
    *,
    max_interval: int = 12,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Final whole-song lead leap cap using octave displacement only."""

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out:
        return out, {"enabled": False, "notes_capped": 0}

    indices = [
        i for i, ev in enumerate(out)
        if isinstance(ev, tuple) and len(ev) == 6 and _lead_pitch(ev) is not None
    ]
    indices.sort(key=lambda i: float(out[i][3]))
    if len(indices) < 2:
        return out, {"enabled": True, "notes_capped": 0}

    cap = max(9, min(14, int(max_interval or 12)))
    replaced: Dict[int, Tuple] = {}
    capped = 0
    for prev_i, cur_i in zip(indices, indices[1:]):
        prev_pitch = _lead_pitch(replaced.get(int(prev_i), out[prev_i]))
        cur_pitch = _lead_pitch(out[cur_i])
        if prev_pitch is None or cur_pitch is None:
            continue
        if abs(int(cur_pitch) - int(prev_pitch)) <= int(cap):
            continue
        candidates: List[Tuple[int, int, int]] = []
        for shift in range(-3, 4):
            cand = _clamp_lead_pitch(int(cur_pitch) + 12 * int(shift))
            interval = abs(int(cand) - int(prev_pitch))
            candidates.append((0 if interval <= cap else 1, abs(int(cand) - int(cur_pitch)), int(cand)))
        candidates.sort(key=lambda item: (int(item[0]), int(item[1]), abs(abs(int(item[2]) - int(prev_pitch)) - cap)))
        if not candidates:
            continue
        new_pitch = int(candidates[0][2])
        if int(new_pitch) == int(cur_pitch) or abs(int(new_pitch) - int(prev_pitch)) > int(cap):
            continue
        ev = out[cur_i]
        replaced[int(cur_i)] = (int(ev[0]), int(new_pitch), int(ev[2]), float(ev[3]), float(ev[4]), [int(new_pitch)])
        capped += 1

    if replaced:
        out = [replaced.get(i, ev) for i, ev in enumerate(out)]
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {"enabled": True, "notes_capped": int(capped), "max_interval": int(cap)}

