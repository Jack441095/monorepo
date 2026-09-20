# composition/song_postprocess_pipeline.py
"""Ordered whole-song postprocess passes after section stitch."""

from __future__ import annotations
from audiogen_core.config import resolve_config

from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from composition.event_utils import (
    median_int as _median_int,
    pitch_from_event as _pitch_from_event,
)
from data.emotion_aliases import canonical_emotion_name

from composition.song_postprocess import (
    add_arrangement_continuity_anchors,
    add_melody_reprises,
    add_section_boundary_melodic_pickups,
    anchor_strongbeat_lead_to_chords,
    cap_song_lead_leaps,
    develop_song_theme_and_rewrite_hooks,
    reinforce_song_hook_identity,
    duck_arp_under_active_lead,
    guard_excessive_chorus_register_jumps,
    guard_reflective_chorus_register,
    lift_bright_chorus_registers,
    professionalize_song_form,
    reduce_chorus_arp_lead_overlap,
    reduce_song_lead_arp_overlap,
    reduce_repeated_song_lead_pitches,
    reinforce_nonchorus_ambient_arp_floor,
    reinforce_bright_chorus_payoffs,
    reinforce_chorus_arp_floor,
    reinforce_chorus_counterline_floor,
    reinforce_chorus_harmonic_motion,
    reinforce_chorus_melody_action,
    repair_song_phrase_end_chord_tones,
    separate_chorus_lead_from_arp_bed,
    shape_emotional_lead_contours,
    shape_phrase_level_emotional_contours,
    shape_reflective_chorus_breathing,
    shape_reflective_song_negative_space,
    soften_reflective_harmonic_motion,
    snap_lead_to_section_scales,
    snap_song_notes_to_section_scales,
    strip_arp_outside_chorus_for_suppressed_primary,
)

# Metadata keys recorded in pipeline order (for audits/docs).
POSTPROCESS_PASS_ORDER: Tuple[str, ...] = (
    "melody_reprise",
    "song_theme_development",
    "hook_identity_reinforce",
    "melodic_pickups",
    "professionalizer",
    "arrangement_glue",
    "bright_chorus_payoff",
    "bright_chorus_register_lift",
    "chorus_melody_action",
    "reflective_chorus_breathing",
    "chorus_arp_floor",
    "chorus_lead_arp_separation",
    "lead_scale_guard",
    "reflective_song_negative_space",
    "lead_phrase_emotional_contour",
    "lead_emotional_contour",
    "phrase_cadence_guard",
    "lead_harmonic_anchor",
    "lead_leap_guard",
    "lead_repeat_guard",
    "lead_scale_guard_final",
    "lead_harmonic_anchor_final",
    "lead_scale_guard_after_final_anchor",
    "chorus_lead_arp_separation_final",
    "chorus_arp_lead_overlap_guard",
    "lead_aware_arp_ducking",
    "nonchorus_ambient_arp_floor",
    "reflective_harmonic_motion_softener",
    "chorus_harmonic_motion",
    "chorus_counterline_floor",
    "chorus_register_jump_guard",
    "reflective_chorus_register_guard",
    "lead_scale_guard_post_reflective_register",
    "strip_arp_outside_chorus",
    "full_arrangement_scale_guard",
    "lead_scale_guard_post_full_arrangement",
    "final_chorus_strength_guard",
    "final_phrase_boundary_breath",
    "final_lead_singability_guard",
    "final_bass_motion_guard",
    "final_bar_velocity_smoother",
    "final_lead_arp_overlap_guard",
)





def _apply_final_lead_singability_guard(
    events: Sequence[Tuple],
    *,
    target_range_semitones: int = 24,
    max_leap_semitones: int = 14,
    low_pitch: int = 52,
    high_pitch: int = 84,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Final octave-displacement pass to keep the rendered lead singable."""
    rows = [tuple(ev) for ev in events or [] if isinstance(ev, (list, tuple)) and len(ev) == 6]
    if not rows:
        return [], {}
    lead_indices = [idx for idx, ev in enumerate(rows) if int(ev[0]) == 2 and _pitch_from_event(ev) is not None]
    lead_indices.sort(key=lambda idx: (float(rows[idx][3]), int(rows[idx][1])))
    if len(lead_indices) < 2:
        return list(rows), {}

    original_pitches = [_pitch_from_event(rows[idx]) for idx in lead_indices]
    pitches = [int(p) for p in original_pitches if p is not None]
    if not pitches:
        return list(rows), {}
    original_range = int(max(pitches) - min(pitches))
    original_max_leap = max((abs(int(b) - int(a)) for a, b in zip(pitches, pitches[1:])), default=0)

    target_span = max(12, min(30, int(target_range_semitones or 24)))
    max_leap = max(7, min(18, int(max_leap_semitones or 14)))
    lo_pitch = max(36, min(72, int(low_pitch)))
    hi_pitch = max(lo_pitch + 12, min(96, int(high_pitch)))
    center = max(lo_pitch + target_span // 2, min(hi_pitch - target_span // 2, _median_int(pitches)))
    win_lo = int(center - target_span // 2)
    win_hi = int(center + target_span // 2)

    replaced: Dict[int, Tuple] = {}
    adjusted_pitches: List[int] = []
    changed = 0
    for idx in lead_indices:
        ev = rows[idx]
        pitch = _pitch_from_event(ev)
        if pitch is None:
            continue
        candidates = sorted({max(lo_pitch, min(hi_pitch, int(pitch) + 12 * shift)) for shift in range(-4, 5)})
        prev = adjusted_pitches[-1] if adjusted_pitches else None

        def _cost(cand: int) -> Tuple[float, int]:
            window_penalty = max(0, win_lo - cand, cand - win_hi)
            leap_penalty = 0 if prev is None else max(0, abs(int(cand) - int(prev)) - max_leap)
            distance = abs(int(cand) - int(pitch))
            return (
                float(window_penalty) * 25.0
                + float(leap_penalty) * 18.0
                + float(distance) * 0.45,
                int(distance),
            )

        best = int(min(candidates, key=_cost))
        adjusted_pitches.append(int(best))
        if int(best) == int(pitch):
            continue
        replaced[int(idx)] = (2, int(best), int(ev[2]), float(ev[3]), float(ev[4]), [int(best)])
        changed += 1

    if not replaced:
        return list(rows), {}

    out = [replaced.get(i, ev) for i, ev in enumerate(rows)]
    out.sort(key=lambda ev: (float(ev[3]), int(ev[0]), int(ev[1])))
    final_pitches = [_pitch_from_event(ev) for ev in out if int(ev[0]) == 2 and _pitch_from_event(ev) is not None]
    final_values = [int(p) for p in final_pitches if p is not None]
    final_range = int(max(final_values) - min(final_values)) if final_values else 0
    final_max_leap = max((abs(int(b) - int(a)) for a, b in zip(final_values, final_values[1:])), default=0)
    return out, {
        "notes_shifted": int(changed),
        "target_range_semitones": int(target_span),
        "max_leap_semitones": int(max_leap),
        "original_range": int(original_range),
        "final_range": int(final_range),
        "original_max_leap": int(original_max_leap),
        "final_max_leap": int(final_max_leap),
    }


def _apply_final_phrase_boundary_breath(
    events: Sequence[Tuple],
    *,
    section_bars: Sequence[int],
    beats_per_bar: float = 4.0,
    phrase_bars: int = 4,
    breath_beats: float = 0.18,
    min_note_beats: float = 0.20,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Leave a final whole-song breath before phrase and section boundaries."""
    rows = [tuple(ev) for ev in events or [] if isinstance(ev, (list, tuple)) and len(ev) == 6]
    if not rows:
        return [], {}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    total_bars = max(1, int(sum(max(0, int(b)) for b in section_bars or [])))
    phrase_bars = max(1, int(phrase_bars))
    breath = max(0.03, min(0.50, float(breath_beats)))
    min_note = max(0.05, min(1.0, float(min_note_beats)))

    boundary_bars = set(range(phrase_bars, total_bars, phrase_bars))
    off = 0
    for bars in section_bars or []:
        off += max(0, int(bars))
        if 0 < off < total_bars:
            boundary_bars.add(int(off))
    if not boundary_bars:
        return list(rows), {}

    boundaries = [float(bar) * bpb for bar in sorted(boundary_bars)]
    out: List[Tuple] = []
    trimmed = 0
    shifted = 0
    for ev in rows:
        try:
            ch, midi, vel, start, dur, notes = ev
            if int(ch) != 2:
                out.append(ev)
                continue
            st = float(start)
            duration = float(dur)
            end = st + duration
            new_start = st
            new_dur = duration
            for boundary in boundaries:
                trim_point = float(boundary) - float(breath)
                if not (st < boundary and end > trim_point):
                    continue
                if st >= trim_point:
                    # A pickup inside the requested breath window defeats the breath entirely.
                    # Move it onto the new phrase instead of leaving a tiny pre-boundary blip.
                    bar_end = boundary + bpb
                    cand_start = min(bar_end - 0.05, boundary + 0.02)
                    new_start = max(boundary, cand_start)
                    new_dur = min(duration, max(0.05, bar_end - new_start - 0.01))
                    shifted += 1
                    break
                cand = trim_point - st
                if cand < min_note:
                    # Very short notes just before the breath point cannot be trimmed musically.
                    # Treat them as phrase pickups and move them to the new phrase.
                    bar_end = boundary + bpb
                    cand_start = min(bar_end - 0.05, boundary + 0.02)
                    new_start = max(boundary, cand_start)
                    new_dur = min(duration, max(0.05, bar_end - new_start - 0.01))
                    shifted += 1
                    break
                if cand < new_dur:
                    new_dur = cand
                    trimmed += 1
            if abs(new_start - st) <= 1e-6 and abs(new_dur - duration) <= 1e-6:
                out.append(ev)
            else:
                out.append((int(ch), int(midi), int(vel), float(new_start), float(max(0.05, new_dur)), list(notes)))
        except Exception:
            out.append(ev)

    out.sort(key=lambda ev: (float(ev[3]), int(ev[0]), int(ev[1])))
    meta = {
        "trimmed_events": int(trimmed),
        "shifted_pickups": int(shifted),
        "boundary_count": int(len(boundaries)),
        "breath_beats": float(breath),
    }
    return out, meta if trimmed or shifted else {}


def _apply_final_chorus_strength_guard(
    events: Sequence[Tuple],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_roots: Sequence[int],
    beats_per_bar: float = 4.0,
    min_chorus_to_verse_ratio: float = 0.90,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Add restrained lead accents if chorus lead density falls below verse density."""
    rows = [tuple(ev) for ev in events or [] if isinstance(ev, (list, tuple)) and len(ev) == 6]
    if not rows or not section_bars:
        return list(rows), {}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    roles = [str(role or "").strip().lower() for role in section_roles or []]
    roots = [int(root) for root in section_roots or []]
    starts: List[float] = []
    off = 0.0
    for bars in section_bars:
        starts.append(float(off))
        off += float(max(0, int(bars))) * bpb
    n = min(len(starts), len(section_bars), len(roles))
    if n <= 0:
        return list(rows), {}

    lead_counts = [0 for _ in range(n)]
    lead_velocities: List[int] = []
    lead_pitches_by_section: List[List[int]] = [[] for _ in range(n)]
    for ev in rows:
        try:
            if int(ev[0]) != 2:
                continue
            st = float(ev[3])
            pitch = _pitch_from_event(ev)
            for sec in range(n):
                sec_start = float(starts[sec])
                sec_end = sec_start + float(int(section_bars[sec])) * bpb
                if sec_start - 1e-6 <= st < sec_end - 1e-6:
                    lead_counts[sec] += 1
                    lead_velocities.append(int(ev[2]))
                    if pitch is not None:
                        lead_pitches_by_section[sec].append(int(pitch))
                    break
        except Exception:
            continue

    verse_rates = [
        float(lead_counts[sec] / max(1, int(section_bars[sec])))
        for sec in range(n)
        if roles[sec] in {"a", "verse", "a_prime"}
    ]
    chorus_sections = [sec for sec in range(n) if roles[sec] in {"b", "chorus", "hook", "tag"}]
    chorus_rates = [float(lead_counts[sec] / max(1, int(section_bars[sec]))) for sec in chorus_sections]
    if not verse_rates or not chorus_rates:
        return list(rows), {}
    avg_verse = float(sum(verse_rates) / max(1, len(verse_rates)))
    avg_chorus = float(sum(chorus_rates) / max(1, len(chorus_rates)))
    target_chorus = float(avg_verse) * max(0.75, min(1.15, float(min_chorus_to_verse_ratio)))
    if avg_chorus >= target_chorus:
        return list(rows), {}

    needed_total = int(round((target_chorus - avg_chorus) * sum(max(1, int(section_bars[s])) for s in chorus_sections)))
    needed_total = max(1, min(16, int(needed_total)))
    base_velocity = int(round(sum(lead_velocities) / max(1, len(lead_velocities)))) if lead_velocities else 78
    additions: List[Tuple] = []
    sec_cursor = 0
    for _ in range(needed_total):
        sec = chorus_sections[sec_cursor % len(chorus_sections)]
        sec_cursor += 1
        bars = max(1, int(section_bars[sec]))
        bar = min(bars - 1, max(0, (lead_counts[sec] + sec_cursor) % bars))
        sec_start = float(starts[sec])
        start = sec_start + float(bar) * bpb + min(2.5, max(0.5, bpb * 0.625))
        sec_end = sec_start + float(bars) * bpb
        if start >= sec_end - 0.25:
            start = sec_end - 0.50
        # Avoid double-hitting an already active lead onset.
        crowded = False
        for ev in rows:
            try:
                if int(ev[0]) == 2 and abs(float(ev[3]) - float(start)) < 0.18:
                    crowded = True
                    break
            except Exception:
                continue
        if crowded:
            start = max(sec_start + 0.25, min(sec_end - 0.50, start + 0.37))
        root = int(roots[sec]) if sec < len(roots) else 60
        existing = lead_pitches_by_section[sec]
        pitch = _median_int(existing) if existing else int(root + 19)
        pitch = max(55, min(84, int(pitch)))
        velocity = int(max(1, min(127, round(float(base_velocity) * 1.04))))
        additions.append((2, int(pitch), int(velocity), float(start), 0.36, [int(pitch)]))
        lead_counts[sec] += 1

    if not additions:
        return list(rows), {}
    out = list(rows) + additions
    out.sort(key=lambda ev: (float(ev[3]), int(ev[0]), int(ev[1])))
    return out, {
        "notes_added": int(len(additions)),
        "avg_verse_lead_notes_per_bar": float(avg_verse),
        "avg_chorus_lead_notes_per_bar_before": float(avg_chorus),
        "target_chorus_lead_notes_per_bar": float(target_chorus),
    }


def _apply_final_bass_motion_guard(
    events: Sequence[Tuple],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    beats_per_bar: float = 4.0,
    low_pitch: int = 36,
    high_pitch: int = 60,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Add a restrained passing bass pitch in non-intro sections that are root-static."""
    rows = [tuple(ev) for ev in events or [] if isinstance(ev, (list, tuple)) and len(ev) == 6]
    if not rows or not section_bars:
        return list(rows), {}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    roles = [str(role or "").strip().lower() for role in section_roles or []]
    starts: List[float] = []
    off = 0.0
    for bars in section_bars:
        starts.append(float(off))
        off += float(max(0, int(bars))) * bpb

    replacements: Dict[int, Tuple] = {}
    sections_repaired = 0
    notes_shifted = 0
    lo = max(24, min(60, int(low_pitch)))
    hi = max(lo + 12, min(72, int(high_pitch)))
    for sec, sec_start in enumerate(starts):
        if sec >= len(section_bars):
            continue
        role = roles[sec] if sec < len(roles) else ""
        if role in {"intro", "outro"}:
            continue
        bars = max(1, int(section_bars[sec]))
        sec_end = float(sec_start) + float(bars) * bpb
        indices: List[int] = []
        pitches: List[int] = []
        for idx, ev in enumerate(rows):
            try:
                if int(ev[0]) != 0:
                    continue
                st = float(ev[3])
                if not (float(sec_start) - 1e-6 <= st < float(sec_end) - 1e-6):
                    continue
                pitch = _pitch_from_event(ev)
                if pitch is None:
                    continue
                indices.append(int(idx))
                pitches.append(int(pitch))
            except Exception:
                continue
        if len(indices) < 2 or len(set(pitches)) > 1:
            continue
        base = int(pitches[0])
        candidates = [base + 2, base - 2, base + 5, base - 5, base + 7, base - 7]
        target = None
        for cand in candidates:
            if lo <= int(cand) <= hi and int(cand) != int(base):
                target = int(cand)
                break
        if target is None:
            continue
        # Prefer a late-middle note so the section keeps its root identity but does not sit still.
        chosen = indices[min(len(indices) - 1, max(1, int(round(len(indices) * 0.66))))]
        ev = rows[chosen]
        replacements[int(chosen)] = (0, int(target), int(ev[2]), float(ev[3]), float(ev[4]), [int(target)])
        sections_repaired += 1
        notes_shifted += 1

    if not replacements:
        return list(rows), {}
    out = [replacements.get(i, ev) for i, ev in enumerate(rows)]
    out.sort(key=lambda ev: (float(ev[3]), int(ev[0]), int(ev[1])))
    return out, {
        "sections_repaired": int(sections_repaired),
        "notes_shifted": int(notes_shifted),
    }


def _apply_final_bar_velocity_smoother(
    events: Sequence[Tuple],
    *,
    beats_per_bar: float = 4.0,
    ratio: float = 1.35,
    velocity_floor: int = 30,
    channels: Sequence[int] = (1, 2, 3, 5),
    max_gap_bars: int = 1,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Smooth whole-song bar mean velocity jumps for the rendered musical layers."""
    rows = [tuple(ev) for ev in events or [] if isinstance(ev, (list, tuple)) and len(ev) == 6]
    if not rows:
        return [], {}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    ratio = max(1.05, min(1.75, float(ratio)))
    floor = max(1, min(96, int(velocity_floor)))
    channel_set = {int(ch) for ch in channels}
    by_ch_bar: Dict[int, Dict[int, List[int]]] = defaultdict(lambda: defaultdict(list))
    for ev in rows:
        try:
            ch = int(ev[0])
            if ch not in channel_set:
                continue
            start = float(ev[3])
            if start < 0.0:
                continue
            bar = int(start // bpb)
            by_ch_bar[ch][bar].append(int(ev[2]))
        except Exception:
            continue

    scales: Dict[Tuple[int, int], float] = {}
    adjusted_bars = 0
    for ch, bar_map in by_ch_bar.items():
        prev_target: Optional[float] = None
        prev_bar: Optional[int] = None
        for bar in sorted(bar_map):
            vals = bar_map.get(bar) or []
            if not vals:
                continue
            raw = float(sum(vals) / max(1, len(vals)))
            target = max(float(floor), raw)
            if prev_target is not None and prev_bar is not None and int(bar) - int(prev_bar) <= int(max(1, max_gap_bars)):
                hi = float(prev_target) * float(ratio)
                lo = float(prev_target) / float(ratio)
                target = max(lo, min(hi, target))
            prev_target = float(target)
            prev_bar = int(bar)
            if raw > 1e-6 and abs(target - raw) > 0.5:
                scales[(int(ch), int(bar))] = float(target / raw)
                adjusted_bars += 1

    if not scales:
        return list(rows), {}

    out: List[Tuple] = []
    adjusted_events = 0
    for ev in rows:
        try:
            ch, midi, vel, start, dur, notes = ev
            key = (int(ch), int(float(start) // bpb))
            scale = float(scales.get(key, 1.0))
            if abs(scale - 1.0) <= 1e-6:
                out.append(ev)
                continue
            new_vel = int(max(1, min(127, round(float(vel) * scale))))
            if new_vel != int(vel):
                adjusted_events += 1
            out.append((int(ch), int(midi), int(new_vel), float(start), float(dur), list(notes)))
        except Exception:
            out.append(ev)
    out.sort(key=lambda ev: (float(ev[3]), int(ev[0]), int(ev[1])))
    return out, {
        "adjusted_bars": int(adjusted_bars),
        "adjusted_events": int(adjusted_events),
        "ratio": float(ratio),
        "velocity_floor": int(floor),
        "max_gap_bars": int(max(1, max_gap_bars)),
    }


def resolve_primary_emotion_for_postprocess(
    sections: Sequence[Any],
    roles_for_post: Sequence[str],
) -> str:
    preferred_roles = {"a", "verse", "a_prime"}
    for i, role in enumerate(roles_for_post):
        if str(role).strip().lower() in preferred_roles and i < len(sections):
            return canonical_emotion_name(str(sections[i].emotion_name))
    secondary_roles = {"b", "chorus", "hook", "tag", "pre_chorus"}
    for i, role in enumerate(roles_for_post):
        if str(role).strip().lower() in secondary_roles and i < len(sections):
            return canonical_emotion_name(str(sections[i].emotion_name))
    return canonical_emotion_name(str(sections[0].emotion_name)) if sections else ""


def _get_config_val(keys: str | List[str], default: Any) -> Any:
    if isinstance(keys, str):
        keys = [keys]
    for key in keys:
        val = resolve_config("composition", key, None)
        if val is not None:
            return val or default
    return default


def _resolve_param(val: Any, context: Dict[str, Any]) -> Any:
    if isinstance(val, str):
        if val in context:
            return context[val]
    if isinstance(val, tuple) and len(val) == 3:
        keys, default, type_conv = val
        raw = _get_config_val(keys, default)
        if type_conv is not None:
            try:
                return type_conv(raw)
            except Exception:
                return default
        return raw
    return val


POSTPROCESS_REGISTRY: Dict[str, Dict[str, Any]] = {
    "melody_reprise": {
        "func": add_melody_reprises,
        "enabled_key": "whole_song_melody_reprise_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "beats_per_bar": 4.0,
            "strength": ("whole_song_melody_reprise_strength", 0.68, float),
        }
    },
    "song_theme_development": {
        "func": develop_song_theme_and_rewrite_hooks,
        "enabled_key": "whole_song_theme_development_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_emotion",
            "beats_per_bar": 4.0,
            "strength": ("whole_song_theme_development_strength", 0.82, float),
        }
    },
    "hook_identity_reinforce": {
        "func": reinforce_song_hook_identity,
        "enabled_key": "whole_song_hook_identity_reinforce_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_emotion",
            "beats_per_bar": "bpb",
            "strength": ("whole_song_hook_identity_strength", 0.85, float),
        }
    },
    "melodic_pickups": {
        "func": add_section_boundary_melodic_pickups,
        "enabled_key": "whole_song_melodic_pickups_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "beats_per_bar": 4.0,
            "strength": ("whole_song_melodic_pickups_strength", 0.72, float),
        }
    },
    "professionalizer": {
        "func": professionalize_song_form,
        "enabled_key": "whole_song_professionalizer_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "primary_emotion": "primary_emotion",
            "beats_per_bar": 4.0,
            "strength": ("whole_song_professionalizer_strength", 0.82, float),
        }
    },
    "arrangement_glue": {
        "func": add_arrangement_continuity_anchors,
        "enabled_key": "whole_song_arrangement_glue_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "beats_per_bar": 4.0,
            "strength": ("whole_song_arrangement_glue_strength", 0.76, float),
        }
    },
    "bright_chorus_payoff": {
        "func": reinforce_bright_chorus_payoffs,
        "enabled_key": "whole_song_bright_chorus_payoff_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_emotions": "section_emotions",
            "beats_per_bar": 4.0,
            "strength": ("whole_song_bright_chorus_payoff_strength", 0.72, float),
        }
    },
    "bright_chorus_register_lift": {
        "func": lift_bright_chorus_registers,
        "enabled_key": "whole_song_bright_chorus_register_lift_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_emotions": "section_emotions",
            "beats_per_bar": 4.0,
            "min_lift_semitones": ("whole_song_bright_chorus_register_lift_min_semitones", 2, int),
        }
    },
    "chorus_melody_action": {
        "func": reinforce_chorus_melody_action,
        "enabled_key": "whole_song_chorus_melody_action_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "beats_per_bar": 4.0,
            "strength": ("whole_song_chorus_melody_action_strength", 0.78, float),
        }
    },
    "reflective_chorus_breathing": {
        "func": shape_reflective_chorus_breathing,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_emotion",
            "beats_per_bar": 4.0,
        }
    },
    "chorus_arp_floor": {
        "func": reinforce_chorus_arp_floor,
        "enabled_key": "whole_song_chorus_arp_floor_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_emotions": "section_emotions",
            "beats_per_bar": 4.0,
            "strength": ("whole_song_chorus_arp_floor_strength", 0.72, float),
        }
    },
    "chorus_lead_arp_separation": {
        "func": separate_chorus_lead_from_arp_bed,
        "enabled_key": "whole_song_chorus_lead_arp_separation_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "beats_per_bar": 4.0,
            "min_separation_semitones": ("whole_song_chorus_lead_arp_min_separation_semitones", 7, int),
            "octave_lift_when_near": False,
        }
    },
    "lead_scale_guard": {
        "func": snap_lead_to_section_scales,
        "params": {
            "section_bars": "section_bars",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_from_composer",
            "beats_per_bar": 4.0,
        }
    },
    "reflective_song_negative_space": {
        "func": shape_reflective_song_negative_space,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_emotion",
            "beats_per_bar": 4.0,
        }
    },
    "lead_phrase_emotional_contour": {
        "func": shape_phrase_level_emotional_contours,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_emotion",
            "beats_per_bar": 4.0,
        }
    },
    "lead_emotional_contour": {
        "func": shape_emotional_lead_contours,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_emotion",
            "beats_per_bar": 4.0,
        }
    },
    "phrase_cadence_guard": {
        "func": repair_song_phrase_end_chord_tones,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "section_phrase_spans": "section_phrase_spans",
            "beats_per_bar": 4.0,
            "primary_emotion": "primary_emotion",
        }
    },
    "lead_harmonic_anchor": {
        "func": anchor_strongbeat_lead_to_chords,
        "params": {
            "section_bars": "section_bars",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_emotion",
            "beats_per_bar": 4.0,
            "max_move_semitones": 3,
            "anchor_long_notes": True,
            "anchor_phrase_starts": True,
        }
    },
    "lead_leap_guard": {
        "func": cap_song_lead_leaps,
        "params": {
            "max_interval": 12,
        }
    },
    "lead_repeat_guard": {
        "func": reduce_repeated_song_lead_pitches,
        "params": {
            "section_bars": "section_bars",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "section_phrase_spans": "section_phrase_spans",
            "beats_per_bar": 4.0,
            "max_same_run": 1,
        }
    },
    "lead_scale_guard_final": {
        "func": snap_lead_to_section_scales,
        "params": {
            "section_bars": "section_bars",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_from_composer",
            "beats_per_bar": 4.0,
        }
    },
    "lead_harmonic_anchor_final": {
        "func": anchor_strongbeat_lead_to_chords,
        "params": {
            "section_bars": "section_bars",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_from_composer",
            "beats_per_bar": 4.0,
            "max_move_semitones": 4,
            "anchor_long_notes": True,
            "anchor_phrase_starts": True,
        }
    },
    "lead_scale_guard_after_final_anchor": {
        "func": snap_lead_to_section_scales,
        "params": {
            "section_bars": "section_bars",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_from_composer",
            "beats_per_bar": 4.0,
        }
    },
    "chorus_lead_arp_separation_final": {
        "func": separate_chorus_lead_from_arp_bed,
        "enabled_key": "whole_song_chorus_lead_arp_separation_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "beats_per_bar": 4.0,
            "min_separation_semitones": lambda ctx: int(max(6, int(_get_config_val("whole_song_chorus_lead_arp_min_separation_semitones", 7)))),
            "octave_lift_when_near": False,
        }
    },
    "chorus_arp_lead_overlap_guard": {
        "func": reduce_chorus_arp_lead_overlap,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_emotions": "section_emotions",
            "beats_per_bar": 4.0,
            "min_arp_per_bar": 4,
        }
    },
    "lead_aware_arp_ducking": {
        "func": duck_arp_under_active_lead,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_emotion",
            "beats_per_bar": 4.0,
            "min_arp_per_bar": 4,
        }
    },
    "nonchorus_ambient_arp_floor": {
        "func": reinforce_nonchorus_ambient_arp_floor,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_emotion",
            "beats_per_bar": 4.0,
        }
    },
    "reflective_harmonic_motion_softener": {
        "func": soften_reflective_harmonic_motion,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_emotion",
            "beats_per_bar": 4.0,
        }
    },
    "chorus_harmonic_motion": {
        "func": reinforce_chorus_harmonic_motion,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "beats_per_bar": 4.0,
        }
    },
    "chorus_counterline_floor": {
        "func": reinforce_chorus_counterline_floor,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_from_composer_or_empty",
            "beats_per_bar": 4.0,
            "min_gestures": 3,
        }
    },
    "chorus_register_jump_guard": {
        "func": guard_excessive_chorus_register_jumps,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "beats_per_bar": 4.0,
        }
    },
    "reflective_chorus_register_guard": {
        "func": guard_reflective_chorus_register,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_emotions": "section_emotions",
            "beats_per_bar": 4.0,
        }
    },
    "lead_scale_guard_post_reflective_register": {
        "func": snap_lead_to_section_scales,
        "params": {
            "section_bars": "section_bars",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_from_composer",
            "beats_per_bar": 4.0,
        }
    },
    "strip_arp_outside_chorus": {
        "func": strip_arp_outside_chorus_for_suppressed_primary,
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "primary_emotion": "primary_emotion",
            "beats_per_bar": 4.0,
        }
    },
    "full_arrangement_scale_guard": {
        "func": snap_song_notes_to_section_scales,
        "params": {
            "section_bars": "section_bars",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_emotion",
            "beats_per_bar": 4.0,
        }
    },
    "lead_scale_guard_post_full_arrangement": {
        "func": snap_lead_to_section_scales,
        "params": {
            "section_bars": "section_bars",
            "section_roots": "section_roots",
            "section_emotions": "section_emotions",
            "primary_emotion": "primary_from_composer",
            "beats_per_bar": 4.0,
        }
    },
    "final_chorus_strength_guard": {
        "func": _apply_final_chorus_strength_guard,
        "enabled_key": "whole_song_chorus_strength_guard_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "section_roots": "section_roots",
            "beats_per_bar": 4.0,
            "min_chorus_to_verse_ratio": ("whole_song_chorus_strength_min_ratio", 0.90, float),
        }
    },
    "final_phrase_boundary_breath": {
        "func": _apply_final_phrase_boundary_breath,
        "enabled_key": "whole_song_phrase_breath_enabled",
        "params": {
            "section_bars": "section_bars",
            "beats_per_bar": 4.0,
            "breath_beats": (["whole_song_phrase_breath_beats", "melody_phrase_breath_beats"], 0.18, float),
            "min_note_beats": (["whole_song_phrase_breath_min_note_beats", "melody_phrase_breath_min_note_beats"], 0.20, float),
        }
    },
    "final_lead_singability_guard": {
        "func": _apply_final_lead_singability_guard,
        "enabled_key": "whole_song_lead_singability_guard_enabled",
        "params": {
            "target_range_semitones": ("whole_song_lead_target_range_semitones", 24, int),
            "max_leap_semitones": ("whole_song_lead_max_leap_semitones", 14, int),
        }
    },
    "final_bass_motion_guard": {
        "func": _apply_final_bass_motion_guard,
        "enabled_key": "whole_song_bass_motion_guard_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "beats_per_bar": 4.0,
        }
    },
    "final_bar_velocity_smoother": {
        "func": _apply_final_bar_velocity_smoother,
        "enabled_key": "whole_song_bar_velocity_smoothing_enabled",
        "params": {
            "beats_per_bar": 4.0,
            "ratio": ("whole_song_bar_velocity_smoothing_ratio", 1.35, float),
            "velocity_floor": ("whole_song_bar_velocity_smoothing_floor", 30, int),
        }
    },
    "final_lead_arp_overlap_guard": {
        "func": reduce_song_lead_arp_overlap,
        "enabled_key": "whole_song_lead_arp_overlap_guard_enabled",
        "params": {
            "section_bars": "section_bars",
            "section_roles": "section_roles",
            "beats_per_bar": 4.0,
            "min_arp_per_bar": ("whole_song_lead_arp_overlap_min_arp_per_bar", 3, int),
            "min_arp_per_bar_chorus": ("whole_song_lead_arp_overlap_min_arp_per_bar_chorus", 5, int),
            "velocity_duck": ("whole_song_lead_arp_overlap_velocity_duck", 14, int),
            "primary_emotion": "primary_emotion",
        }
    },
}


def run_whole_song_postprocess(
    events: Sequence[Tuple],
    *,
    sections: Sequence[Any],
    roles_for_post: Sequence[str],
    section_bars_for_post: Sequence[int],
    section_phrase_spans: Optional[Sequence[Dict[str, Any]]] = None,
    composer: Any = None,
    beats_per_bar: float = 4.0,
) -> Tuple[List[Tuple], Dict[str, Any], str]:
    """Apply stitched-song polish passes; returns (events, meta, primary_emotion)."""

    events = list(events)
    song_postprocess: Dict[str, Any] = {}
    primary_emotion_for_post = resolve_primary_emotion_for_postprocess(sections, roles_for_post)
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0

    def _primary_from_composer() -> str:
        if composer is None:
            return str(primary_emotion_for_post)
        return str(getattr(composer, "_song_primary_emotion_name", "") or primary_emotion_for_post)

    context = {
        "section_bars": section_bars_for_post,
        "section_roles": roles_for_post,
        "section_roots": [int(s.root_note) for s in sections],
        "section_emotions": [str(s.emotion_name) for s in sections],
        "primary_emotion": primary_emotion_for_post,
        "primary_from_composer": _primary_from_composer(),
        "primary_from_composer_or_empty": _primary_from_composer() or "",
        "section_phrase_spans": list(section_phrase_spans or []) if section_phrase_spans is not None else [],
        "bpb": bpb,
    }

    for pass_name in POSTPROCESS_PASS_ORDER:
        pass_meta = POSTPROCESS_REGISTRY.get(pass_name)
        if not pass_meta:
            continue

        enabled_key = pass_meta.get("enabled_key")
        enabled = True
        if enabled_key:
            enabled = bool(_get_config_val(enabled_key, True))

        if not enabled:
            continue

        resolved_kwargs = {}
        for param_name, param_val in pass_meta.get("params", {}).items():
            if callable(param_val) and not isinstance(param_val, type):
                resolved_kwargs[param_name] = param_val(context)
            else:
                resolved_kwargs[param_name] = _resolve_param(param_val, context)

        func = pass_meta["func"]
        try:
            events, pass_meta_dict = func(events, **resolved_kwargs)
            if pass_meta_dict:
                song_postprocess[pass_name] = dict(pass_meta_dict)
                if pass_name == "melodic_pickups":
                    song_postprocess.update(dict(pass_meta_dict))
        except Exception:
            pass

    return events, song_postprocess, str(primary_emotion_for_post)
