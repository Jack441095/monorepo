# composition/song_postprocess/form_polish/contours.py
# Phrase-level and note-level emotional contour shaping for the song lead.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .._common import (
    Event,
    _emotion_contour_bias,
    _emotion_scale_pcs_for_section,
    _lead_pitch,
    _nearest_scale_pitch,
    _section_starts,
)


def shape_emotional_lead_contours(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_roots: Sequence[int],
    section_emotions: Sequence[str],
    primary_emotion: Optional[str] = None,
    beats_per_bar: float = 4.0,
    max_shift_semitones: int = 2,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Apply small adjective-driven contour nudges before cadence/harmony repair."""

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "notes_shifted": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=bpb)
    n = min(
        len(starts),
        len(section_bars),
        len(section_roles or []),
        len(section_roots or []),
        len(section_emotions or []),
    )
    if n <= 0:
        return out, {"enabled": False, "notes_shifted": 0}

    ends = [float(starts[i]) + float(int(section_bars[i])) * bpb for i in range(n)]
    scale_by_section = [
        _emotion_scale_pcs_for_section(
            emotion_name=str(primary_emotion or list(section_emotions)[i]),
            root_note=int(list(section_roots)[i]),
        )
        for i in range(n)
    ]

    def _section_for_start(st: float) -> Optional[int]:
        for sec_i in range(n):
            if float(starts[sec_i]) - 1e-6 <= float(st) < float(ends[sec_i]) - 1e-6:
                return int(sec_i)
        return None

    replaced: Dict[int, Tuple] = {}
    shifted = 0
    sections_touched: set[int] = set()
    max_shift = max(1, min(4, int(max_shift_semitones or 2)))
    lead_indices = [
        idx for idx, ev in enumerate(out)
        if isinstance(ev, tuple) and len(ev) == 6 and _lead_pitch(ev) is not None
    ]
    lead_indices.sort(key=lambda idx: float(out[idx][3]))
    lead_pos = {int(idx): int(pos) for pos, idx in enumerate(lead_indices)}

    def _prev_lead_pitch_in_section(idx: int, sec_i: int) -> Optional[int]:
        pos = lead_pos.get(int(idx))
        if pos is None or int(pos) <= 0:
            return None
        for prev_pos in range(int(pos) - 1, -1, -1):
            prev_idx = int(lead_indices[prev_pos])
            try:
                prev_st = float(out[prev_idx][3])
            except Exception:
                continue
            if _section_for_start(float(prev_st)) != int(sec_i):
                return None
            prev_pitch = _lead_pitch(out[prev_idx])
            if prev_pitch is not None:
                return int(prev_pitch)
        return None

    for i, ev in enumerate(out):
        p = _lead_pitch(ev)
        if p is None:
            continue
        try:
            st = float(ev[3])
            dur = float(ev[4])
        except Exception:
            continue
        sec = _section_for_start(float(st))
        if sec is None:
            continue
        sec_len = max(1e-6, float(ends[sec]) - float(starts[sec]))
        progress = max(0.0, min(1.0, (float(st) - float(starts[sec])) / sec_len))
        role = str(list(section_roles)[sec])
        emo = str(primary_emotion or list(section_emotions)[sec])
        bias, begin_at = _emotion_contour_bias(emo, role)
        if int(bias) == 0 or float(progress) < float(begin_at):
            continue
        if float(dur) >= 1.25 and float(progress) >= 0.80:
            continue
        strength = min(1.0, (float(progress) - float(begin_at)) / max(0.08, 1.0 - float(begin_at)))
        raw_shift = int(round(float(bias) * float(strength)))
        if raw_shift == 0:
            raw_shift = 1 if int(bias) > 0 else -1
        raw_shift = max(-max_shift, min(max_shift, int(raw_shift)))
        scale_pcs = set(scale_by_section[sec] or set())
        p2 = _nearest_scale_pitch(int(p) + int(raw_shift), scale_pcs=scale_pcs, prefer_direction=int(raw_shift))
        prev_pitch = _prev_lead_pitch_in_section(int(i), int(sec))
        if prev_pitch is not None and int(bias) < 0 and int(p2) >= int(prev_pitch):
            contour_target = _nearest_scale_pitch(
                int(prev_pitch) - 1,
                scale_pcs=scale_pcs,
                prefer_direction=-1,
            )
            if abs(int(contour_target) - int(p)) <= max_shift:
                p2 = int(contour_target)
        elif prev_pitch is not None and int(bias) > 0 and int(p2) <= int(prev_pitch):
            contour_target = _nearest_scale_pitch(
                int(prev_pitch) + 1,
                scale_pcs=scale_pcs,
                prefer_direction=1,
            )
            if abs(int(contour_target) - int(p)) <= max_shift:
                p2 = int(contour_target)
        if int(p2) == int(p) or abs(int(p2) - int(p)) > max_shift:
            continue
        replaced[int(i)] = (2, int(p2), int(ev[2]), float(st), float(dur), [int(p2)])
        shifted += 1
        sections_touched.add(int(sec))

    if replaced:
        out = [replaced.get(i, ev) for i, ev in enumerate(out)]
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "notes_shifted": int(shifted),
        "sections_touched": int(len(sections_touched)),
        "primary_emotion": str(primary_emotion or ""),
    }


def shape_phrase_level_emotional_contours(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_roots: Sequence[int],
    section_emotions: Sequence[str],
    primary_emotion: Optional[str] = None,
    beats_per_bar: float = 4.0,
    phrase_bars: int = 2,
    max_shift_semitones: int = 3,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Shape phrase endpoints so adjective contour is heard across bars, not just notes."""

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "notes_shifted": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    phrase_len = max(1, min(4, int(phrase_bars or 2)))
    starts = _section_starts(section_bars, beats_per_bar=bpb)
    n = min(
        len(starts),
        len(section_bars),
        len(section_roles or []),
        len(section_roots or []),
        len(section_emotions or []),
    )
    if n <= 0:
        return out, {"enabled": False, "notes_shifted": 0}

    scale_by_section = [
        _emotion_scale_pcs_for_section(
            emotion_name=str(primary_emotion or list(section_emotions)[i]),
            root_note=int(list(section_roots)[i]),
        )
        for i in range(n)
    ]
    replaced: Dict[int, Tuple] = {}
    shifted = 0
    phrases_shaped = 0
    max_shift = max(1, min(5, int(max_shift_semitones or 3)))

    for sec in range(n):
        bars = max(1, int(section_bars[sec]))
        sec_start = float(starts[sec])
        sec_end = sec_start + float(bars) * bpb
        emo = str(primary_emotion or list(section_emotions)[sec])
        role = str(list(section_roles)[sec])
        bias, _begin_at = _emotion_contour_bias(emo, role)
        if int(bias) == 0:
            continue
        heavy_descent = emo in {"grief", "remorse", "sadness"}
        scale_pcs = set(scale_by_section[sec] or set())
        for phrase_start_bar in range(0, bars, phrase_len):
            ph_start = sec_start + float(phrase_start_bar) * bpb
            ph_end = min(sec_end, ph_start + float(phrase_len) * bpb)
            lead_idxs: List[int] = []
            for idx, ev in enumerate(out):
                if idx in replaced or _lead_pitch(ev) is None:
                    continue
                try:
                    st = float(ev[3])
                except Exception:
                    continue
                if ph_start - 1e-6 <= st < ph_end - 1e-6:
                    lead_idxs.append(int(idx))
            if len(lead_idxs) < 3:
                continue
            lead_idxs.sort(key=lambda idx: float(out[idx][3]))
            phrase_changed = False
            if int(bias) < 0:
                mid = max(1, len(lead_idxs) // 3) if heavy_descent else max(1, len(lead_idxs) // 2)
                for pos in range(mid, len(lead_idxs)):
                    idx = int(lead_idxs[pos])
                    if idx in replaced:
                        continue
                    prev_idx = int(lead_idxs[pos - 1])
                    prev_ev = replaced.get(prev_idx, out[prev_idx])
                    cur_ev = out[idx]
                    prev_pitch = _lead_pitch(prev_ev)
                    cur_pitch = _lead_pitch(cur_ev)
                    if prev_pitch is None or cur_pitch is None or int(cur_pitch) < int(prev_pitch):
                        continue
                    target0 = int(cur_pitch) - min(2, max_shift)
                    p_step = _nearest_scale_pitch(target0, scale_pcs=scale_pcs, prefer_direction=-1)
                    if int(p_step) >= int(prev_pitch):
                        p_step = _nearest_scale_pitch(int(prev_pitch) - 1, scale_pcs=scale_pcs, prefer_direction=-1)
                    if int(p_step) == int(cur_pitch) or abs(int(p_step) - int(cur_pitch)) > max_shift:
                        continue
                    replaced[int(idx)] = (
                        2, int(p_step), int(cur_ev[2]), float(cur_ev[3]), float(cur_ev[4]), [int(p_step)]
                    )
                    shifted += 1
                    phrase_changed = True
            elif int(bias) > 0:
                mid = max(1, len(lead_idxs) // 2)
                for pos in range(mid, len(lead_idxs)):
                    idx = int(lead_idxs[pos])
                    if idx in replaced:
                        continue
                    prev_idx = int(lead_idxs[pos - 1])
                    prev_ev = replaced.get(prev_idx, out[prev_idx])
                    cur_ev = out[idx]
                    prev_pitch = _lead_pitch(prev_ev)
                    cur_pitch = _lead_pitch(cur_ev)
                    if prev_pitch is None or cur_pitch is None or int(cur_pitch) > int(prev_pitch):
                        continue
                    target0 = int(cur_pitch) + min(2, max_shift)
                    p_step = _nearest_scale_pitch(target0, scale_pcs=scale_pcs, prefer_direction=1)
                    if int(p_step) <= int(prev_pitch):
                        p_step = _nearest_scale_pitch(int(prev_pitch) + 1, scale_pcs=scale_pcs, prefer_direction=1)
                    if int(p_step) == int(cur_pitch) or abs(int(p_step) - int(cur_pitch)) > max_shift:
                        continue
                    replaced[int(idx)] = (
                        2, int(p_step), int(cur_ev[2]), float(cur_ev[3]), float(cur_ev[4]), [int(p_step)]
                    )
                    shifted += 1
                    phrase_changed = True
            first = _lead_pitch(out[lead_idxs[0]])
            last_idx = int(lead_idxs[-1])
            last = _lead_pitch(replaced.get(last_idx, out[last_idx]))
            if first is not None and last is not None:
                target = int(last)
                if int(bias) < 0 and int(last) >= int(first) - 1:
                    target = int(last) - min(2, max_shift)
                elif int(bias) > 0 and int(last) <= int(first) + 1:
                    target = int(last) + min(2, max_shift)
                if int(target) != int(last):
                    p2 = _nearest_scale_pitch(int(target), scale_pcs=scale_pcs, prefer_direction=int(bias))
                    if abs(int(p2) - int(last)) <= max_shift and int(p2) != int(last):
                        ev = out[last_idx]
                        replaced[int(last_idx)] = (2, int(p2), int(ev[2]), float(ev[3]), float(ev[4]), [int(p2)])
                        shifted += 1
                        phrase_changed = True
            if phrase_changed:
                phrases_shaped += 1

    if replaced:
        out = [replaced.get(i, ev) for i, ev in enumerate(out)]
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "notes_shifted": int(shifted),
        "phrases_shaped": int(phrases_shaped),
        "primary_emotion": str(primary_emotion or ""),
    }

