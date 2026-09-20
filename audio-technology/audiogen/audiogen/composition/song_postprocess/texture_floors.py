"""Song postprocess: texture_floors."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple


from composition.section_planner.section_dynamics_stage import (
    LIGHT_COUNTERLINE_FLOOR_EMOTIONS,
    RICH_COUNTER_EMOTIONS,
    SPARSE_COUNTER_EMOTIONS,
)

from ._common import (
    Event,
    _active_chord_pcs_at,
    _build_chord_windows,
    _clamp_lead_pitch,
    _emotion_scale_pcs_for_section,
    _lead_pitch,
    _section_starts,
)

# Phase-C audit: lead/arp masking outliers (pride, anger, amusement; love moderate).
_HIGH_LEAD_ARP_OVERLAP_PRIMARIES = frozenset({"pride", "anger", "amusement", "love"})



def reinforce_chorus_counterline_floor(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_roots: Sequence[int],
    section_emotions: Sequence[str],
    primary_emotion: str = "",
    beats_per_bar: float = 4.0,
    min_gestures: int = 3,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Ensure each chorus has a small counterline bed for texture contrast."""

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "added_counter_events": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    n = min(len(starts), len(section_bars), len(section_roles or []), len(section_roots or []), len(section_emotions or []))
    added: List[Tuple] = []

    def _is_chorus(role: str) -> bool:
        return str(role or "").strip().lower() in {"b", "chorus", "hook", "tag"}

    try:
        from data.emotion_aliases import canonical_emotion_name

        primary_emo = canonical_emotion_name(str(primary_emotion or "").strip().lower())
    except Exception:
        primary_emo = str(primary_emotion or "").strip().lower()

    verse_light_filled = False

    def _section_emotion(sec: int) -> str:
        try:
            from data.emotion_aliases import canonical_emotion_name

            return canonical_emotion_name(
                str(primary_emotion or section_emotions[sec] or "").strip().lower()
            )
        except Exception:
            return str(primary_emotion or section_emotions[sec] or "").strip().lower()

    def _counter_in_section(sec_start: float, sec_end: float) -> int:
        count = 0
        for ev in out:
            try:
                if int(ev[0]) != 5:
                    continue
                st = float(ev[3])
            except Exception:
                continue
            if sec_start - 1e-6 <= st < sec_end - 1e-6:
                count += 1
        return int(count)

    def _append_counter_gestures(
        *,
        sec: int,
        sec_start: float,
        bars: int,
        need: int,
        light: bool,
    ) -> None:
        if need <= 0:
            return
        try:
            from data.emotion_aliases import canonical_emotion_name
            from data.emotion_scales import melody_scale_intervals_for_emotion
            from data.music_data import EMOTION_BY_NAME

            emo_name = canonical_emotion_name(
                str(primary_emotion or section_emotions[sec] or "").strip().lower()
            )
            emo_obj = EMOTION_BY_NAME.get(emo_name, emo_name)
            scale = list(melody_scale_intervals_for_emotion(emo_obj) or [0, 2, 4, 5, 7, 9, 11])
        except Exception:
            scale = [0, 2, 4, 5, 7, 9, 11]
        if len(scale) < 3:
            scale = [0, 2, 4, 5, 7, 9, 11]
        root = int(section_roots[sec])
        gestures = int(need)
        phrase_beats = max(float(bpb), float(bars) * float(bpb) / float(max(1, gestures)))
        for g in range(gestures):
            degree = (2 + g) % max(1, len(scale))
            midi = int(root) + int(scale[degree]) - 12
            if midi < 48:
                midi += 12
            if midi > 76:
                midi -= 12
            st = sec_start + float(g) * phrase_beats + min(1.25, float(bpb) * 0.25)
            vel = 40 + 2 * g if light else 44 + 3 * g
            dur = 0.55 if light else 0.65
            added.append((5, int(midi), int(vel), float(st), float(dur), [int(midi)]))

    for sec in range(n):
        role = str(section_roles[sec] or "").strip().lower()
        sec_emo = _section_emotion(sec)
        sparse = sec_emo in SPARSE_COUNTER_EMOTIONS or primary_emo in SPARSE_COUNTER_EMOTIONS
        light = sec_emo in LIGHT_COUNTERLINE_FLOOR_EMOTIONS or primary_emo in LIGHT_COUNTERLINE_FLOOR_EMOTIONS
        if sparse and not light:
            continue

        is_chorus = _is_chorus(role)
        if not is_chorus:
            if not light or verse_light_filled or role not in {"a", "verse"}:
                continue
            verse_light_filled = True
            bars = max(1, int(section_bars[sec]))
            sec_start = float(starts[sec])
            sec_end = sec_start + float(bars) * float(bpb)
            need = max(0, 1 - _counter_in_section(sec_start, sec_end))
            _append_counter_gestures(sec=sec, sec_start=sec_start, bars=bars, need=need, light=True)
            continue

        bars = max(1, int(section_bars[sec]))
        sec_start = float(starts[sec])
        sec_end = sec_start + float(bars) * float(bpb)
        counter_in_section = _counter_in_section(sec_start, sec_end)
        if light:
            section_target = max(1, min(2, max(1, int(bars) // 4)))
        else:
            section_target = max(int(min_gestures), min(6, max(3, int(bars) // 2)))
            if sec_emo in RICH_COUNTER_EMOTIONS or primary_emo in RICH_COUNTER_EMOTIONS:
                section_target = max(4, min(6, int(section_target) + 1))
        need = max(0, int(section_target) - int(counter_in_section))
        _append_counter_gestures(
            sec=sec,
            sec_start=sec_start,
            bars=bars,
            need=need,
            light=bool(light),
        )

    if added:
        out = sorted(list(out) + list(added), key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))
    return out, {
        "enabled": True,
        "added_counter_events": int(len(added)),
        "chorus_sections_filled": int(
            sum(
                1
                for sec in range(n)
                if str(section_roles[sec] or "").strip().lower() in {"b", "chorus", "hook", "tag"}
            )
        ),
        "light_verse_filled": bool(verse_light_filled),
    }


def reinforce_chorus_arp_floor(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_emotions: Sequence[str],
    beats_per_bar: float = 4.0,
    strength: float = 0.72,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Late full-song arp floor for chorus sections that lost too much motion."""

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "added_notes": 0}
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return out, {"enabled": False, "added_notes": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    chord_windows = _build_chord_windows(out)
    n = min(len(starts), len(section_bars), len(section_roles or []), len(section_emotions or []))
    added: List[Tuple] = []
    sections_repaired = 0

    def _is_chorus(role: str) -> bool:
        return str(role or "").strip().lower() in {"b", "chorus", "hook", "tag"}

    def _has_near_arp(start: float, eps: float = 0.06) -> bool:
        for ev in list(out) + list(added):
            try:
                if int(ev[0]) == 3 and abs(float(ev[3]) - float(start)) <= float(eps):
                    return True
            except Exception:
                continue
        return False

    def _arp_pitch(pc: int, anchor: int) -> int:
        cands = [12 * octv + int(pc) for octv in range(3, 7)]
        return int(min(cands, key=lambda p: abs(int(p) - int(anchor)))) if cands else int(anchor)

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
        emotion_lc = str(section_emotions[i] or "").strip().lower()
        restrained = emotion_lc in {
            "disappointment",
            "disapproval",
            "gratitude",
            "grief",
            "optimism",
            "pride",
            "realization",
            "relief",
            "remorse",
            "sadness",
        }
        floor = 6
        target_npb = (6.10 + 0.35 * float(s)) if restrained else (6.15 + 0.45 * float(s))

        sec_start = float(starts[i])
        sec_end = sec_start + float(bars) * float(bpb)
        counts = [0 for _ in range(bars)]
        pitches: List[int] = []
        for ev in out:
            try:
                if int(ev[0]) != 3:
                    continue
                st = float(ev[3])
            except Exception:
                continue
            if not (sec_start - 1e-6 <= st < sec_end - 1e-6):
                continue
            bi = int((st - sec_start) // float(bpb))
            if 0 <= bi < bars:
                counts[bi] += 1
                try:
                    pitches.append(int(ev[1]))
                except Exception:
                    pass
        if (sum(counts) / max(1, bars)) >= target_npb and min(counts or [floor]) >= floor:
            continue

        anchor = sorted(pitches)[len(pitches) // 2] if pitches else 60
        local_added = 0
        max_add_base = 2.25 if restrained else 1.65
        max_add = int(max(1, round(float(bars) * (max_add_base + 0.65 * float(s)))))
        max_add = int(max(max_add, sum(max(0, int(floor) - int(c)) for c in counts)))
        offsets = [0.0, 0.75, 1.5, 2.25, 3.0, 3.75]
        for bi in sorted(range(bars), key=lambda x: counts[x]):
            if local_added >= max_add:
                break
            for off in offsets:
                if local_added >= max_add or counts[bi] >= floor:
                    break
                st = sec_start + float(bi) * float(bpb) + min(float(off), float(bpb) - 0.25)
                if _has_near_arp(float(st)):
                    continue
                pcs = _active_chord_pcs_at(chord_windows, float(st), beats_per_bar=float(bpb))
                if not pcs:
                    continue
                pc = sorted(int(x) % 12 for x in pcs)[(counts[bi] + bi) % len(pcs)]
                pitch = _arp_pitch(int(pc), int(anchor))
                vel = 46 if restrained else 52
                added.append((3, int(pitch), int(vel), float(st), 0.25, [int(pitch)]))
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


def reduce_chorus_arp_lead_overlap(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_emotions: Sequence[str],
    beats_per_bar: float = 4.0,
    min_arp_per_bar: int = 6,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Thin nonessential chorus arp hits that mask lead-heavy soft emotions."""

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "removed_events": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    n = min(len(starts), len(section_bars), len(section_roles or []), len(section_emotions or []))
    if n <= 0:
        return out, {"enabled": False, "removed_events": 0}

    sensitive = {
        "admiration",
        "caring",
        "confusion",
        "disappointment",
        "embarrassment",
        "joy",
        "love",
        "nervousness",
        "neutral",
        "realization",
        "pride",
        "anger",
        "amusement",
    }
    chorus_roles = {"b", "chorus", "hook", "tag"}
    remove_ids: set[int] = set()
    considered = 0

    for sec in range(n):
        role = str(section_roles[sec] or "").strip().lower()
        emotion = str(section_emotions[sec] or "").strip().lower()
        if role not in chorus_roles or emotion not in sensitive:
            continue
        try:
            bars = max(1, int(section_bars[sec]))
        except Exception:
            bars = 1
        sec_start = float(starts[sec])
        sec_end = sec_start + float(bars) * float(bpb)
        arp_by_bar = [0 for _ in range(bars)]
        lead_starts: List[float] = []
        for ev in out:
            try:
                ch = int(ev[0])
                st = float(ev[3])
            except Exception:
                continue
            if not (sec_start - 1e-6 <= st < sec_end - 1e-6):
                continue
            bi = int((st - sec_start) // float(bpb))
            if not (0 <= bi < bars):
                continue
            if ch == 3:
                arp_by_bar[bi] += 1
            elif _lead_pitch(ev) is not None:
                lead_starts.append(float(st))
        if not lead_starts:
            continue

        for ev_i, ev in enumerate(out):
            try:
                if int(ev[0]) != 3:
                    continue
                st = float(ev[3])
            except Exception:
                continue
            if not (sec_start - 1e-6 <= st < sec_end - 1e-6):
                continue
            bi = int((st - sec_start) // float(bpb))
            if not (0 <= bi < bars):
                continue
            if arp_by_bar[bi] <= int(min_arp_per_bar):
                continue
            local = (float(st) - sec_start) % bpb
            if abs(local - 0.0) <= 0.06 or abs(local - 2.0) <= 0.06:
                continue
            if not any(abs(float(st) - float(ls)) <= 0.10 for ls in lead_starts):
                continue
            remove_ids.add(int(ev_i))
            arp_by_bar[bi] -= 1
            considered += 1

    if remove_ids:
        out = [ev for i, ev in enumerate(out) if int(i) not in remove_ids]
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))
    return out, {"enabled": True, "removed_events": int(len(remove_ids)), "candidates_removed": int(considered)}


def duck_arp_under_active_lead(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_emotions: Sequence[str],
    primary_emotion: str = "",
    beats_per_bar: float = 4.0,
    min_arp_per_bar: int = 4,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Shorten or remove arp hits that mask active topline phrases."""

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "removed_events": 0, "shortened_events": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    n = min(len(starts), len(section_bars), len(section_roles or []), len(section_emotions or []))
    if n <= 0:
        return out, {"enabled": False, "removed_events": 0, "shortened_events": 0}

    sensitive = {
        "admiration",
        "approval",
        "caring",
        "confusion",
        "curiosity",
        "desire",
        "disappointment",
        "disapproval",
        "embarrassment",
        "excitement",
        "fear",
        "gratitude",
        "grief",
        "joy",
        "love",
        "nervousness",
        "neutral",
        "optimism",
        "realization",
        "relief",
        "remorse",
        "sadness",
        "surprise",
        "pride",
        "anger",
        "amusement",
    }
    primary = str(primary_emotion or "").strip().lower()
    remove_ids: set[int] = set()
    replace: Dict[int, Tuple] = {}
    sections_ducked = 0

    def _overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
        return float(a0) < float(b1) - 1e-6 and float(a1) > float(b0) + 1e-6

    for sec in range(n):
        role = str(section_roles[sec] or "").strip().lower()
        emotion = str(section_emotions[sec] or "").strip().lower()
        if emotion not in sensitive and primary not in sensitive:
            continue
        bars = max(1, int(section_bars[sec]))
        sec_start = float(starts[sec])
        sec_end = sec_start + float(bars) * bpb
        lead_windows: List[Tuple[float, float]] = []
        arp_by_bar = [0 for _ in range(bars)]
        for ev in out:
            try:
                ch = int(ev[0])
                st = float(ev[3])
                dur = max(0.0, float(ev[4]))
            except Exception:
                continue
            if not (sec_start - 1e-6 <= st < sec_end - 1e-6):
                continue
            if ch == 3:
                bi = int((st - sec_start) // bpb)
                if 0 <= bi < bars:
                    arp_by_bar[bi] += 1
            elif _lead_pitch(ev) is not None:
                lead_windows.append((float(st) - 0.05, min(sec_end, float(st) + float(dur) + 0.08)))
        if not lead_windows:
            continue
        local_removed = 0
        local_shortened = 0
        for idx, ev in enumerate(out):
            if idx in remove_ids or idx in replace:
                continue
            try:
                if int(ev[0]) != 3:
                    continue
                st = float(ev[3])
                dur = max(0.0, float(ev[4]))
            except Exception:
                continue
            if not (sec_start - 1e-6 <= st < sec_end - 1e-6):
                continue
            bi = int((st - sec_start) // bpb)
            if not (0 <= bi < bars):
                continue
            if not any(_overlaps(float(st), float(st) + float(dur), a, b) for a, b in lead_windows):
                continue
            local = (float(st) - sec_start) % bpb
            protected = abs(local - 0.0) <= 0.06 or abs(local - 2.0) <= 0.06
            floor = int(min_arp_per_bar) + (1 if role in {"b", "chorus", "hook", "tag"} else 0)
            removal_floor = int(floor) + (2 if role not in {"b", "chorus", "hook", "tag"} else 1)
            if not protected and arp_by_bar[bi] > removal_floor and dur <= 0.30:
                remove_ids.add(int(idx))
                arp_by_bar[bi] -= 1
                local_removed += 1
                continue
            if dur > 0.30:
                new_dur = max(0.18, min(0.36, float(dur) * 0.70))
                if new_dur < dur - 1e-6:
                    replace[int(idx)] = (3, int(ev[1]), max(28, int(ev[2]) - 3), float(st), float(new_dur), list(ev[5]))
                    local_shortened += 1
        if local_removed or local_shortened:
            sections_ducked += 1

    if remove_ids or replace:
        out2: List[Tuple] = []
        for i, ev in enumerate(out):
            if int(i) in remove_ids:
                continue
            out2.append(replace.get(int(i), ev))
        out = sorted(out2, key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "sections_ducked": int(sections_ducked),
        "removed_events": int(len(remove_ids)),
        "shortened_events": int(len(replace)),
    }


def _time_overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return float(a0) < float(b1) - 1e-6 and float(a1) > float(b0) + 1e-6


def _role_at_time(
    st: float,
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    beats_per_bar: float,
) -> str:
    if not section_bars:
        return ""
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    n = min(len(starts), len(section_bars), len(section_roles or []))
    for i in range(n):
        sec_start = float(starts[i])
        sec_end = sec_start + float(int(section_bars[i])) * float(bpb)
        if sec_start - 1e-6 <= float(st) < sec_end - 1e-6:
            return str(section_roles[i] or "").strip().lower()
    return str(section_roles[n - 1] or "").strip().lower() if n > 0 else ""


def reduce_song_lead_arp_overlap(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    beats_per_bar: float = 4.0,
    lead_pad_beats: float = 0.06,
    min_arp_per_bar: int = 3,
    min_arp_per_bar_chorus: int = 5,
    velocity_duck: int = 14,
    remove_max_duration: float = 0.32,
    primary_emotion: str = "",
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Final song-wide pass: duck or trim arp hits that mask active lead lines."""

    primary = str(primary_emotion or "").strip().lower()
    if primary in _HIGH_LEAD_ARP_OVERLAP_PRIMARIES:
        lead_pad_beats = max(float(lead_pad_beats), 0.08)
        min_arp_per_bar = max(2, int(min_arp_per_bar) - 1)
        min_arp_per_bar_chorus = max(3, int(min_arp_per_bar_chorus) - 1)
        velocity_duck = int(min(22, int(velocity_duck) + 5))
        remove_max_duration = min(float(remove_max_duration), 0.28)
    if primary == "love":
        lead_pad_beats = max(float(lead_pad_beats), 0.10)
        velocity_duck = int(min(24, int(velocity_duck) + 2))
        remove_max_duration = min(float(remove_max_duration), 0.26)

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out:
        return out, {"enabled": False, "removed_events": 0, "ducked_events": 0, "shortened_events": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    chorus_roles = {"b", "chorus", "hook", "tag"}
    lead_windows: List[Tuple[float, float]] = []
    for ev in out:
        if _lead_pitch(ev) is None:
            continue
        try:
            st = float(ev[3])
            dur = max(0.0, float(ev[4]))
        except Exception:
            continue
        lead_windows.append((float(st) - float(lead_pad_beats), float(st) + float(dur) + float(lead_pad_beats)))
    if not lead_windows:
        return out, {"enabled": False, "removed_events": 0, "ducked_events": 0, "shortened_events": 0}

    arp_by_bar: Dict[int, int] = defaultdict(int)
    for ev in out:
        try:
            if int(ev[0]) != 3:
                continue
            bi = int(float(ev[3]) // bpb)
        except Exception:
            continue
        arp_by_bar[int(bi)] += 1

    remove_ids: set[int] = set()
    replace: Dict[int, Tuple] = {}
    ducked = 0
    shortened = 0

    for idx, ev in enumerate(out):
        try:
            if int(ev[0]) != 3:
                continue
            st = float(ev[3])
            dur = max(0.0, float(ev[4]))
            vel = int(ev[2])
        except Exception:
            continue
        end = float(st) + float(dur)
        if not any(_time_overlaps(float(st), float(end), a, b) for a, b in lead_windows):
            continue

        role = _role_at_time(
            float(st),
            section_bars=section_bars,
            section_roles=section_roles,
            beats_per_bar=float(bpb),
        )
        bi = int(float(st) // bpb)
        floor = int(min_arp_per_bar_chorus if role in chorus_roles else min_arp_per_bar)
        local = float(st) % bpb
        on_strong = abs(local - 0.0) <= 0.06 or abs(local - 2.0) <= 0.06

        if (
            not on_strong
            and int(arp_by_bar.get(int(bi), 0)) > int(floor)
            and float(dur) <= float(remove_max_duration)
        ):
            remove_ids.add(int(idx))
            arp_by_bar[int(bi)] = max(0, int(arp_by_bar.get(int(bi), 0)) - 1)
            continue

        if int(vel) > 24:
            new_vel = max(24, int(vel) - int(max(0, velocity_duck)))
            if new_vel < int(vel):
                replace[int(idx)] = (3, int(ev[1]), int(new_vel), float(st), float(dur), list(ev[5]))
                ducked += 1
                continue

        if float(dur) > 0.26:
            new_dur = max(0.18, min(0.28, float(dur) * 0.72))
            if new_dur < float(dur) - 1e-6:
                replace[int(idx)] = (3, int(ev[1]), int(vel), float(st), float(new_dur), list(ev[5]))
                shortened += 1

    if remove_ids or replace:
        out2: List[Tuple] = []
        for i, ev in enumerate(out):
            if int(i) in remove_ids:
                continue
            out2.append(replace.get(int(i), ev))
        out = sorted(out2, key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "removed_events": int(len(remove_ids)),
        "ducked_events": int(ducked),
        "shortened_events": int(shortened),
    }


def reinforce_nonchorus_ambient_arp_floor(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_roots: Sequence[int],
    section_emotions: Sequence[str],
    primary_emotion: str = "",
    beats_per_bar: float = 4.0,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Restore a light ambient arp bed in verses/preludes after lead ducking."""

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "added_notes": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    n = min(len(starts), len(section_bars), len(section_roles or []), len(section_roots or []), len(section_emotions or []))
    if n <= 0:
        return out, {"enabled": False, "added_notes": 0}

    airy = {
        "joy", "amusement", "excitement", "optimism", "surprise", "gratitude", "approval",
        "admiration", "love", "caring", "relief", "sadness", "grief", "remorse",
    }
    primary = str(primary_emotion or "").strip().lower()
    added: List[Tuple] = []
    sections_repaired = 0

    def _is_chorus(role: str) -> bool:
        return str(role or "").strip().lower() in {"b", "chorus", "hook", "tag"}

    for sec in range(n):
        role = str(section_roles[sec] or "").strip().lower()
        emotion = str(section_emotions[sec] or "").strip().lower()
        if _is_chorus(role) or (emotion not in airy and primary not in airy):
            continue
        bars = max(1, int(section_bars[sec]))
        sec_start = float(starts[sec])
        sec_end = sec_start + float(bars) * bpb
        arp_count = 0
        lead_starts: List[float] = []
        chord_pcs_by_bar: Dict[int, List[int]] = {}
        for ev in out:
            try:
                ch = int(ev[0])
                st = float(ev[3])
            except Exception:
                continue
            if not (sec_start - 1e-6 <= st < sec_end - 1e-6):
                continue
            bi = int((st - sec_start) // bpb)
            if ch == 3:
                arp_count += 1
            elif _lead_pitch(ev) is not None:
                lead_starts.append(float(st))
            elif ch == 1 and 0 <= bi < bars:
                notes = [int(n) for n in list(ev[5] or []) if isinstance(n, int)]
                if notes:
                    chord_pcs_by_bar.setdefault(int(bi), [int(n) % 12 for n in notes])
        target_per_bar = 1.25 if role in {"intro", "outro", "ending"} else 1.75
        if primary in {"sadness", "grief", "remorse"}:
            target_per_bar -= 0.35
        target_count = max(1, int(round(float(bars) * float(target_per_bar))))
        missing = max(0, int(target_count) - int(arp_count))
        if missing <= 0:
            continue

        try:
            scale = list(_emotion_scale_pcs_for_section(emotion_name=emotion or primary, root_note=int(section_roots[sec])) or [])
        except Exception:
            scale = []
        root = int(section_roots[sec])
        local_added = 0
        for bar in range(bars):
            if local_added >= missing:
                break
            pcs = list(chord_pcs_by_bar.get(int(bar), []) or [])
            if not pcs and scale:
                pcs = sorted(int(pc) for pc in scale)
            if not pcs:
                pcs = [int(root) % 12, (int(root) + 7) % 12]
            for off in (1.5, 3.0):
                if local_added >= missing:
                    break
                st = sec_start + float(bar) * bpb + float(off)
                if st >= sec_end - 1e-6:
                    continue
                if any(abs(float(st) - float(ls)) <= 0.18 for ls in lead_starts):
                    continue
                pc = int(pcs[(bar + local_added) % len(pcs)]) % 12
                pitch = int(root) - 12
                while pitch % 12 != pc:
                    pitch += 1
                while pitch < 52:
                    pitch += 12
                while pitch > 72:
                    pitch -= 12
                added.append((3, int(pitch), 36, float(st), 0.32, [int(pitch)]))
                local_added += 1
        if local_added:
            sections_repaired += 1

    if added:
        out = sorted(list(out) + list(added), key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "sections_repaired": int(sections_repaired),
        "added_notes": int(len(added)),
    }


def strip_arp_outside_chorus_for_suppressed_primary(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    primary_emotion: str = "",
    beats_per_bar: float = 4.0,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Remove ch3 arp notes outside chorus roles when the song primary opts out of arp beds."""

    from data.emotion_profiles import emotion_arp_bed_suppressed

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    primary = str(primary_emotion or "").strip().lower()
    if not out or not section_bars or not emotion_arp_bed_suppressed(primary):
        return out, {"enabled": False, "removed_events": 0}

    chorus_roles = {"b", "chorus", "hook", "tag"}
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    n = min(len(starts), len(section_bars), len(section_roles or []))
    if n <= 0:
        return out, {"enabled": False, "removed_events": 0}

    kept: List[Tuple] = []
    removed = 0
    for ev in out:
        try:
            if int(ev[0]) != 3:
                kept.append(ev)
                continue
            st = float(ev[3])
        except Exception:
            kept.append(ev)
            continue
        sec_i = 0
        for i in range(n - 1, -1, -1):
            if float(st) >= float(starts[i]) - 1e-6:
                sec_i = int(i)
                break
        role = str(section_roles[sec_i] or "").strip().lower() if sec_i < len(section_roles or []) else ""
        if role in chorus_roles:
            kept.append(ev)
        else:
            removed += 1

    kept.sort(key=lambda e: (float(e[3]), int(e[0]) if len(e) == 6 else 0))
    return kept, {
        "enabled": True,
        "removed_events": int(removed),
        "primary_emotion": str(primary),
    }


def soften_reflective_harmonic_motion(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_emotions: Sequence[str],
    primary_emotion: str = "",
    beats_per_bar: float = 4.0,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Remove excess non-structural passing chords for slower reflective harmony."""

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "removed_chords": 0}

    reflective = {"sadness", "grief", "remorse", "love", "caring", "relief"}
    primary = str(primary_emotion or "").strip().lower()
    if primary not in reflective:
        return out, {"enabled": True, "sections_softened": 0, "removed_chords": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    n = min(len(starts), len(section_bars), len(section_roles or []), len(section_emotions or []))
    remove_ids: set[int] = set()
    sections_softened = 0

    def _is_chorus(role: str) -> bool:
        return str(role or "").strip().lower() in {"b", "chorus", "hook", "tag"}

    for sec in range(n):
        role = str(section_roles[sec] or "").strip().lower()
        emotion = str(section_emotions[sec] or "").strip().lower()
        if _is_chorus(role) or (emotion not in reflective and primary not in reflective):
            continue
        bars = max(1, int(section_bars[sec]))
        sec_start = float(starts[sec])
        sec_end = sec_start + float(bars) * bpb
        chord_idxs: List[int] = []
        for idx, ev in enumerate(out):
            try:
                if int(ev[0]) != 1:
                    continue
                st = float(ev[3])
            except Exception:
                continue
            if sec_start - 1e-6 <= st < sec_end - 1e-6:
                chord_idxs.append(int(idx))
        target = max(1, int(round(float(bars) * (0.75 if role in {"intro", "outro", "ending"} else 0.90))))
        extra = max(0, len(chord_idxs) - target)
        if extra <= 0:
            continue

        def _remove_key(idx: int) -> Tuple[int, float]:
            st = float(out[idx][3])
            local = (st - sec_start) % bpb
            structural = abs(local - 0.0) <= 0.08 or abs(local - 2.0) <= 0.08
            return (1 if structural else 0, -float(st))

        local_removed = 0
        for idx in sorted(chord_idxs, key=_remove_key):
            if local_removed >= extra:
                break
            local = (float(out[idx][3]) - sec_start) % bpb
            if abs(local - 0.0) <= 0.08:
                continue
            remove_ids.add(int(idx))
            local_removed += 1
        if local_removed:
            sections_softened += 1

    if remove_ids:
        out = [ev for i, ev in enumerate(out) if int(i) not in remove_ids]
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "sections_softened": int(sections_softened),
        "removed_chords": int(len(remove_ids)),
    }


def separate_chorus_lead_from_arp_bed(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    beats_per_bar: float = 4.0,
    min_separation_semitones: int = 7,
    octave_lift_when_near: bool = True,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Keep chorus lead above arp bed while allowing occasional lock-in moments."""

    out = [tuple(ev) for ev in list(events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "lead_notes_shifted": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=float(bpb))
    n = min(len(starts), len(section_bars), len(section_roles or []))
    if n <= 0:
        return out, {"enabled": False, "lead_notes_shifted": 0}

    def _is_chorus(role: str) -> bool:
        return str(role or "").strip().lower() in {"b", "chorus", "hook", "tag"}

    def _section_index_for_start(st: float) -> Optional[int]:
        for i in range(n):
            sec_start = float(starts[i])
            sec_end = sec_start + float(int(section_bars[i])) * float(bpb)
            if sec_start - 1e-6 <= float(st) < sec_end - 1e-6:
                return int(i)
        return None

    # Build chorus-local pitch pools to estimate lead/bed register.
    arp_by_section: Dict[int, List[int]] = {}
    arp_indices_by_section: Dict[int, List[int]] = {}
    lead_by_section: Dict[int, List[int]] = {}
    for ev_i, ev in enumerate(out):
        try:
            ch = int(ev[0])
            st = float(ev[3])
            midi = int(ev[1])
        except Exception:
            continue
        sec = _section_index_for_start(float(st))
        if sec is None or not _is_chorus(str(section_roles[sec])):
            continue
        if ch == 3:
            arp_by_section.setdefault(int(sec), []).append(int(midi))
            arp_indices_by_section.setdefault(int(sec), []).append(int(ev_i))
        elif ch == 2:
            p = _lead_pitch(ev)
            if p is not None:
                lead_by_section.setdefault(int(sec), []).append(int(p))

    # Fast lookup for "arp is present near this lead onset".
    arp_starts = sorted(
        float(ev[3]) for ev in out
        if isinstance(ev, (tuple, list)) and len(ev) == 6 and int(ev[0]) == 3
    )

    def _near_arp(st: float, eps: float = 0.11) -> bool:
        t = float(st)
        for a in arp_starts:
            if a < t - float(eps):
                continue
            if a > t + float(eps):
                break
            return True
        return False

    replaced: Dict[int, Tuple] = {}
    shifted = 0
    arp_shifted = 0
    for i, ev in enumerate(out):
        pitch = _lead_pitch(ev)
        if pitch is None:
            continue
        try:
            st = float(ev[3])
            dur = float(ev[4])
            vel = int(ev[2])
        except Exception:
            continue
        sec = _section_index_for_start(float(st))
        if sec is None or not _is_chorus(str(section_roles[sec])):
            continue
        arp_pitches = list(arp_by_section.get(int(sec), []) or [])
        if not arp_pitches:
            continue
        arp_med = int(sorted(arp_pitches)[len(arp_pitches) // 2])
        local = float(st - float(starts[sec])) % float(bpb)
        on_strong = abs(local - 0.0) <= 0.09 or abs(local - 2.0) <= 0.09

        target_min = int(arp_med) + int(max(5, int(min_separation_semitones)))
        p2 = int(pitch)
        if bool(octave_lift_when_near) and _near_arp(float(st)) and not on_strong:
            if int(p2) < int(arp_med) + 12:
                p2 += 12
        while int(p2) < int(target_min) and int(p2) + 12 <= 84:
            p2 += 12
        p2 = _clamp_lead_pitch(int(p2))
        if int(p2) == int(pitch):
            continue
        replaced[int(i)] = (2, int(p2), int(vel), float(st), float(dur), [int(p2)])
        shifted += 1

    # If lead is already near its ceiling, move high arp-bed notes down instead
    # of pretending lead-only octave lifting can create the requested gap.
    min_sep = int(max(5, int(min_separation_semitones)))
    effective_leads_by_section: Dict[int, List[int]] = {}
    for ev_i, ev0 in enumerate(out):
        ev_eff = replaced.get(int(ev_i), ev0)
        if _lead_pitch(ev_eff) is None:
            continue
        try:
            st_eff = float(ev_eff[3])
        except Exception:
            continue
        sec_eff = _section_index_for_start(float(st_eff))
        if sec_eff is None or not _is_chorus(str(section_roles[sec_eff])):
            continue
        p_eff = _lead_pitch(ev_eff)
        if p_eff is not None:
            effective_leads_by_section.setdefault(int(sec_eff), []).append(int(p_eff))

    for sec, arp_indices in list(arp_indices_by_section.items()):
        leads = list(effective_leads_by_section.get(int(sec), []) or lead_by_section.get(int(sec), []) or [])
        arps = list(arp_by_section.get(int(sec), []) or [])
        if not leads or not arps:
            continue
        lead_med = int(sorted(leads)[len(leads) // 2])
        arp_med = int(sorted(arps)[len(arps) // 2])
        if int(lead_med) - int(arp_med) >= int(min_sep):
            continue
        ceiling = int(lead_med) - int(min_sep)
        for ev_i in sorted(arp_indices, key=lambda j: float(out[j][3])):
            ev = replaced.get(int(ev_i), out[ev_i])
            try:
                p = int(ev[1])
            except Exception:
                continue
            if int(p) <= int(ceiling):
                continue
            p2 = int(p)
            while int(p2) > int(ceiling) and int(p2) - 12 >= 57:
                p2 -= 12
            if int(p2) == int(p) or int(p2) > int(ceiling):
                continue
            replaced[int(ev_i)] = (3, int(p2), int(ev[2]), float(ev[3]), float(ev[4]), [int(p2)])
            arp_shifted += 1

    if replaced:
        out = [replaced.get(i, ev) for i, ev in enumerate(out)]
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {"enabled": True, "lead_notes_shifted": int(shifted), "arp_notes_shifted": int(arp_shifted)}


