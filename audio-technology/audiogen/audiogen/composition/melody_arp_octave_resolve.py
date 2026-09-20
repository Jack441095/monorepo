# composition/melody_arp_octave_resolve.py — post-pass: move lead by octave vs arp clashes.

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from midi.midi_range_limiter import RANGE_LIMITER


def _pitch_from_ev(ev: Tuple) -> Optional[int]:
    if not (isinstance(ev, tuple) and len(ev) == 6):
        return None
    try:
        return int(ev[5][0]) if isinstance(ev[5], list) and ev[5] else int(ev[1])
    except Exception:
        return None


def _arp_intervals(arp_events: List[Tuple]) -> List[Tuple[float, float, int]]:
    out: List[Tuple[float, float, int]] = []
    for ev in list(arp_events or []):
        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 3):
            continue
        try:
            st = float(ev[3])
            en = st + float(ev[4])
        except Exception:
            continue
        if en <= st + 1e-9:
            continue
        p = _pitch_from_ev(ev)
        if p is None:
            continue
        out.append((st, en, int(p)))
    return out


def _overlaps_arp_clash(
    *,
    pm: int,
    sm: float,
    em: float,
    arp_ints: List[Tuple[float, float, int]],
    clash_max_semitones: int,
) -> bool:
    mx = max(0, min(24, int(clash_max_semitones)))
    for sa, ea, pa in arp_ints:
        if float(em) <= float(sa) + 1e-9 or float(sm) >= float(ea) - 1e-9:
            continue
        if abs(int(pm) - int(pa)) <= mx:
            return True
    return False


def resolve_melody_octaves_vs_arp_clashes(
    melody_events: List[Tuple],
    arp_events: List[Tuple],
    *,
    enabled: bool,
    clash_max_semitones: int = 0,
    prefer_up: bool = True,
    melody_channel: int = 2,
) -> List[Tuple]:
    """Return a new melody event list with ±12 shifts where lead overlaps arp on a clashing pitch."""
    if not enabled:
        return list(melody_events or [])
    arp_ints = _arp_intervals(list(arp_events or []))
    if not arp_ints:
        return list(melody_events or [])

    mx = max(0, min(24, int(clash_max_semitones)))
    out: List[Tuple] = []
    for ev in list(melody_events or []):
        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
            out.append(ev)
            continue
        ch, midi, vel, st, dur, notes = ev
        try:
            sm = float(st)
            em = sm + float(dur)
        except Exception:
            out.append(ev)
            continue
        if em <= sm + 1e-9:
            out.append(ev)
            continue
        pm = _pitch_from_ev(ev)
        if pm is None:
            out.append(ev)
            continue
        if not _overlaps_arp_clash(pm=pm, sm=sm, em=em, arp_ints=arp_ints, clash_max_semitones=mx):
            out.append(ev)
            continue

        deltas = (12, -12) if bool(prefer_up) else (-12, 12)
        chosen: Optional[int] = None
        for d in deltas:
            try:
                p2 = int(RANGE_LIMITER.clamp_note(int(pm) + int(d), int(melody_channel)))
            except Exception:
                continue
            if int(p2) == int(pm):
                continue
            if not _overlaps_arp_clash(pm=p2, sm=sm, em=em, arp_ints=arp_ints, clash_max_semitones=mx):
                chosen = int(p2)
                break
        if chosen is None:
            out.append(ev)
            continue
        n2 = list(notes) if isinstance(notes, list) else notes
        if isinstance(n2, list) and n2:
            try:
                n2[0] = int(chosen)
            except Exception:
                pass
        out.append((int(ch), int(chosen), int(vel), float(st), float(dur), n2))
    return out


def resolve_melody_unisons_vs_arp_by_interval(
    melody_events: List[Tuple],
    arp_events: List[Tuple],
    *,
    enabled: bool,
    interval_semitones: int = 7,
    melody_channel: int = 2,
) -> List[Tuple]:
    """Shift exact overlapping lead/arp unisons by a configured interval."""
    if not enabled:
        return list(melody_events or [])
    arp_ints = _arp_intervals(list(arp_events or []))
    if not arp_ints:
        return list(melody_events or [])
    interval = max(1, min(12, abs(int(interval_semitones))))
    out: List[Tuple] = []
    for ev in list(melody_events or []):
        if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == melody_channel):
            out.append(ev)
            continue
        ch, midi, vel, start, duration, notes = ev
        pitch = _pitch_from_ev(ev)
        try:
            start_f = float(start)
            end_f = start_f + float(duration)
        except Exception:
            out.append(ev)
            continue
        exact_unison = any(
            end_f > arp_start + 1e-9
            and start_f < arp_end - 1e-9
            and pitch == arp_pitch
            for arp_start, arp_end, arp_pitch in arp_ints
        )
        if pitch is None or not exact_unison:
            out.append(ev)
            continue
        shifted = int(RANGE_LIMITER.clamp_note(pitch + interval, melody_channel))
        shifted_notes = list(notes) if isinstance(notes, list) else notes
        if isinstance(shifted_notes, list) and shifted_notes:
            shifted_notes[0] = shifted
        out.append((int(ch), shifted, int(vel), start_f, float(duration), shifted_notes))
    return out


def _snap_pitch(pitch: int, scale_pcs: set[int], melody_channel: int) -> int:
    try:
        pitch = int(RANGE_LIMITER.clamp_note(int(pitch), int(melody_channel)))
    except Exception:
        pass
    if not scale_pcs or (pitch % 12) in scale_pcs:
        return pitch
    best_cand = pitch
    best_dist = 999.0
    for cand in range(pitch - 12, pitch + 13):
        if (cand % 12) in scale_pcs:
            try:
                clamped = int(RANGE_LIMITER.clamp_note(cand, melody_channel))
            except Exception:
                clamped = cand
            if (clamped % 12) in scale_pcs:
                dist = abs(clamped - pitch)
                if dist < best_dist:
                    best_dist = dist
                    best_cand = clamped
    if best_cand == pitch and pitch % 12 not in scale_pcs:
        for cand in range(pitch - 12, pitch + 13):
            if (cand % 12) in scale_pcs:
                dist = abs(cand - pitch)
                if dist < best_dist:
                    best_dist = dist
                    best_cand = cand
    return best_cand


def snap_lead_events_to_strict_scale(
    events: List[Tuple],
    emotion: Any,
    section_root_pc: int,
    melody_channel: int = 2,
) -> List[Tuple]:
    """Snap melody/counter-melody events to the emotion's strict perceptual scale."""
    try:
        intervals = getattr(emotion, "scale_intervals", None)
        if not intervals:
            return list(events or [])
        scale_pcs = {(int(section_root_pc) + int(iv)) % 12 for iv in intervals}
        if not scale_pcs:
            return list(events or [])
            
        out = []
        for ev in list(events or []):
            if not (isinstance(ev, tuple) and len(ev) == 6):
                out.append(ev)
                continue
            ch, midi, vel, st, dur, notes = ev
            if int(ch) != int(melody_channel):
                out.append(ev)
                continue
                
            midi2 = _snap_pitch(int(midi), scale_pcs, melody_channel)
            notes2 = notes
            if isinstance(notes, list):
                notes2 = []
                for n in notes:
                    try:
                        notes2.append(_snap_pitch(int(n), scale_pcs, melody_channel))
                    except Exception:
                        notes2.append(n)
            out.append((int(ch), int(midi2), int(vel), float(st), float(dur), notes2))
        return out
    except Exception:
        return list(events or [])
