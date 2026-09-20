# composition/song_postprocess/form_polish/chorus_registers.py
# Chorus register/payoff shaping: brighter chorus payoffs, register lift for
# bright choruses, and chorus melodic-action reinforcement.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .._common import (
    Event,
    _active_chord_pcs_at,
    _build_chord_windows,
    _clamp_lead_pitch,
    _emotion_scale_pcs_for_section,
    _lead_between,
    _lead_pitch,
    _reharmonize_inserted_lead_pitch,
    _section_starts,
    _snap_inserted_pitch_to_section_scale,
)


def reinforce_bright_chorus_payoffs(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_emotions: Sequence[str],
    beats_per_bar: float = 4.0,
    strength: float = 0.72,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Restate bright chorus openings when realized chorus coverage falls below verse coverage."""

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False}
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return out, {"enabled": False, "strength": float(s)}

    starts = _section_starts(section_bars, beats_per_bar=bpb)
    roles = [str(r or "").strip().lower() for r in list(section_roles or [])]
    emotions = [str(e or "").strip().lower() for e in list(section_emotions or [])]
    n = min(len(starts), len(roles), len(emotions), len(section_bars))
    bright = {"amusement", "excitement", "joy", "surprise"}
    verse_roles = {"a", "verse"}
    chorus_roles = {"b", "chorus", "hook"}

    verse_cov_by_emotion: Dict[str, List[float]] = {}
    for i in range(n):
        if roles[i] not in verse_roles:
            continue
        start = float(starts[i])
        end = start + float(section_bars[i]) * bpb
        lead = _lead_between(out, start, end)
        cov = float(sum(max(0.0, float(ev[4])) for ev in lead)) / max(1e-9, end - start)
        verse_cov_by_emotion.setdefault(emotions[i], []).append(float(cov))

    inserted: List[Tuple] = []
    choruses_reinforced = 0
    notes_added = 0
    for i in range(n):
        emotion = emotions[i]
        if emotion not in bright or roles[i] not in chorus_roles:
            continue
        verse_covs = verse_cov_by_emotion.get(emotion, [])
        if not verse_covs:
            continue
        start = float(starts[i])
        end = start + float(section_bars[i]) * bpb
        lead = _lead_between(out, start, end)
        chorus_cov = float(sum(max(0.0, float(ev[4])) for ev in lead)) / max(1e-9, end - start)
        verse_cov = float(sum(verse_covs) / len(verse_covs))
        if chorus_cov >= verse_cov * (0.92 - 0.08 * s):
            continue
        span = min(2.0 * bpb, max(bpb, end - start))
        opening = [ev for ev in lead if start - 1e-6 <= float(ev[3]) < start + span - 1e-6]
        if len(opening) < 3:
            continue
        final_start = max(start, end - span)
        ending = [ev for ev in lead if final_start - 1e-6 <= float(ev[3]) < end - 1e-6]
        opening_beats = float(sum(max(0.0, float(ev[4])) for ev in opening))
        ending_beats = float(sum(max(0.0, float(ev[4])) for ev in ending))
        if ending_beats >= opening_beats * (0.84 - 0.12 * s):
            continue
        occupied = {round(float(ev[3]), 6) for ev in ending}
        local_added = 0
        for ev in opening:
            rel = float(ev[3]) - start
            dst = round(final_start + rel, 6)
            if dst >= end - bpb - 1e-6 or dst in occupied:
                continue
            pitch = _lead_pitch(ev)
            if pitch is None:
                continue
            vel = max(1, min(127, int(ev[2]) + 3))
            inserted.append((2, int(pitch), int(vel), float(dst), float(ev[4]), [int(pitch)]))
            occupied.add(dst)
            local_added += 1
        if local_added:
            choruses_reinforced += 1
            notes_added += local_added

    if inserted:
        out.extend(inserted)
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))
    return out, {
        "enabled": True,
        "strength": float(s),
        "choruses_reinforced": int(choruses_reinforced),
        "notes_added": int(notes_added),
    }


def lift_bright_chorus_registers(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_emotions: Sequence[str],
    beats_per_bar: float = 4.0,
    min_lift_semitones: int = 2,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Octave-lift bright choruses whose realized lead median does not clear the verse."""

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False}
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=bpb)
    roles = [str(r or "").strip().lower() for r in list(section_roles or [])]
    emotions = [str(e or "").strip().lower() for e in list(section_emotions or [])]
    n = min(len(starts), len(roles), len(emotions), len(section_bars))
    bright = {"amusement", "excitement", "joy", "optimism", "surprise"}

    verse_pitches: Dict[str, List[int]] = {}
    section_ranges: List[Tuple[float, float]] = []
    for i in range(n):
        start = float(starts[i])
        end = start + float(section_bars[i]) * bpb
        section_ranges.append((start, end))
        if roles[i] in {"a", "verse"}:
            verse_pitches.setdefault(emotions[i], []).extend(
                int(p) for ev in _lead_between(out, start, end) if (p := _lead_pitch(ev)) is not None
            )

    replacements: Dict[int, Tuple] = {}
    sections_lifted = 0
    notes_lifted = 0
    for i in range(n):
        emotion = emotions[i]
        if emotion not in bright or roles[i] not in {"b", "chorus", "hook"}:
            continue
        vp = sorted(verse_pitches.get(emotion, []))
        if not vp:
            continue
        start, end = section_ranges[i]
        lead = _lead_between(out, start, end)
        cp = sorted(int(p) for ev in lead if (p := _lead_pitch(ev)) is not None)
        if not cp:
            continue
        verse_med = int(vp[len(vp) // 2])
        chorus_med = int(cp[len(cp) // 2])
        if chorus_med >= verse_med + int(min_lift_semitones):
            continue
        # Keep the whole line in a normal lead range after the octave move.
        if max(cp) + 12 > 84:
            continue
        local = 0
        for idx, ev in enumerate(out):
            pitch = _lead_pitch(ev)
            if pitch is None:
                continue
            st = float(ev[3])
            if not (start - 1e-6 <= st < end - 1e-6):
                continue
            new_pitch = int(pitch) + 12
            replacements[idx] = (2, int(new_pitch), int(ev[2]), float(ev[3]), float(ev[4]), [int(new_pitch)])
            local += 1
        if local:
            sections_lifted += 1
            notes_lifted += local

    if replacements:
        out = [replacements.get(i, ev) for i, ev in enumerate(out)]
    return out, {
        "enabled": True,
        "sections_lifted": int(sections_lifted),
        "notes_lifted": int(notes_lifted),
    }


def reinforce_chorus_melody_action(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_roots: Sequence[int],
    section_emotions: Sequence[str],
    beats_per_bar: float = 4.0,
    strength: float = 0.78,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Late full-song lead activity repair for chorus sections."""

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "added_notes": 0}
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return out, {"enabled": False, "added_notes": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    chord_windows = _build_chord_windows(out)
    added: List[Tuple] = []
    sections_repaired = 0

    def _is_chorus(role: str) -> bool:
        return str(role or "").strip().lower() in {"b", "chorus", "hook", "tag"}

    def _has_near_lead(start: float, eps: float = 0.16) -> bool:
        for ev in list(out) + list(added):
            if _lead_pitch(ev) is None:
                continue
            try:
                if abs(float(ev[3]) - float(start)) <= float(eps):
                    return True
            except Exception:
                continue
        return False

    def _lead_before(start: float) -> Optional[int]:
        prev = None
        for ev in sorted(list(out) + list(added), key=lambda e: float(e[3])):
            if _lead_pitch(ev) is None:
                continue
            try:
                if float(ev[3]) >= float(start) - 1e-6:
                    break
            except Exception:
                continue
            prev = _lead_pitch(ev)
        return int(prev) if prev is not None else None

    def _allowed_pcs(root: int, emotion: str, start: float) -> set[int]:
        scale_pcs = _emotion_scale_pcs_for_section(emotion_name=str(emotion), root_note=int(root))
        chord_pcs = _active_chord_pcs_at(chord_windows, float(start), beats_per_bar=float(bpb))
        if scale_pcs and chord_pcs:
            return set(scale_pcs & chord_pcs) or set(chord_pcs) or set(scale_pcs)
        return set(chord_pcs or scale_pcs)

    def _nearest_allowed(target: int, pcs: set[int]) -> int:
        if not pcs:
            return _clamp_lead_pitch(int(target))
        best = _clamp_lead_pitch(int(target))
        best_key = (10**9, 10**9)
        for cand in range(int(target) - 14, int(target) + 15):
            if int(cand) % 12 not in pcs:
                continue
            c = _clamp_lead_pitch(int(cand))
            key = (abs(int(c) - int(target)), abs(int(c) - 74))
            if key < best_key:
                best = int(c)
                best_key = key
        return int(best)

    n = min(len(starts), len(section_bars), len(section_roles or []))
    for i in range(n):
        role = str(section_roles[i])
        if not _is_chorus(role):
            continue
        try:
            bars = int(section_bars[i])
        except Exception:
            bars = 0
        if bars <= 0:
            continue
        sec_start = float(starts[i])
        sec_end = sec_start + float(bars) * float(bpb)
        root = int(section_roots[i]) if i < len(section_roots or []) else 60
        emotion = str(section_emotions[i]) if i < len(section_emotions or []) else ""
        emotion_lc = str(emotion).strip().lower()
        slowish = emotion_lc in {"sadness", "grief", "remorse", "disappointment", "relief", "love", "caring"}
        urgent_payoff = emotion_lc in {"anger", "disgust", "fear", "nervousness"}
        payoff_emotion = emotion_lc in {
            "anger",
            "amusement",
            "curiosity",
            "disgust",
            "excitement",
            "fear",
            "joy",
            "nervousness",
            "optimism",
            "pride",
            "surprise",
        }

        counts = [0 for _ in range(bars)]
        dur_by_bar = [0.0 for _ in range(bars)]
        for ev in out:
            if _lead_pitch(ev) is None:
                continue
            try:
                st = float(ev[3])
                dur = float(ev[4])
            except Exception:
                continue
            if not (sec_start - 1e-6 <= st < sec_end - 1e-6):
                continue
            bi = int((st - sec_start) // float(bpb))
            if 0 <= bi < bars:
                counts[bi] += 1
            b0 = int(max(0, (st - sec_start) // float(bpb)))
            b1 = int(min(bars - 1, ((st + max(0.0, dur) - 1e-6) - sec_start) // float(bpb)))
            for bj in range(max(0, b0), min(bars, b1 + 1)):
                lo = sec_start + float(bj) * float(bpb)
                hi = lo + float(bpb)
                dur_by_bar[bj] += max(0.0, min(st + dur, hi) - max(st, lo))

        if payoff_emotion:
            target_avg = (8.65 if urgent_payoff else 8.20) + 0.65 * float(s)
            floor = 9 if urgent_payoff and s >= 0.65 else (8 if s >= 0.70 else 7)
        else:
            target_avg = 5.95 + 0.45 * float(s) + (0.25 if slowish else 0.0)
            floor = 5 + (1 if s >= 0.82 else 0)
        target_total = int(round(float(bars) * float(target_avg)))
        if sum(counts) >= target_total and min(counts or [floor]) >= max(3, floor - 1):
            continue

        offsets = [0.5, 1.0, 1.75, 2.5, 3.25]
        max_add_base = 1.65 if urgent_payoff else (1.25 if payoff_emotion else 0.95)
        max_add = int(max(1, round(float(bars) * (max_add_base + 0.95 * float(s)))))
        local_added = 0
        bar_order = sorted(range(bars), key=lambda bi: (int(counts[bi]), float(dur_by_bar[bi])))
        for bi in bar_order:
            if local_added >= max_add or sum(counts) >= target_total:
                break
            local_floor = int(floor)
            if bi == bars - 1:
                local_floor = max(3, local_floor - 1)
            for off in offsets:
                if local_added >= max_add:
                    break
                if counts[bi] >= local_floor and sum(counts) >= target_total:
                    break
                st = sec_start + float(bi) * float(bpb) + min(float(off), float(bpb) - 0.28)
                if _has_near_lead(st):
                    continue
                prev = _lead_before(st)
                if prev is None:
                    prev = int(root) + 14
                direction = 1 if (bi + local_added) % 2 == 0 else -1
                target_pitch = int(prev) + int(direction) * (2 if slowish else 3)
                if payoff_emotion:
                    target_pitch = 74 + (2 if direction > 0 else -1) + (1 if bi % 4 >= 2 else 0)
                pitch = _nearest_allowed(
                    int(target_pitch),
                    _allowed_pcs(int(root), str(emotion), float(st)),
                )
                dur = 0.34 + (0.08 if slowish else 0.0)
                pitch = _reharmonize_inserted_lead_pitch(
                    int(pitch),
                    start_beat=float(st),
                    duration_beats=float(dur),
                    chord_windows=chord_windows,
                    beats_per_bar=float(bpb),
                    force=False,
                )
                pitch = _snap_inserted_pitch_to_section_scale(
                    int(pitch),
                    scale_pcs=_emotion_scale_pcs_for_section(emotion_name=str(emotion), root_note=int(root)),
                    chord_pcs=_active_chord_pcs_at(chord_windows, float(st), beats_per_bar=float(bpb)),
                )
                velocity = 68 + (-2 if slowish else 3)
                added.append((2, int(pitch), int(max(1, min(127, velocity))), float(st), float(dur), [int(pitch)]))
                counts[bi] += 1
                local_added += 1
        if local_added:
            sections_repaired += 1

    if added:
        out = sorted(list(out) + list(added), key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))
    return out, {
        "enabled": True,
        "strength": float(s),
        "sections_repaired": int(sections_repaired),
        "added_notes": int(len(added)),
    }

