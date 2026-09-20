# composition/song_postprocess/form_polish/reflective.py
# Reflective/introspective emotion shaping: chorus breathing space, song-level
# negative space, and a register guard for reflective choruses.

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from .._common import Event, _lead_pitch, _section_starts


def shape_reflective_chorus_breathing(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_emotions: Sequence[str],
    primary_emotion: str = "",
    beats_per_bar: float = 4.0,
    target_notes_per_bar: float = 6.4,
    max_coverage_ratio: float = 0.78,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Give reflective choruses phrase space without muting the main hook."""

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "removed_notes": 0, "shortened_notes": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    n = min(len(starts), len(section_bars), len(section_roles or []), len(section_emotions or []))
    reflective = {"sadness", "grief", "remorse", "disappointment", "relief", "caring", "embarrassment"}
    primary_is_reflective = str(primary_emotion or "").strip().lower() in reflective
    remove_ids: set[int] = set()
    replace: Dict[int, Tuple] = {}
    sections_shaped = 0

    def _is_chorus(role: str) -> bool:
        return str(role or "").strip().lower() in {"b", "chorus", "hook", "tag"}

    def _strong_or_cadence(local: float, bars: int, st: float, sec_start: float) -> bool:
        pos = float(local) % float(bpb)
        if abs(pos - 0.0) <= 0.08 or abs(pos - 2.0) <= 0.08:
            return True
        bar = int((float(st) - float(sec_start)) // float(bpb))
        return bool(bar >= max(0, int(bars) - 1))

    for sec in range(n):
        role = str(section_roles[sec] or "")
        emotion = str(section_emotions[sec] or "").strip().lower()
        if not _is_chorus(role) or (emotion not in reflective and not primary_is_reflective):
            continue
        bars = max(0, int(section_bars[sec]))
        if bars <= 0:
            continue
        sec_start = float(starts[sec])
        sec_end = sec_start + float(bars) * float(bpb)
        lead_indices: List[int] = []
        total_dur = 0.0
        for i, ev in enumerate(out):
            if _lead_pitch(ev) is None:
                continue
            try:
                st = float(ev[3])
                dur = max(0.0, float(ev[4]))
            except Exception:
                continue
            if not (sec_start - 1e-6 <= st < sec_end - 1e-6):
                continue
            lead_indices.append(int(i))
            total_dur += min(float(dur), max(0.0, sec_end - st))
        if not lead_indices:
            continue

        target_count = max(1, int(round(float(bars) * float(target_notes_per_bar))))
        coverage = float(total_dur) / max(1e-6, float(bars) * float(bpb))
        if len(lead_indices) <= target_count and coverage <= float(max_coverage_ratio):
            continue

        def _candidate_key(i: int) -> Tuple[int, float, float]:
            ev = out[i]
            st = float(ev[3])
            dur = float(ev[4])
            local = float(st) - float(sec_start)
            protected = _strong_or_cadence(local, bars, st, sec_start) or dur >= 0.95
            # Later offbeat short notes are safest to remove first.
            return (1 if protected else 0, -float(local), -float(dur))

        removed_here = 0
        for idx in sorted(lead_indices, key=_candidate_key):
            if len(lead_indices) - removed_here <= target_count:
                break
            ev = out[idx]
            st = float(ev[3])
            dur = float(ev[4])
            local = float(st) - float(sec_start)
            if _strong_or_cadence(local, bars, st, sec_start) or dur >= 0.95:
                continue
            remove_ids.add(int(idx))
            coverage -= max(0.0, float(dur)) / max(1e-6, float(bars) * float(bpb))
            removed_here += 1

        shortened_here = 0
        if coverage > float(max_coverage_ratio):
            for idx in sorted(lead_indices, key=lambda i: -float(out[i][4])):
                if idx in remove_ids or coverage <= float(max_coverage_ratio):
                    continue
                ev = out[idx]
                st = float(ev[3])
                dur = float(ev[4])
                local = float(st) - float(sec_start)
                if dur < 0.85 or _strong_or_cadence(local, bars, st, sec_start):
                    continue
                new_dur = max(0.55, float(dur) * 0.82)
                if new_dur >= dur - 1e-6:
                    continue
                replace[int(idx)] = (int(ev[0]), int(ev[1]), int(ev[2]), float(st), float(new_dur), list(ev[5]))
                coverage -= (float(dur) - float(new_dur)) / max(1e-6, float(bars) * float(bpb))
                shortened_here += 1

        if removed_here or shortened_here:
            sections_shaped += 1

    if remove_ids or replace:
        out2 = []
        for i, ev in enumerate(out):
            if int(i) in remove_ids:
                continue
            out2.append(replace.get(int(i), ev))
        out = sorted(out2, key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "sections_shaped": int(sections_shaped),
        "removed_notes": int(len(remove_ids)),
        "shortened_notes": int(len(replace)),
    }


def shape_reflective_song_negative_space(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_emotions: Sequence[str],
    primary_emotion: str = "",
    beats_per_bar: float = 4.0,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Create song-wide breath for reflective adjectives while preserving hook anchors."""

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "removed_notes": 0, "shortened_notes": 0}

    reflective = {"sadness", "grief", "remorse", "disappointment", "caring", "love", "relief", "desire", "embarrassment"}
    primary = str(primary_emotion or "").strip().lower()
    if primary not in reflective:
        return out, {"enabled": True, "sections_shaped": 0, "removed_notes": 0, "shortened_notes": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    n = min(len(starts), len(section_bars), len(section_roles or []), len(section_emotions or []))
    remove_ids: set[int] = set()
    replace: Dict[int, Tuple] = {}
    sections_shaped = 0

    def _targets(role: str) -> Tuple[float, float]:
        role0 = str(role or "").strip().lower()
        if primary == "embarrassment":
            if role0 in {"intro", "outro", "ending"}:
                return (3.0, 0.60)
            if role0 in {"a", "verse"}:
                return (4.1, 0.66)
            if role0 == "pre_chorus":
                return (4.6, 0.68)
            if role0 in {"b", "chorus", "hook", "tag"}:
                return (5.6, 0.72)
            return (4.1, 0.66)
        if role0 in {"intro", "outro", "ending"}:
            return (3.4, 0.66)
        if role0 in {"a", "verse"}:
            return (4.6, 0.72)
        if role0 == "pre_chorus":
            return (5.2, 0.74)
        if role0 in {"b", "chorus", "hook", "tag"}:
            return (6.2, 0.78)
        return (4.8, 0.72)

    def _protected(local: float, bars: int, st: float, dur: float) -> bool:
        pos = float(local) % bpb
        if abs(pos - 0.0) <= 0.08 or abs(pos - 2.0) <= 0.08:
            return True
        bar = int(max(0, min(int(bars) - 1, int(local // bpb))))
        if bar >= max(0, int(bars) - 1):
            return True
        return bool(float(dur) >= 1.10)

    for sec in range(n):
        role = str(section_roles[sec] or "")
        emotion = str(section_emotions[sec] or "").strip().lower()
        if emotion not in reflective and primary not in reflective:
            continue
        bars = max(1, int(section_bars[sec]))
        sec_start = float(starts[sec])
        sec_end = sec_start + float(bars) * bpb
        lead_idxs: List[int] = []
        total_dur = 0.0
        for idx, ev in enumerate(out):
            if _lead_pitch(ev) is None:
                continue
            try:
                st = float(ev[3])
                dur = max(0.0, float(ev[4]))
            except Exception:
                continue
            if sec_start - 1e-6 <= st < sec_end - 1e-6:
                lead_idxs.append(int(idx))
                total_dur += min(float(dur), max(0.0, sec_end - st))
        if not lead_idxs:
            continue
        target_npb, target_cov = _targets(role)
        if primary in {"grief", "remorse", "sadness"}:
            target_npb -= 0.35
            target_cov -= 0.04
        target_count = max(1, int(round(float(bars) * float(target_npb))))
        coverage = total_dur / max(1e-6, float(bars) * bpb)
        if len(lead_idxs) <= target_count and coverage <= target_cov:
            continue

        def _remove_key(idx: int) -> Tuple[int, float, float]:
            ev = out[idx]
            st = float(ev[3])
            dur = float(ev[4])
            local = st - sec_start
            prot = _protected(local, bars, st, dur)
            offbeat_distance = min(abs((local % bpb) - 0.0), abs((local % bpb) - 2.0))
            return (1 if prot else 0, -float(offbeat_distance), -float(local))

        removed_here = 0
        for idx in sorted(lead_idxs, key=_remove_key):
            if len(lead_idxs) - removed_here <= target_count:
                break
            ev = out[idx]
            st = float(ev[3])
            dur = float(ev[4])
            local = st - sec_start
            if _protected(local, bars, st, dur):
                continue
            remove_ids.add(int(idx))
            coverage -= max(0.0, float(dur)) / max(1e-6, float(bars) * bpb)
            removed_here += 1

        shortened_here = 0
        if coverage > target_cov:
            for idx in sorted(lead_idxs, key=lambda j: -float(out[j][4])):
                if idx in remove_ids or coverage <= target_cov:
                    continue
                ev = out[idx]
                st = float(ev[3])
                dur = float(ev[4])
                local = st - sec_start
                if dur < 0.70 or _protected(local, bars, st, dur):
                    continue
                new_dur = max(0.42, float(dur) * 0.74)
                if new_dur >= dur - 1e-6:
                    continue
                replace[int(idx)] = (2, int(ev[1]), int(ev[2]), float(st), float(new_dur), list(ev[5]))
                coverage -= (float(dur) - float(new_dur)) / max(1e-6, float(bars) * bpb)
                shortened_here += 1

        if removed_here or shortened_here:
            sections_shaped += 1

    if remove_ids or replace:
        out2: List[Tuple] = []
        for i, ev in enumerate(out):
            if int(i) in remove_ids:
                continue
            out2.append(replace.get(int(i), ev))
        out = sorted(out2, key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "sections_shaped": int(sections_shaped),
        "removed_notes": int(len(remove_ids)),
        "shortened_notes": int(len(replace)),
        "primary_emotion": str(primary_emotion or ""),
    }


def guard_reflective_chorus_register(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_emotions: Sequence[str],
    beats_per_bar: float = 4.0,
    note_ceiling: int = 79,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Cap reflective chorus peaks without flattening the whole chorus lift."""

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "notes_shifted": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    n = min(len(starts), len(section_bars), len(section_roles or []), len(section_emotions or []))
    reflective = {"sadness", "grief", "remorse", "disappointment", "relief", "caring"}
    replacements: Dict[int, Tuple] = {}
    sections_shifted = 0

    def _is_chorus(role: str) -> bool:
        return str(role or "").strip().lower() in {"b", "chorus", "hook", "tag"}

    for sec in range(n):
        role = str(section_roles[sec] or "")
        emotion = str(section_emotions[sec] or "").strip().lower()
        if emotion not in reflective or not _is_chorus(role):
            continue
        sec_start = float(starts[sec])
        sec_end = sec_start + float(int(section_bars[sec])) * float(bpb)
        lead_indices: List[int] = []
        pitches: List[int] = []
        for i, ev in enumerate(out):
            p = _lead_pitch(ev)
            if p is None:
                continue
            try:
                st = float(ev[3])
            except Exception:
                continue
            if sec_start - 1e-6 <= st < sec_end - 1e-6:
                lead_indices.append(int(i))
                pitches.append(int(p))
        if not pitches:
            continue
        if max(pitches) <= int(note_ceiling):
            continue
        local_shifted = 0
        for idx in lead_indices:
            ev = out[idx]
            p = _lead_pitch(ev)
            if p is None:
                continue
            if int(p) <= int(note_ceiling):
                continue
            # Drop only ceiling notes by an octave when they stay in a normal lead register.
            if int(p) - 12 < 57:
                continue
            p2 = int(p) - 12
            replacements[int(idx)] = (2, int(p2), int(ev[2]), float(ev[3]), float(ev[4]), [int(p2)])
            local_shifted += 1
        if local_shifted:
            sections_shifted += 1

    if replacements:
        out = [replacements.get(i, ev) for i, ev in enumerate(out)]
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "sections_shifted": int(sections_shifted),
        "notes_shifted": int(len(replacements)),
    }

