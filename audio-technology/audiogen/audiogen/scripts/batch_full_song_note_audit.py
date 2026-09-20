#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import secrets
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from composition.evaluation import evaluate_song
from composition.song_generator import SongGenerator, SongSectionSpec
from data.emotion_aliases import canonical_emotion_name
from data.emotion_scales import melody_scale_intervals_for_emotion
from data.music_data import EMOTIONS, EMOTION_BY_NAME

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
CHANNEL_NAMES = {0: "bass", 1: "chords", 2: "melody", 3: "arp", 4: "drone", 5: "counter_melody"}


@dataclass(frozen=True)
class SectionWindow:
    section_index: int
    start_beats: float
    end_beats: float
    role: str
    emotion: str
    root_midi: int


def midi_to_name(midi: int) -> str:
    m = int(midi)
    return f"{NOTE_NAMES[m % 12]}{(m // 12) - 1}"


def build_sections(form: str, emotion: str, bars: int, root: int) -> Tuple[List[SongSectionSpec], str]:
    if form == "dialogue":
        return SongGenerator.pop_form(emotion, bars_per_section=int(bars), root_note=int(root)), "dialogue (call and response)"
    return SongGenerator.default_form(emotion, bars_per_section=int(bars), root_note=int(root)), "default"


def section_windows(song_render: Any, sections: Sequence[SongSectionSpec]) -> List[SectionWindow]:
    md = dict(getattr(song_render, "metadata", {}) or {})
    roles = list(md.get("section_roles") or [])
    out: List[SectionWindow] = []
    acc = 0.0
    for i, spec in enumerate(list(sections or [])):
        bars = int(getattr(spec, "bars", 0) or 0)
        if bars <= 0:
            continue
        start = float(acc)
        end = float(acc + (float(bars) * 4.0))
        role = str(roles[i] if i < len(roles) else "").strip().lower()
        emo = canonical_emotion_name(str(getattr(spec, "emotion_name", "") or ""))
        out.append(
            SectionWindow(
                section_index=int(i),
                start_beats=float(start),
                end_beats=float(end),
                role=str(role),
                emotion=str(emo),
                root_midi=int(getattr(spec, "root_note", 60) or 60),
            )
        )
        acc = end
    return out


def find_window(windows: Sequence[SectionWindow], start_beats: float) -> Optional[SectionWindow]:
    t = float(start_beats)
    for w in windows:
        if w.start_beats - 1e-9 <= t < w.end_beats - 1e-9:
            return w
    return windows[-1] if windows else None


def clip_duration_to_window(start_beats: float, duration_beats: float, window: Optional[SectionWindow]) -> float:
    if window is None:
        return max(0.0, float(duration_beats))
    return max(0.0, min(float(duration_beats), float(window.end_beats) - float(start_beats)))


def note_rows_for_song(
    *,
    song_events: Sequence[Tuple[Any, Any, Any, Any, Any, Any]],
    windows: Sequence[SectionWindow],
    base_emotion: str,
    run_index: int,
    seed: int,
    primary_emotion: str = "",
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    rows: List[Dict[str, Any]] = []
    by_run_total = 0
    by_run_in_key = 0
    by_run_in_key_primary = 0
    primary_name = canonical_emotion_name(str(primary_emotion or base_emotion))

    for ev in list(song_events or []):
        if not isinstance(ev, (tuple, list)) or len(ev) != 6:
            continue
        ch, _midi_field, vel, st, dur, notes = ev
        try:
            channel = int(ch)
            start_beats = float(st)
            duration_beats = float(dur)
            velocity = int(vel)
        except Exception:
            continue
        note_list = list(notes) if isinstance(notes, (list, tuple)) else []
        w = find_window(windows, start_beats)
        duration_beats = clip_duration_to_window(float(start_beats), float(duration_beats), w)
        sec_idx = int(getattr(w, "section_index", -1))
        sec_role = str(getattr(w, "role", ""))
        sec_emotion = str(getattr(w, "emotion", canonical_emotion_name(base_emotion)))
        sec_root = int(getattr(w, "root_midi", 60))
        sec_emotion_obj = EMOTION_BY_NAME.get(str(sec_emotion).strip().lower())
        allowed = {
            (sec_root + int(iv)) % 12
            for iv in melody_scale_intervals_for_emotion(sec_emotion_obj if sec_emotion_obj is not None else sec_emotion)
        }
        primary_obj = EMOTION_BY_NAME.get(str(primary_name).strip().lower())
        allowed_primary = {
            (sec_root + int(iv)) % 12
            for iv in melody_scale_intervals_for_emotion(primary_obj if primary_obj is not None else primary_name)
        }

        for n in note_list:
            if not isinstance(n, int):
                continue
            midi = int(n)
            pc = int(midi % 12)
            in_key = 1 if pc in allowed else 0
            in_key_primary = 1 if pc in allowed_primary else 0
            by_run_total += 1
            by_run_in_key += in_key
            by_run_in_key_primary += in_key_primary
            rows.append(
                {
                    "emotion": str(base_emotion),
                    "run_index": int(run_index),
                    "seed": int(seed),
                    "channel": int(channel),
                    "channel_name": str(CHANNEL_NAMES.get(channel, f"ch_{channel}")),
                    "start_beats": float(start_beats),
                    "duration_beats": float(duration_beats),
                    "velocity": int(velocity),
                    "midi": int(midi),
                    "note": str(midi_to_name(midi)),
                    "pc": int(pc),
                    "in_key": int(in_key),
                    "in_key_primary": int(in_key_primary),
                    "section_index": int(sec_idx),
                    "section_role": str(sec_role),
                    "section_emotion": str(sec_emotion),
                    "section_root_midi": int(sec_root),
                }
            )

    metrics = {
        "in_key_ratio": float(by_run_in_key / by_run_total) if by_run_total > 0 else 0.0,
        "in_key_primary_ratio": float(by_run_in_key_primary / by_run_total) if by_run_total > 0 else 0.0,
        "note_count": float(by_run_total),
    }
    return rows, metrics


def write_csv(path: Path, rows: Iterable[Dict[str, Any]], headers: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(headers))
        w.writeheader()
        for row in rows:
            w.writerow(dict(row))


def _median(values: Sequence[float]) -> float:
    vals = [float(v) for v in values]
    return float(statistics.median(vals)) if vals else 0.0


def _mean(values: Sequence[float]) -> float:
    vals = [float(v) for v in values]
    return float(sum(vals) / len(vals)) if vals else 0.0


def _percentile(values: Sequence[float], q: float) -> float:
    vals = sorted(float(v) for v in values)
    if not vals:
        return 0.0
    if len(vals) == 1:
        return float(vals[0])
    pos = (len(vals) - 1) * max(0.0, min(1.0, float(q)))
    lo = int(pos)
    hi = min(len(vals) - 1, lo + 1)
    frac = float(pos - lo)
    return float(vals[lo] * (1.0 - frac) + vals[hi] * frac)


def run_composition_diagnostics(
    note_rows: Sequence[Dict[str, Any]],
    sections: Sequence[SongSectionSpec],
) -> Dict[str, Any]:
    """Musical risk metrics that catch safe-but-generic full-song renders."""

    lead = [r for r in note_rows if str(r.get("channel_name", "")) == "melody"]
    counter = [r for r in note_rows if str(r.get("channel_name", "")) == "counter_melody"]
    pitches = [int(r.get("midi", 0)) for r in lead]
    total_bars = int(sum(int(getattr(s, "bars", 0) or 0) for s in sections))
    roots = {int(getattr(s, "root_note", 60) or 60) for s in sections}
    section_emotions = {str(getattr(s, "emotion_name", "") or "").strip().lower() for s in sections}

    if pitches:
        pitch_min = int(min(pitches))
        pitch_max = int(max(pitches))
        pitch_median = float(_median(pitches))
        pitch_p95 = float(_percentile(pitches, 0.95))
        ceiling = int(pitch_max)
        ceiling_hit_frac = float(sum(1 for p in pitches if int(p) >= ceiling) / max(1, len(pitches)))
        top_band_frac = float(sum(1 for p in pitches if int(p) >= ceiling - 2) / max(1, len(pitches)))
    else:
        pitch_min = pitch_max = 0
        pitch_median = pitch_p95 = ceiling_hit_frac = top_band_frac = 0.0

    # A high single-pitch concentration is a red flag for range-limit pileups.
    pitch_counts: Dict[int, int] = defaultdict(int)
    for p in pitches:
        pitch_counts[int(p)] += 1
    top_pitch_frac = float(max(pitch_counts.values()) / max(1, len(pitches))) if pitch_counts else 0.0

    return {
        "total_bars": int(total_bars),
        "lead_pitch_min": int(pitch_min),
        "lead_pitch_max": int(pitch_max),
        "lead_pitch_median": float(pitch_median),
        "lead_pitch_p95": float(pitch_p95),
        "lead_ceiling_hit_frac": float(ceiling_hit_frac),
        "lead_top_band_frac": float(top_band_frac),
        "lead_top_pitch_frac": float(top_pitch_frac),
        "unique_section_roots": int(len(roots)),
        "unique_section_emotions": int(len({e for e in section_emotions if e})),
        "counter_melody_events": int(len(counter)),
        "counter_melody_events_per_bar": float(len(counter) / max(1, total_bars)),
    }


def canonical_arrangement_role(role: str) -> str:
    raw = str(role or "").strip().lower()
    return {
        "a": "verse",
        "verse": "verse",
        "b": "chorus",
        "chorus": "chorus",
        "hook": "chorus",
        "pre": "pre_chorus",
        "pre_chorus": "pre_chorus",
        "intro": "intro",
        "outro": "outro",
        "tag": "outro",
    }.get(raw, raw)


def section_arrangement_rows_for_song(
    *,
    song_events: Sequence[Tuple[Any, Any, Any, Any, Any, Any]],
    windows: Sequence[SectionWindow],
    base_emotion: str,
    run_index: int,
    seed: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    events = [ev for ev in list(song_events or []) if isinstance(ev, (tuple, list)) and len(ev) == 6]

    for window in windows:
        section_events: List[Tuple[int, float, float, int, List[int]]] = []
        for ev in events:
            try:
                channel = int(ev[0])
                velocity = int(ev[2])
                start = float(ev[3])
                duration = float(ev[4])
            except Exception:
                continue
            if not (float(window.start_beats) - 1e-9 <= start < float(window.end_beats) - 1e-9):
                continue
            duration = clip_duration_to_window(float(start), float(duration), window)
            notes = [int(n) for n in list(ev[5] or []) if isinstance(n, int)]
            section_events.append((channel, start, duration, velocity, notes))

        bars = max(1e-9, (float(window.end_beats) - float(window.start_beats)) / 4.0)
        lead_events = [ev for ev in section_events if ev[0] == 2 and ev[4]]
        arp_events = [ev for ev in section_events if ev[0] == 3 and ev[4]]
        lead_notes = [int(n) for _ch, _st, _dur, _vel, notes in lead_events for n in notes]
        arp_notes = [int(n) for _ch, _st, _dur, _vel, notes in arp_events for n in notes]
        lead_beats = float(sum(float(ev[2]) for ev in lead_events))
        arp_beats = float(sum(float(ev[2]) for ev in arp_events))
        active_channels = sorted({int(ch) for ch, _st, _dur, _vel, notes in section_events if notes})

        chord_shapes: List[Tuple[int, ...]] = []
        for ch, _st, _dur, _vel, notes in sorted(section_events, key=lambda item: float(item[1])):
            if ch != 1 or not notes:
                continue
            shape = tuple(sorted({int(n) % 12 for n in notes}))
            if shape and (not chord_shapes or shape != chord_shapes[-1]):
                chord_shapes.append(shape)

        rows.append(
            {
                "emotion": str(base_emotion),
                "run_index": int(run_index),
                "seed": int(seed),
                "section_index": int(window.section_index),
                "section_role": str(window.role),
                "section_emotion": str(window.emotion),
                "section_bars": float(bars),
                "lead_note_count": int(len(lead_notes)),
                "lead_onset_count": int(len(lead_events)),
                "lead_notes_per_bar": float(len(lead_notes) / bars),
                "lead_onsets_per_bar": float(len(lead_events) / bars),
                "lead_beats_per_bar": float(lead_beats / bars),
                "lead_coverage_ratio": float(lead_beats / max(1e-9, bars * 4.0)),
                "lead_register_median": float(_median(lead_notes)),
                "lead_velocity_avg": float(_mean([float(ev[3]) for ev in lead_events])),
                "arp_note_count": int(len(arp_notes)),
                "arp_onset_count": int(len(arp_events)),
                "arp_notes_per_bar": float(len(arp_notes) / bars),
                "arp_onsets_per_bar": float(len(arp_events) / bars),
                "arp_beats_per_bar": float(arp_beats / bars),
                "arp_register_median": float(_median(arp_notes)),
                "arp_velocity_avg": float(_mean([float(ev[3]) for ev in arp_events])),
                "chord_change_rate_per_bar": float(max(0, len(chord_shapes) - 1) / bars),
                "texture_channel_count": int(len(active_channels)),
                "texture_signature": "+".join(str(ch) for ch in active_channels),
            }
        )
    return rows


def summarize_section_roles(section_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in section_rows:
        role = canonical_arrangement_role(str(row.get("section_role", "")))
        if not role:
            continue
        grouped[(str(row.get("emotion", "")), role)].append(dict(row))

    metric_keys = (
        "lead_notes_per_bar",
        "lead_onsets_per_bar",
        "lead_register_median",
        "lead_velocity_avg",
        "lead_beats_per_bar",
        "lead_coverage_ratio",
        "arp_notes_per_bar",
        "arp_onsets_per_bar",
        "arp_beats_per_bar",
        "arp_register_median",
        "arp_velocity_avg",
        "chord_change_rate_per_bar",
        "texture_channel_count",
    )
    out: List[Dict[str, Any]] = []
    for (emotion, role), rows in sorted(grouped.items()):
        item: Dict[str, Any] = {
            "emotion": str(emotion),
            "section_role": str(role),
            "sections": int(len(rows)),
        }
        for key in metric_keys:
            item[f"{key}_avg"] = float(_mean([float(r.get(key, 0.0)) for r in rows]))
        item["texture_signature_count"] = int(len({str(r.get("texture_signature", "")) for r in rows}))
        out.append(item)
    return out


def _audit_tension_arc(emotion: str) -> str:
    try:
        from data.tension_arc_dynamics import tension_arc_for_emotion

        return str(tension_arc_for_emotion(str(emotion or "")) or "rise")
    except Exception:
        return "rise"


def _intro_chorus_velocity_arc_fit(delta: float, tension_arc: str) -> float:
    """How well intro→chorus velocity change matches the emotion's tension_arc template."""
    d = float(delta)
    arc = str(tension_arc or "rise").strip().lower()
    if arc == "fall":
        if d <= 2.0:
            return 1.0
        if d <= 8.0:
            return max(0.0, min(1.0, 1.0 - (d - 2.0) / 8.0))
        return max(0.0, min(1.0, 1.0 - (d - 8.0) / 14.0))
    if arc == "flat":
        if 8.0 <= d <= 40.0:
            return max(0.0, min(1.0, 1.0 - abs(d - 24.0) / 22.0))
        if d < 8.0:
            return max(0.0, min(1.0, d / 8.0))
        return max(0.0, min(1.0, 1.0 - (d - 40.0) / 16.0))
    if arc == "spike":
        if d >= 14.0:
            return 1.0
        if d >= 8.0:
            return max(0.0, min(1.0, 0.75 + (d - 8.0) / 24.0))
        return max(0.0, min(1.0, d / 8.0))
    # rise
    if d >= 10.0:
        return 1.0
    if d >= 6.0:
        return max(0.0, min(1.0, 0.7 + (d - 6.0) / 16.0))
    return max(0.0, min(1.0, d / 6.0))


def summarize_arrangement_contrast(role_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_emotion: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for row in role_rows:
        by_emotion[str(row.get("emotion", ""))][str(row.get("section_role", ""))] = dict(row)

    out: List[Dict[str, Any]] = []
    for emotion, roles in sorted(by_emotion.items()):
        verse = roles.get("verse", {})
        pre = roles.get("pre_chorus", {})
        chorus = roles.get("chorus", {})
        intro = roles.get("intro", {})
        outro = roles.get("outro", {})

        def value(role_row: Dict[str, Any], key: str) -> float:
            if key in role_row:
                return float(role_row.get(key, 0.0))
            if key == "lead_beats_per_bar_avg":
                return float(role_row.get("lead_onsets_per_bar_avg", 0.0))
            if key == "lead_coverage_ratio_avg":
                return float(role_row.get("lead_beats_per_bar_avg", role_row.get("lead_onsets_per_bar_avg", 0.0))) / 4.0
            return 0.0

        verse_chorus_lead_delta = value(chorus, "lead_notes_per_bar_avg") - value(verse, "lead_notes_per_bar_avg")
        verse_chorus_lead_beats_delta = value(chorus, "lead_beats_per_bar_avg") - value(verse, "lead_beats_per_bar_avg")
        verse_chorus_lead_coverage_delta = value(chorus, "lead_coverage_ratio_avg") - value(verse, "lead_coverage_ratio_avg")
        verse_chorus_arp_delta = value(chorus, "arp_notes_per_bar_avg") - value(verse, "arp_notes_per_bar_avg")
        verse_chorus_register_delta = value(chorus, "lead_register_median_avg") - value(verse, "lead_register_median_avg")
        intro_chorus_velocity_delta = value(chorus, "lead_velocity_avg_avg") - value(intro, "lead_velocity_avg_avg")
        tension_arc = _audit_tension_arc(str(emotion))
        velocity_arc_fit = _intro_chorus_velocity_arc_fit(intro_chorus_velocity_delta, tension_arc)
        pre_chorus_harmony_delta = value(chorus, "chord_change_rate_per_bar_avg") - value(pre, "chord_change_rate_per_bar_avg")
        chorus_outro_density_delta = value(chorus, "lead_notes_per_bar_avg") - value(outro, "lead_notes_per_bar_avg")
        texture_span = max(
            [value(row, "texture_channel_count_avg") for row in roles.values()] or [0.0]
        ) - min([value(row, "texture_channel_count_avg") for row in roles.values()] or [0.0])
        issue_flags = []
        if verse_chorus_lead_delta < 0.75 and verse_chorus_lead_coverage_delta < 0.05:
            issue_flags.append("weak_chorus_lead_payoff")
        if verse_chorus_register_delta < 2.0:
            issue_flags.append("weak_chorus_register_lift")
        if verse_chorus_register_delta > 12.0:
            issue_flags.append("excessive_chorus_register_jump")
        if velocity_arc_fit < 0.75:
            issue_flags.append("weak_dynamic_arc")
        if pre_chorus_harmony_delta < 0.0:
            issue_flags.append("chorus_harmony_less_active_than_pre")
        if chorus_outro_density_delta < 0.75:
            issue_flags.append("weak_outro_release")
        if texture_span < 1.0:
            issue_flags.append("weak_texture_span")

        contrast_score = 100.0 * (
            0.12 * _clamp01(verse_chorus_lead_delta / 2.0)
            + 0.16 * _clamp01(verse_chorus_lead_beats_delta / 0.8)
            + 0.18 * _clamp01(verse_chorus_register_delta / 4.0)
            + 0.16 * float(velocity_arc_fit)
            + 0.12 * _clamp01(abs(verse_chorus_arp_delta) / 2.0)
            + 0.16 * _clamp01(chorus_outro_density_delta / 1.0)
            + 0.10 * _clamp01(texture_span / 1.0)
        )
        contrast_score -= 10.0 * _clamp01((verse_chorus_register_delta - 12.0) / 8.0)
        contrast_score -= 8.0 * _clamp01(abs(min(0.0, pre_chorus_harmony_delta)) / 0.8)
        contrast_score = 100.0 * _clamp01(float(contrast_score) / 100.0)
        out.append(
            {
                "emotion": str(emotion),
                "verse_to_chorus_lead_notes_per_bar_delta": float(verse_chorus_lead_delta),
                "verse_to_chorus_lead_beats_per_bar_delta": float(verse_chorus_lead_beats_delta),
                "verse_to_chorus_lead_coverage_delta": float(verse_chorus_lead_coverage_delta),
                "verse_to_chorus_arp_notes_per_bar_delta": float(verse_chorus_arp_delta),
                "verse_to_chorus_lead_register_delta": float(verse_chorus_register_delta),
                "intro_to_chorus_lead_velocity_delta": float(intro_chorus_velocity_delta),
                "tension_arc": str(tension_arc),
                "intro_chorus_velocity_arc_fit": float(velocity_arc_fit),
                "pre_to_chorus_chord_motion_delta": float(pre_chorus_harmony_delta),
                "chorus_to_outro_lead_notes_per_bar_delta": float(chorus_outro_density_delta),
                "texture_channel_span": float(texture_span),
                "contrast_issue_count": int(len(issue_flags)),
                "weak_contrast_flags": ";".join(issue_flags),
                "arrangement_contrast_score": float(contrast_score),
            }
        )
    return out


def _fmt(x: float) -> str:
    return f"{float(x):0.3f}"


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def professional_quality_score(row: Dict[str, Any]) -> float:
    """Composite 0..100 quality score (delegates to ``composition.audit_aligned_score``)."""
    from composition.audit_aligned_score import professional_quality_score as _pqs

    return float(_pqs(row))


EMOTION_MATCH_TARGETS: Dict[str, Dict[str, Any]] = {
    # target ranges are intentionally broad: they describe emotional production intent,
    # not correctness. Missing emotions fall back to valence/arousal-derived defaults.
    "sadness": {"density": (0.50, 0.70), "register": (64, 73), "motion": (0.75, 1.30), "overlap": (0.12, 0.22), "descent": (0.54, 0.70), "leap": (5.0, 9.5), "counter": (0.08, 0.22)},
    "grief": {"density": (0.44, 0.64), "register": (63, 73), "motion": (0.60, 1.15), "overlap": (0.10, 0.22), "descent": (0.58, 0.82), "leap": (5.0, 9.5), "counter": (0.10, 0.24)},
    "remorse": {"density": (0.46, 0.66), "register": (63, 73), "motion": (0.65, 1.20), "overlap": (0.10, 0.22), "descent": (0.58, 0.80), "leap": (5.0, 9.5), "counter": (0.10, 0.24)},
    "relief": {"density": (0.56, 0.74), "register": (66, 76), "motion": (0.75, 1.35), "overlap": (0.12, 0.23), "descent": (0.48, 0.64), "leap": (5.0, 9.5), "counter": (0.02, 0.09)},
    "desire": {"density": (0.58, 0.76), "register": (67, 77), "motion": (0.75, 1.30), "overlap": (0.12, 0.24), "descent": (0.44, 0.60), "leap": (6.0, 10.5), "counter": (0.04, 0.10)},
    "love": {"density": (0.56, 0.74), "register": (66, 76), "motion": (0.65, 1.20), "overlap": (0.12, 0.23), "descent": (0.45, 0.62), "leap": (5.0, 9.5), "counter": (0.02, 0.09)},
    "caring": {"density": (0.54, 0.72), "register": (65, 75), "motion": (0.65, 1.20), "overlap": (0.10, 0.22), "descent": (0.48, 0.66), "leap": (5.0, 9.5), "counter": (0.08, 0.22)},
    "joy": {"density": (0.62, 0.82), "register": (70, 81), "motion": (0.95, 1.55), "overlap": (0.14, 0.25), "descent": (0.36, 0.54), "leap": (6.0, 10.5), "counter": (0.10, 0.24)},
    "amusement": {"density": (0.60, 0.80), "register": (72, 84), "motion": (1.00, 1.60), "overlap": (0.14, 0.25), "descent": (0.30, 0.50), "leap": (6.0, 10.5), "counter": (0.10, 0.24)},
    "excitement": {"density": (0.64, 0.84), "register": (70, 82), "motion": (1.05, 1.70), "overlap": (0.14, 0.26), "descent": (0.32, 0.52), "leap": (6.0, 11.0), "counter": (0.10, 0.24)},
    "anger": {"density": (0.56, 0.76), "register": (62, 74), "motion": (0.95, 1.65), "overlap": (0.08, 0.20), "descent": (0.48, 0.66), "leap": (6.0, 11.0), "counter": (0.02, 0.09)},
    "fear": {"density": (0.58, 0.78), "register": (66, 78), "motion": (1.00, 1.75), "overlap": (0.10, 0.24), "descent": (0.46, 0.66), "leap": (6.0, 11.0), "counter": (0.01, 0.08)},
    "nervousness": {"density": (0.58, 0.78), "register": (66, 78), "motion": (1.00, 1.70), "overlap": (0.10, 0.24), "descent": (0.44, 0.64), "leap": (6.0, 11.0), "counter": (0.01, 0.08)},
    "confusion": {"density": (0.58, 0.78), "register": (66, 78), "motion": (1.00, 1.70), "overlap": (0.10, 0.24), "descent": (0.40, 0.62), "leap": (6.0, 11.0), "counter": (0.03, 0.11)},
    "disgust": {"density": (0.56, 0.76), "register": (64, 76), "motion": (0.90, 1.55), "overlap": (0.10, 0.23), "descent": (0.50, 0.70), "leap": (5.5, 10.5), "counter": (0.03, 0.10)},
    "approval": {"density": (0.52, 0.74), "register": (68, 80), "motion": (0.70, 1.35), "overlap": (0.10, 0.22), "descent": (0.32, 0.52), "leap": (5.0, 9.5), "counter": (0.10, 0.24)},
    "disapproval": {"density": (0.52, 0.72), "register": (60, 72), "motion": (0.80, 1.45), "overlap": (0.08, 0.20), "descent": (0.52, 0.72), "leap": (5.0, 10.0), "counter": (0.02, 0.09)},
    "embarrassment": {"density": (0.50, 0.70), "register": (63, 74), "motion": (0.75, 1.35), "overlap": (0.10, 0.22), "descent": (0.50, 0.70), "leap": (5.0, 10.0), "counter": (0.00, 0.06)},
}


def emotion_match_features(note_rows: Sequence[Dict[str, Any]], run_row: Dict[str, Any]) -> Dict[str, float]:
    lead = [
        r for r in note_rows
        if str(r.get("channel_name", "")) == "melody"
        and str(r.get("emotion", "")) == str(run_row.get("emotion", ""))
        and int(r.get("run_index", -1)) == int(run_row.get("run_index", -2))
    ]
    lead_sorted = sorted(lead, key=lambda r: float(r.get("start_beats", 0.0)))
    intervals: List[int] = []
    for a, b in zip(lead_sorted, lead_sorted[1:]):
        intervals.append(int(b.get("midi", 0)) - int(a.get("midi", 0)))
    nonzero = [iv for iv in intervals if int(iv) != 0]
    down = [iv for iv in nonzero if int(iv) < 0]
    descent_ratio = float(len(down) / max(1, len(nonzero))) if nonzero else 0.5
    return {
        "density": float(run_row.get("lead_activity", 0.0)),
        "register": float(run_row.get("lead_pitch_median", 0.0)),
        "motion": float(run_row.get("chord_change_rate_per_bar", 0.0)),
        "overlap": float(run_row.get("lead_arp_overlap", 0.0)),
        "descent": float(descent_ratio),
        "leap": float(run_row.get("lead_abs_interval_p95", 0.0)),
        "counter": float(run_row.get("counter_melody_events_per_bar", 0.0)),
    }


def _range_fit(value: float, lo: float, hi: float) -> float:
    v = float(value)
    lo_f = float(lo)
    hi_f = float(hi)
    if lo_f <= v <= hi_f:
        return 1.0
    span = max(1e-6, hi_f - lo_f)
    dist = lo_f - v if v < lo_f else v - hi_f
    return _clamp01(1.0 - float(dist) / float(span))


def emotion_match_score(emotion: str, features: Dict[str, float]) -> Dict[str, Any]:
    emo = canonical_emotion_name(str(emotion or ""))
    target = dict(EMOTION_MATCH_TARGETS.get(emo, {}) or {})
    if not target:
        target = {"density": (0.56, 0.76), "register": (65, 78), "motion": (0.75, 1.55), "overlap": (0.10, 0.24), "descent": (0.42, 0.64), "leap": (5.0, 10.5), "counter": (0.10, 0.24)}
    weights = {"density": 0.18, "register": 0.18, "motion": 0.14, "overlap": 0.12, "descent": 0.18, "leap": 0.12, "counter": 0.08}
    parts: Dict[str, float] = {}
    for key, weight in weights.items():
        lo, hi = target.get(key, (0.0, 1.0))
        parts[key] = float(_range_fit(float(features.get(key, 0.0)), float(lo), float(hi)))
    score = 100.0 * _clamp01(sum(float(weights[k]) * float(parts[k]) for k in weights))
    weakest = sorted(parts.items(), key=lambda kv: float(kv[1]))[:3]
    return {
        "emotion_match_score": float(score),
        "emotion_match_weakest": ";".join(f"{k}:{_fmt(v)}" for k, v in weakest),
        **{f"emotion_match_{k}_fit": float(v) for k, v in parts.items()},
    }


def hook_development_features(note_rows: Sequence[Dict[str, Any]], run_row: Dict[str, Any]) -> Dict[str, float]:
    lead = [
        r for r in note_rows
        if str(r.get("channel_name", "")) == "melody"
        and str(r.get("emotion", "")) == str(run_row.get("emotion", ""))
        and int(r.get("run_index", -1)) == int(run_row.get("run_index", -2))
    ]
    if not lead:
        return {"hook_identity_score": 0.0, "chorus_payoff_score": 0.0, "motif_development_score": 0.0}

    by_section: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    role_by_section: Dict[int, str] = {}
    for r in lead:
        try:
            sec = int(r.get("section_index", -1))
        except Exception:
            continue
        if sec < 0:
            continue
        by_section[int(sec)].append(r)
        role_by_section[int(sec)] = str(r.get("section_role", "")).strip().lower()
    for rows in by_section.values():
        rows.sort(key=lambda r: float(r.get("start_beats", 0.0)))

    def _bucket(v: float) -> float:
        if v <= 0.25:
            return 0.25
        if v <= 0.5:
            return 0.5
        if v <= 1.0:
            return 1.0
        return 2.0

    def _signature(rows: Sequence[Dict[str, Any]], *, max_notes: int = 6) -> List[Tuple[int, float, float]]:
        rows0 = list(rows or [])
        if not rows0:
            return []
        start0 = float(rows0[0].get("start_beats", 0.0))
        window = [
            r for r in rows0
            if float(r.get("start_beats", 0.0)) < start0 + 8.0 - 1e-6
        ][:max_notes]
        if len(window) < 3:
            return []
        p0 = int(window[0].get("midi", 0))
        out: List[Tuple[int, float, float]] = []
        for r in window:
            out.append(
                (
                    int(r.get("midi", 0)) - int(p0),
                    _bucket(float(r.get("start_beats", 0.0)) - start0),
                    _bucket(float(r.get("duration_beats", 0.0))),
                )
            )
        return out

    def _sim(a: Sequence[Tuple[int, float, float]], b: Sequence[Tuple[int, float, float]]) -> float:
        if not a or not b:
            return 0.0
        n = min(len(a), len(b))
        if n <= 0:
            return 0.0
        hits = 0.0
        for i in range(n):
            ai = a[i]
            bi = b[i]
            pitch_fit = 1.0 if abs(int(ai[0]) - int(bi[0])) <= 2 else (0.5 if abs(int(ai[0]) - int(bi[0])) <= 5 else 0.0)
            rhythm_fit = 1.0 if abs(float(ai[1]) - float(bi[1])) <= 0.25 else 0.0
            dur_fit = 1.0 if abs(float(ai[2]) - float(bi[2])) <= 0.25 else 0.4
            hits += 0.55 * pitch_fit + 0.30 * rhythm_fit + 0.15 * dur_fit
        return _clamp01(hits / float(n))

    chorus_secs = [
        sec for sec, role in sorted(role_by_section.items())
        if role in {"b", "chorus", "hook", "tag"}
    ]
    verse_secs = [
        sec for sec, role in sorted(role_by_section.items())
        if role in {"a", "verse", "a_prime"}
    ]
    pre_secs = [sec for sec, role in sorted(role_by_section.items()) if role == "pre_chorus"]
    if not chorus_secs:
        return {"hook_identity_score": 0.0, "chorus_payoff_score": 0.0, "motif_development_score": 0.0}

    hook_sig = _signature(by_section.get(chorus_secs[0], []), max_notes=7)
    chorus_sims = [
        _sim(hook_sig, _signature(by_section.get(sec, []), max_notes=7))
        for sec in chorus_secs[1:]
    ]
    chorus_consistency = sum(chorus_sims) / max(1, len(chorus_sims)) if chorus_sims else (1.0 if hook_sig else 0.0)
    family_secs = verse_secs[:2] + pre_secs[:1]
    family_sims = [
        _sim(hook_sig, _signature(by_section.get(sec, []), max_notes=5))
        for sec in family_secs
    ]
    family_avg = sum(family_sims) / max(1, len(family_sims)) if family_sims else 0.0
    # Good development is recognisable but not copy-paste.
    motif_development = _clamp01(1.0 - abs(float(family_avg) - 0.48) / 0.48)
    hook_identity = _clamp01(0.68 * float(chorus_consistency) + 0.32 * float(family_avg))

    def _section_stats(secs: Sequence[int]) -> Tuple[float, float, float]:
        counts: List[float] = []
        regs: List[float] = []
        vels: List[float] = []
        for sec in secs:
            rows = list(by_section.get(int(sec), []) or [])
            if not rows:
                continue
            counts.append(float(len(rows)))
            pitches = sorted(int(r.get("midi", 0)) for r in rows)
            regs.append(float(pitches[len(pitches) // 2]))
            vels.append(sum(float(r.get("velocity", 0.0)) for r in rows) / max(1, len(rows)))
        if not counts:
            return (0.0, 0.0, 0.0)
        return (
            sum(counts) / float(len(counts)),
            sum(regs) / float(len(regs)),
            sum(vels) / float(len(vels)),
        )

    chorus_count, chorus_reg, chorus_vel = _section_stats(chorus_secs)
    verse_count, verse_reg, verse_vel = _section_stats(verse_secs or pre_secs)
    density_lift = _clamp01((float(chorus_count) - float(verse_count) + 4.0) / 12.0)
    register_lift = _clamp01((float(chorus_reg) - float(verse_reg) + 2.0) / 10.0)
    velocity_lift = _clamp01((float(chorus_vel) - float(verse_vel) + 8.0) / 28.0)
    chorus_payoff = _clamp01(0.42 * density_lift + 0.36 * register_lift + 0.22 * velocity_lift)
    return {
        "hook_identity_score": float(hook_identity),
        "chorus_payoff_score": float(chorus_payoff),
        "motif_development_score": float(motif_development),
    }


def harmonic_melody_metrics(
    events: Sequence[Sequence[Any]],
    *,
    beats_per_bar: float = 4.0,
    bars: Optional[int] = None,
    phrase_spans: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    if bars is None:
        mx = 0.0
        for ev in events:
            if not ev or len(ev) != 6:
                continue
            try:
                mx = max(mx, float(ev[3]) + float(ev[4]))
            except Exception:
                continue
        bars_n = int(max(1, round(mx / bpb))) if mx > 1e-6 else 0
    else:
        bars_n = int(bars)
    bars_n = max(0, int(bars_n))

    strong_eps = 0.06
    phrase_end_eps = 0.65

    chord_by_bar: List[List[Tuple[float, float, set[int]]]] = [[] for _ in range(bars_n)]
    chord_pcs_by_bar: List[set[int]] = [set() for _ in range(bars_n)]
    melody_by_bar: List[List[Tuple[float, float, int]]] = [[] for _ in range(bars_n)]
    chord_segments_abs: List[Tuple[float, float, set[int]]] = []
    melody_events_abs: List[Tuple[float, float, int]] = []

    for ev in events:
        if not ev or len(ev) != 6:
            continue
        try:
            ch = int(ev[0])
            st = float(ev[3])
            dur = float(ev[4])
            notes = ev[5] if len(ev) > 5 else None
        except Exception:
            continue
        if dur <= 1e-9:
            continue
        bar = int(st // bpb) if bpb > 1e-9 else 0
        if bar < 0 or bar >= bars_n:
            continue
        st_local = float(st - float(bar) * bpb)
        en_local = float(min(st_local + dur, bpb))
        if en_local <= st_local + 1e-9:
            continue
        if ch == 1:
            pcs = set()
            if isinstance(notes, list):
                for n in notes:
                    if isinstance(n, int):
                        pcs.add(int(n) % 12)
            if pcs:
                chord_by_bar[bar].append((st_local, en_local, set(pcs)))
                chord_pcs_by_bar[bar].update(set(pcs))
                chord_segments_abs.append((float(st), float(st + dur), set(pcs)))
        elif ch == 2:
            try:
                pitch = int(notes[0]) if isinstance(notes, list) and notes else int(ev[1])
            except Exception:
                continue
            melody_by_bar[bar].append((st_local, en_local, int(pitch)))
            melody_events_abs.append((float(st), float(st + dur), int(pitch)))

    for bi in range(bars_n):
        chord_by_bar[bi].sort(key=lambda x: float(x[0]))
        melody_by_bar[bi].sort(key=lambda x: float(x[0]))
    chord_segments_abs.sort(key=lambda x: float(x[0]))
    melody_events_abs.sort(key=lambda x: float(x[0]))

    phrase_end_bars = set()
    if bars_n > 0:
        for bi in range(bars_n):
            if (int(bi) % 4) == 3 or int(bi) == int(bars_n) - 1:
                phrase_end_bars.add(int(bi))

    def _active_pcs_for_onset(bar: int, onset_local: float) -> set[int]:
        if bar < 0 or bar >= bars_n:
            return set()
        for s0, s1, pcs in chord_by_bar[bar]:
            if float(s0) - 1e-6 <= float(onset_local) <= float(s1) + 1e-6:
                return set(pcs)
        return set(chord_pcs_by_bar[bar])

    def _active_pcs_for_absolute_onset(onset_beats: float) -> set[int]:
        onset = float(onset_beats)
        for s0, s1, pcs in chord_segments_abs:
            if float(s0) - 1e-6 <= onset <= float(s1) + 1e-6:
                return set(pcs)
        bar = int(onset // bpb) if bpb > 1e-9 else 0
        if 0 <= bar < len(chord_pcs_by_bar):
            return set(chord_pcs_by_bar[bar])
        return set()

    strong_total = 0
    strong_hit = 0
    onset_total = 0
    onset_hit = 0
    phrase_total = 0
    phrase_hit = 0

    for bi in range(bars_n):
        mel = melody_by_bar[bi]
        if not mel:
            continue
        for st0, _en0, mp in mel:
            pcs = _active_pcs_for_onset(int(bi), float(st0))
            if not pcs:
                continue
            onset_total += 1
            if (int(mp) % 12) in pcs:
                onset_hit += 1
            nearest = round(float(st0))
            if abs(float(st0) - float(nearest)) <= strong_eps:
                strong_total += 1
                if (int(mp) % 12) in pcs:
                    strong_hit += 1

    phrase_spans_list = [dict(x) for x in list(phrase_spans or []) if isinstance(x, dict)]
    if phrase_spans_list and melody_events_abs:
        prev_end = 0.0
        for span in phrase_spans_list:
            try:
                phrase_end = float(span.get("absolute_end_beats", span.get("end_beats")))
            except Exception:
                continue
            if phrase_end <= prev_end + 1e-6:
                prev_end = max(prev_end, phrase_end)
                continue
            last = None
            for st0, _en0, mp in melody_events_abs:
                if float(st0) >= float(phrase_end) - 1e-6:
                    break
                if float(st0) < float(prev_end) - 1e-6:
                    continue
                last = (float(st0), int(mp))
            prev_end = phrase_end
            if last is None:
                continue
            pcs_last = _active_pcs_for_absolute_onset(float(last[0]))
            if not pcs_last:
                continue
            phrase_total += 1
            if (int(last[1]) % 12) in pcs_last:
                phrase_hit += 1
    else:
        for bi in range(bars_n):
            mel = melody_by_bar[bi]
            if not mel:
                continue
            if int(bi) in phrase_end_bars:
                st_last, _en_last, mp_last = mel[-1]
                if float(st_last) >= float(bpb) - float(phrase_end_eps):
                    pcs_last = _active_pcs_for_onset(int(bi), float(st_last))
                    if pcs_last:
                        phrase_total += 1
                        if (int(mp_last) % 12) in pcs_last:
                            phrase_hit += 1

    return {
        "mh_onset_total": int(onset_total),
        "mh_onset_hit": int(onset_hit),
        "mh_onset_chord_tone_frac": float(onset_hit / onset_total) if onset_total > 0 else 0.5,
        "mh_strongbeat_total": int(strong_total),
        "mh_strongbeat_hit": int(strong_hit),
        "mh_strongbeat_chord_tone_frac": float(strong_hit / strong_total) if strong_total > 0 else 0.5,
        "mh_phrase_end_total": int(phrase_total),
        "mh_phrase_end_hit": int(phrase_hit),
        "mh_phrase_end_chord_tone_frac": float(phrase_hit / phrase_total) if phrase_total > 0 else 0.5,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate full-song note audit (3 seeds per emotion by default).")
    ap.add_argument("--emotion", default=None, help="Single emotion; if omitted runs all emotions.")
    ap.add_argument("--runs-per-emotion", type=int, default=3)
    ap.add_argument("--bars", type=int, default=8, help="Bars-per-section input to SongGenerator forms.")
    ap.add_argument("--root", type=int, default=60)
    ap.add_argument("--form", choices=["default", "dialogue"], default="default")
    ap.add_argument("--seed-base", type=int, default=100000)
    ap.add_argument(
        "--random-seeds",
        action="store_true",
        help="Use fresh random 32-bit seeds instead of seed-base + offsets.",
    )
    ap.add_argument("--k", type=int, default=1, help="Best-of-k candidates per run.")
    ap.add_argument("--time-budget-s", type=float, default=None)
    ap.add_argument("--out-dir", default="logs")
    ap.add_argument(
        "--song-upgrade-phase-c",
        action="store_true",
        help="Re-apply song-upgrade Phase C profile (default on CONFIG).",
    )
    ap.add_argument(
        "--legacy-composition",
        action="store_true",
        help="Disable song-upgrade profiles for this audit run.",
    )
    ap.add_argument(
        "--song-rerank-model",
        default="artifacts/song_rerank/rerank_v1.json",
        help="Rerank model JSON path when Phase C profile is enabled.",
    )
    args = ap.parse_args()

    from audiogen_core.config import CONFIG
    from audiogen_core.song_upgrade_profile import apply_legacy_composition_profile, apply_phase_c_profile

    if bool(getattr(args, "legacy_composition", False)):
        apply_legacy_composition_profile(CONFIG)
    elif bool(getattr(args, "song_upgrade_phase_c", False)):
        model_path = str(getattr(args, "song_rerank_model", "") or "").strip()
        apply_phase_c_profile(CONFIG)
        if model_path:
            CONFIG.composition.song_rerank_model_path = model_path
    else:
        model_path = str(getattr(args, "song_rerank_model", "") or "").strip()
        if model_path and model_path != "artifacts/song_rerank/rerank_v1.json":
            CONFIG.composition.song_rerank_model_path = model_path

    if args.emotion:
        emotions = [canonical_emotion_name(str(args.emotion))]
    else:
        emotions = [str(getattr(e, "name", "")).strip().lower() for e in list(EMOTIONS or []) if str(getattr(e, "name", "")).strip()]

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(str(args.out_dir)).expanduser() / f"full_song_seed_audit_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    sg = SongGenerator()
    note_rows: List[Dict[str, Any]] = []
    run_rows: List[Dict[str, Any]] = []
    section_rows: List[Dict[str, Any]] = []
    used_seeds: set[int] = set()

    def _seed_for_run(emo_idx: int, run_idx: int) -> int:
        if not bool(args.random_seeds):
            return int(args.seed_base) + (int(emo_idx) * 1000) + int(run_idx)
        while True:
            seed0 = int(secrets.randbits(32))
            if seed0 not in used_seeds:
                used_seeds.add(seed0)
                return int(seed0)

    for emo_idx, emotion in enumerate(emotions):
        for run_idx in range(int(max(1, args.runs_per_emotion))):
            seed = _seed_for_run(int(emo_idx), int(run_idx))
            sections, arrangement_form = build_sections(str(args.form), str(emotion), int(args.bars), int(args.root))
            if int(args.k) > 1:
                song = sg.generate_song_best_of_k(
                    sections,
                    base_tempo_bpm=70.0,
                    arrangement_form=str(arrangement_form),
                    seed=int(seed),
                    k=int(args.k),
                    time_budget_s=args.time_budget_s,
                )
            else:
                song = sg.generate_song(
                    sections,
                    base_tempo_bpm=70.0,
                    arrangement_form=str(arrangement_form),
                    seed=int(seed),
                )
            events = list(getattr(song, "events", []) or [])
            windows = section_windows(song, sections)
            primary = str(
                (getattr(song, "metadata", {}) or {}).get("primary_emotion_for_postprocess")
                or emotion
            )
            rows, key_metrics = note_rows_for_song(
                song_events=events,
                windows=windows,
                base_emotion=str(emotion),
                run_index=int(run_idx),
                seed=int(seed),
                primary_emotion=str(primary),
            )
            from tools.analysis.emotion_panel_metrics import lead_tonality_metrics

            lead_tone = lead_tonality_metrics(
                events,
                specs=sections,
                primary_emotion=str(primary),
            )
            composition_metrics = run_composition_diagnostics(rows, sections)
            note_rows.extend(rows)
            section_rows.extend(
                section_arrangement_rows_for_song(
                    song_events=events,
                    windows=windows,
                    base_emotion=str(emotion),
                    run_index=int(run_idx),
                    seed=int(seed),
                )
            )

            total_bars = int(sum(int(getattr(s, "bars", 0) or 0) for s in sections)) if sections else None
            eval_metrics = evaluate_song(events, beats_per_bar=4.0, bars=total_bars)
            harmony_metrics = harmonic_melody_metrics(
                events,
                beats_per_bar=4.0,
                phrase_spans=list((getattr(song, "metadata", {}) or {}).get("section_phrase_spans", []) or []),
            )
            run_rows.append(
                {
                    "emotion": str(emotion),
                    "run_index": int(run_idx),
                    "seed": int(seed),
                    "events": int(eval_metrics.total_events),
                    "notes": int(key_metrics["note_count"]),
                    "total_bars": int(composition_metrics["total_bars"]),
                    "in_key_ratio": float(key_metrics["in_key_ratio"]),
                    "in_key_primary_ratio": float(key_metrics["in_key_primary_ratio"]),
                    "lead_min3_pct": float(lead_tone["lead_min3_pct"]),
                    "lead_maj3_pct": float(lead_tone["lead_maj3_pct"]),
                    "lead_off_scale_pct": float(lead_tone["lead_off_scale_pct"]),
                    "lead_activity": float(eval_metrics.lead_activity),
                    "arp_activity": float(eval_metrics.arp_activity),
                    "lead_arp_overlap": float(eval_metrics.lead_arp_overlap),
                    "lead_pitch_min": int(composition_metrics["lead_pitch_min"]),
                    "lead_pitch_max": int(composition_metrics["lead_pitch_max"]),
                    "lead_pitch_range": int(eval_metrics.lead_pitch_range),
                    "lead_pitch_median": float(composition_metrics["lead_pitch_median"]),
                    "lead_pitch_p95": float(composition_metrics["lead_pitch_p95"]),
                    "lead_ceiling_hit_frac": float(composition_metrics["lead_ceiling_hit_frac"]),
                    "lead_top_band_frac": float(composition_metrics["lead_top_band_frac"]),
                    "lead_top_pitch_frac": float(composition_metrics["lead_top_pitch_frac"]),
                    "lead_repeat_frac": float(eval_metrics.lead_repeat_frac),
                    "lead_abs_interval_p95": float(eval_metrics.lead_abs_interval_p95),
                    "lead_max_leap": int(eval_metrics.lead_max_leap),
                    "chord_change_rate_per_bar": float(eval_metrics.chord_change_rate_per_bar),
                    "mh_onset_chord_tone_frac": float(harmony_metrics["mh_onset_chord_tone_frac"]),
                    "mh_strongbeat_chord_tone_frac": float(harmony_metrics["mh_strongbeat_chord_tone_frac"]),
                    "mh_phrase_end_chord_tone_frac": float(harmony_metrics["mh_phrase_end_chord_tone_frac"]),
                    "unique_section_roots": int(composition_metrics["unique_section_roots"]),
                    "unique_section_emotions": int(composition_metrics["unique_section_emotions"]),
                    "counter_melody_events": int(composition_metrics["counter_melody_events"]),
                    "counter_melody_events_per_bar": float(composition_metrics["counter_melody_events_per_bar"]),
                }
            )
            hook_features = hook_development_features(rows, run_rows[-1])
            run_rows[-1].update({k: float(v) for k, v in hook_features.items()})
            run_rows[-1]["professional_quality_score"] = float(professional_quality_score(run_rows[-1]))
            match_features = emotion_match_features(rows, run_rows[-1])
            match = emotion_match_score(str(emotion), match_features)
            run_rows[-1].update({k: float(v) if isinstance(v, (int, float)) else v for k, v in match.items()})
            run_rows[-1].update({f"emotion_match_feature_{k}": float(v) for k, v in match_features.items()})
            print(f"generated emotion={emotion} run={run_idx+1}/{int(args.runs_per_emotion)} seed={seed} notes={int(key_metrics['note_count'])} in_key={_fmt(key_metrics['in_key_ratio'])}")

    # Rank seeds within each emotion by descending quality score.
    rows_by_emotion: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for rr in run_rows:
        rows_by_emotion[str(rr["emotion"])].append(rr)
    for _emotion, rows in rows_by_emotion.items():
        ranked = sorted(rows, key=lambda x: float(x.get("professional_quality_score", 0.0)), reverse=True)
        for rank_idx, row in enumerate(ranked, start=1):
            row["seed_rank_in_emotion"] = int(rank_idx)

    note_headers = [
        "emotion",
        "run_index",
        "seed",
        "channel",
        "channel_name",
        "start_beats",
        "duration_beats",
        "velocity",
        "midi",
        "note",
        "pc",
        "in_key",
        "in_key_primary",
        "section_index",
        "section_role",
        "section_emotion",
        "section_root_midi",
    ]
    run_headers = [
        "emotion",
        "run_index",
        "seed",
        "events",
        "notes",
        "total_bars",
        "in_key_ratio",
        "in_key_primary_ratio",
        "lead_min3_pct",
        "lead_maj3_pct",
        "lead_off_scale_pct",
        "lead_activity",
        "arp_activity",
        "lead_arp_overlap",
        "lead_pitch_min",
        "lead_pitch_max",
        "lead_pitch_range",
        "lead_pitch_median",
        "lead_pitch_p95",
        "lead_ceiling_hit_frac",
        "lead_top_band_frac",
        "lead_top_pitch_frac",
        "lead_repeat_frac",
        "lead_abs_interval_p95",
        "lead_max_leap",
        "chord_change_rate_per_bar",
        "mh_onset_chord_tone_frac",
        "mh_strongbeat_chord_tone_frac",
        "mh_phrase_end_chord_tone_frac",
        "unique_section_roots",
        "unique_section_emotions",
        "counter_melody_events",
        "counter_melody_events_per_bar",
        "hook_identity_score",
        "chorus_payoff_score",
        "motif_development_score",
        "professional_quality_score",
        "emotion_match_score",
        "emotion_match_weakest",
        "emotion_match_density_fit",
        "emotion_match_register_fit",
        "emotion_match_motion_fit",
        "emotion_match_overlap_fit",
        "emotion_match_descent_fit",
        "emotion_match_leap_fit",
        "emotion_match_counter_fit",
        "emotion_match_feature_density",
        "emotion_match_feature_register",
        "emotion_match_feature_motion",
        "emotion_match_feature_overlap",
        "emotion_match_feature_descent",
        "emotion_match_feature_leap",
        "emotion_match_feature_counter",
        "seed_rank_in_emotion",
    ]
    write_csv(out_dir / "all_notes.csv", note_rows, note_headers)
    write_csv(out_dir / "run_summary.csv", run_rows, run_headers)

    section_headers = [
        "emotion",
        "run_index",
        "seed",
        "section_index",
        "section_role",
        "section_emotion",
        "section_bars",
        "lead_note_count",
        "lead_onset_count",
        "lead_notes_per_bar",
        "lead_onsets_per_bar",
        "lead_beats_per_bar",
        "lead_coverage_ratio",
        "lead_register_median",
        "lead_velocity_avg",
        "arp_note_count",
        "arp_onset_count",
        "arp_notes_per_bar",
        "arp_onsets_per_bar",
        "arp_beats_per_bar",
        "arp_register_median",
        "arp_velocity_avg",
        "chord_change_rate_per_bar",
        "texture_channel_count",
        "texture_signature",
    ]
    role_summary_rows = summarize_section_roles(section_rows)
    role_summary_headers = [
        "emotion",
        "section_role",
        "sections",
        "lead_notes_per_bar_avg",
        "lead_onsets_per_bar_avg",
        "lead_beats_per_bar_avg",
        "lead_coverage_ratio_avg",
        "lead_register_median_avg",
        "lead_velocity_avg_avg",
        "arp_notes_per_bar_avg",
        "arp_onsets_per_bar_avg",
        "arp_beats_per_bar_avg",
        "arp_register_median_avg",
        "arp_velocity_avg_avg",
        "chord_change_rate_per_bar_avg",
        "texture_channel_count_avg",
        "texture_signature_count",
    ]
    contrast_rows = summarize_arrangement_contrast(role_summary_rows)
    contrast_headers = [
        "emotion",
        "verse_to_chorus_lead_notes_per_bar_delta",
        "verse_to_chorus_lead_beats_per_bar_delta",
        "verse_to_chorus_lead_coverage_delta",
        "verse_to_chorus_arp_notes_per_bar_delta",
        "verse_to_chorus_lead_register_delta",
        "intro_to_chorus_lead_velocity_delta",
        "tension_arc",
        "intro_chorus_velocity_arc_fit",
        "pre_to_chorus_chord_motion_delta",
        "chorus_to_outro_lead_notes_per_bar_delta",
        "texture_channel_span",
        "contrast_issue_count",
        "weak_contrast_flags",
        "arrangement_contrast_score",
    ]
    write_csv(out_dir / "section_summary.csv", section_rows, section_headers)
    write_csv(out_dir / "emotion_section_summary.csv", role_summary_rows, role_summary_headers)
    write_csv(out_dir / "arrangement_contrast_summary.csv", contrast_rows, contrast_headers)

    by_emotion: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in run_rows:
        by_emotion[str(row["emotion"])].append(row)

    emotion_summary_rows: List[Dict[str, Any]] = []
    for emotion in sorted(by_emotion.keys()):
        rows = by_emotion[emotion]

        def avg(k: str) -> float:
            xs = [float(r[k]) for r in rows]
            return float(sum(xs) / max(1, len(xs)))

        def stdev(k: str) -> float:
            xs = [float(r[k]) for r in rows]
            return float(statistics.pstdev(xs)) if len(xs) > 1 else 0.0

        emotion_summary_rows.append(
            {
                "emotion": emotion,
                "runs": int(len(rows)),
                "in_key_ratio_avg": avg("in_key_ratio"),
                "in_key_ratio_std": stdev("in_key_ratio"),
                "lead_activity_avg": avg("lead_activity"),
                "arp_activity_avg": avg("arp_activity"),
                "lead_arp_overlap_avg": avg("lead_arp_overlap"),
                "lead_ceiling_hit_frac_avg": avg("lead_ceiling_hit_frac"),
                "lead_top_band_frac_avg": avg("lead_top_band_frac"),
                "lead_top_pitch_frac_avg": avg("lead_top_pitch_frac"),
                "lead_abs_interval_p95_avg": avg("lead_abs_interval_p95"),
                "lead_repeat_frac_avg": avg("lead_repeat_frac"),
                "chord_change_rate_avg": avg("chord_change_rate_per_bar"),
                "mh_onset_chord_tone_frac_avg": avg("mh_onset_chord_tone_frac"),
                "mh_strongbeat_chord_tone_frac_avg": avg("mh_strongbeat_chord_tone_frac"),
                "mh_phrase_end_chord_tone_frac_avg": avg("mh_phrase_end_chord_tone_frac"),
                "unique_section_roots_avg": avg("unique_section_roots"),
                "unique_section_emotions_avg": avg("unique_section_emotions"),
                "counter_melody_events_per_bar_avg": avg("counter_melody_events_per_bar"),
                "hook_identity_score_avg": avg("hook_identity_score"),
                "chorus_payoff_score_avg": avg("chorus_payoff_score"),
                "motif_development_score_avg": avg("motif_development_score"),
                "professional_quality_score_avg": avg("professional_quality_score"),
                "professional_quality_score_std": stdev("professional_quality_score"),
                "emotion_match_score_avg": avg("emotion_match_score"),
                "emotion_match_score_std": stdev("emotion_match_score"),
            }
        )

    emotion_headers = [
        "emotion",
        "runs",
        "in_key_ratio_avg",
        "in_key_ratio_std",
        "lead_activity_avg",
        "arp_activity_avg",
        "lead_arp_overlap_avg",
        "lead_ceiling_hit_frac_avg",
        "lead_top_band_frac_avg",
        "lead_top_pitch_frac_avg",
        "lead_abs_interval_p95_avg",
        "lead_repeat_frac_avg",
        "chord_change_rate_avg",
        "mh_onset_chord_tone_frac_avg",
        "mh_strongbeat_chord_tone_frac_avg",
        "mh_phrase_end_chord_tone_frac_avg",
        "unique_section_roots_avg",
        "unique_section_emotions_avg",
        "counter_melody_events_per_bar_avg",
        "hook_identity_score_avg",
        "chorus_payoff_score_avg",
        "motif_development_score_avg",
        "professional_quality_score_avg",
        "professional_quality_score_std",
        "emotion_match_score_avg",
        "emotion_match_score_std",
    ]
    write_csv(out_dir / "emotion_summary.csv", emotion_summary_rows, emotion_headers)

    emotion_match_rows: List[Dict[str, Any]] = []
    for emotion in sorted(by_emotion.keys()):
        rows = by_emotion[emotion]

        def avg2(k: str) -> float:
            xs = [float(r.get(k, 0.0)) for r in rows]
            return float(sum(xs) / max(1, len(xs)))

        weak_counts: Dict[str, int] = defaultdict(int)
        for row in rows:
            for item in str(row.get("emotion_match_weakest", "")).split(";"):
                key = item.split(":", 1)[0].strip()
                if key:
                    weak_counts[key] += 1
        weakest = ";".join(f"{k}:{v}" for k, v in sorted(weak_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:4])
        emotion_match_rows.append(
            {
                "emotion": emotion,
                "runs": int(len(rows)),
                "emotion_match_score_avg": avg2("emotion_match_score"),
                "density_fit_avg": avg2("emotion_match_density_fit"),
                "register_fit_avg": avg2("emotion_match_register_fit"),
                "motion_fit_avg": avg2("emotion_match_motion_fit"),
                "overlap_fit_avg": avg2("emotion_match_overlap_fit"),
                "descent_fit_avg": avg2("emotion_match_descent_fit"),
                "leap_fit_avg": avg2("emotion_match_leap_fit"),
                "counter_fit_avg": avg2("emotion_match_counter_fit"),
                "density_value_avg": avg2("emotion_match_feature_density"),
                "register_value_avg": avg2("emotion_match_feature_register"),
                "motion_value_avg": avg2("emotion_match_feature_motion"),
                "overlap_value_avg": avg2("emotion_match_feature_overlap"),
                "descent_value_avg": avg2("emotion_match_feature_descent"),
                "leap_value_avg": avg2("emotion_match_feature_leap"),
                "counter_value_avg": avg2("emotion_match_feature_counter"),
                "common_weak_dimensions": weakest,
            }
        )
    emotion_match_headers = [
        "emotion",
        "runs",
        "emotion_match_score_avg",
        "density_fit_avg",
        "register_fit_avg",
        "motion_fit_avg",
        "overlap_fit_avg",
        "descent_fit_avg",
        "leap_fit_avg",
        "counter_fit_avg",
        "density_value_avg",
        "register_value_avg",
        "motion_value_avg",
        "overlap_value_avg",
        "descent_value_avg",
        "leap_value_avg",
        "counter_value_avg",
        "common_weak_dimensions",
    ]
    write_csv(out_dir / "emotion_match_summary.csv", emotion_match_rows, emotion_match_headers)

    lines = [
        "# Full Song Seed Audit",
        "",
        f"- Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Emotions: {len(emotions)}",
        f"- Runs per emotion: {int(args.runs_per_emotion)}",
        f"- Seed mode: {'random' if bool(args.random_seeds) else 'sequential'}",
        f"- Form: {args.form}",
        f"- Bars per section input: {int(args.bars)}",
        f"- Root MIDI: {int(args.root)}",
        "",
        "## Key Metrics",
        "- `in_key_ratio`: fraction of all generated notes that fit the active section key/scale.",
        "- `lead_abs_interval_p95`: 95th percentile melody leap size (semitones).",
        "- `lead_ceiling_hit_frac`: fraction of lead notes at the song's top realized pitch; high values indicate range-limit pileups.",
        "- `lead_top_band_frac`: fraction of lead notes within two semitones of the song's top realized pitch.",
        "- `lead_repeat_frac`: adjacent repeated melody notes ratio.",
        "- `lead_arp_overlap`: lead time overlapped by arp (too high can mask topline).",
        "- `unique_section_roots` / `unique_section_emotions`: section-level harmonic and emotional arc variety.",
        "- `counter_melody_events_per_bar`: counterline participation; near zero means the layer is effectively unused.",
        "- `mh_strongbeat_chord_tone_frac`: fraction of strong-beat melody onsets that land on active chord tones.",
        "- `mh_phrase_end_chord_tone_frac`: fraction of phrase-ending melody landings that land on active chord tones.",
        "- `professional_quality_score`: composite score (0..100) for seed ranking; higher is better.",
        "- `emotion_match_score`: heuristic score (0..100) for whether measurable traits fit the requested emotion/adjective.",
        "",
        "## Files",
        "- `all_notes.csv`: every generated note across all runs.",
        "- `run_summary.csv`: per-song metrics and seed.",
        "- `emotion_summary.csv`: average and variance per emotion.",
        "- `section_summary.csv`: per-section density, register, velocity, harmony, and texture metrics.",
        "- `emotion_section_summary.csv`: section-role averages per emotion.",
        "- `arrangement_contrast_summary.csv`: verse/pre/chorus/outro contrast deltas per emotion.",
        "- `emotion_match_summary.csv`: adjective-fit score and weakest emotional dimensions per emotion.",
        "",
        "## Top Seeds Per Emotion",
        "",
    ]
    for emotion in sorted(rows_by_emotion.keys()):
        top = sorted(
            rows_by_emotion[emotion],
            key=lambda x: float(x.get("professional_quality_score", 0.0)),
            reverse=True,
        )[:3]
        lines.append(f"### {emotion}")
        lines.append("seed,score,in_key,strongbeat_ct,phrase_end_ct,lead_p95,ceiling,top_band,repeat,overlap,roots,arc")
        for row in top:
            lines.append(
                f"{int(row['seed'])},{_fmt(float(row['professional_quality_score']))},"
                f"{_fmt(float(row['in_key_ratio']))},{_fmt(float(row['mh_strongbeat_chord_tone_frac']))},"
                f"{_fmt(float(row['mh_phrase_end_chord_tone_frac']))},{_fmt(float(row['lead_abs_interval_p95']))},"
                f"{_fmt(float(row['lead_ceiling_hit_frac']))},{_fmt(float(row['lead_top_band_frac']))},"
                f"{_fmt(float(row['lead_repeat_frac']))},{_fmt(float(row['lead_arp_overlap']))},"
                f"{int(row['unique_section_roots'])},{int(row['unique_section_emotions'])}"
            )
        lines.append("")

    lines.extend(
        [
        "## Emotion Summary",
        "",
        ]
    )
    lines.append(
        "emotion,runs,in_key_ratio_avg,in_key_ratio_std,lead_abs_interval_p95_avg,"
        "lead_ceiling_hit_frac_avg,lead_top_band_frac_avg,lead_top_pitch_frac_avg,"
        "lead_repeat_frac_avg,lead_arp_overlap_avg,mh_onset_chord_tone_frac_avg,"
        "mh_strongbeat_chord_tone_frac_avg,mh_phrase_end_chord_tone_frac_avg,"
        "unique_section_roots_avg,unique_section_emotions_avg,counter_melody_events_per_bar_avg,"
        "professional_quality_score_avg,professional_quality_score_std"
        ",emotion_match_score_avg,emotion_match_score_std"
    )
    for row in sorted(emotion_summary_rows, key=lambda r: str(r["emotion"])):
        lines.append(
            f"{row['emotion']},{int(row['runs'])},{_fmt(float(row['in_key_ratio_avg']))},{_fmt(float(row['in_key_ratio_std']))},"
            f"{_fmt(float(row['lead_abs_interval_p95_avg']))},"
            f"{_fmt(float(row['lead_ceiling_hit_frac_avg']))},{_fmt(float(row['lead_top_band_frac_avg']))},"
            f"{_fmt(float(row['lead_top_pitch_frac_avg']))},{_fmt(float(row['lead_repeat_frac_avg']))},{_fmt(float(row['lead_arp_overlap_avg']))},"
            f"{_fmt(float(row['mh_onset_chord_tone_frac_avg']))},{_fmt(float(row['mh_strongbeat_chord_tone_frac_avg']))},"
            f"{_fmt(float(row['mh_phrase_end_chord_tone_frac_avg']))},"
            f"{_fmt(float(row['unique_section_roots_avg']))},{_fmt(float(row['unique_section_emotions_avg']))},"
            f"{_fmt(float(row['counter_melody_events_per_bar_avg']))},"
            f"{_fmt(float(row['professional_quality_score_avg']))},{_fmt(float(row['professional_quality_score_std']))}"
            f",{_fmt(float(row['emotion_match_score_avg']))},{_fmt(float(row['emotion_match_score_std']))}"
        )

    lines.extend(
        [
            "",
            "## Emotion Match Summary",
            "",
            "emotion,match_score,density_fit,register_fit,motion_fit,overlap_fit,descent_fit,leap_fit,counter_fit,weak_dimensions",
        ]
    )
    for row in sorted(emotion_match_rows, key=lambda r: float(r["emotion_match_score_avg"])):
        lines.append(
            f"{row['emotion']},{_fmt(float(row['emotion_match_score_avg']))},"
            f"{_fmt(float(row['density_fit_avg']))},{_fmt(float(row['register_fit_avg']))},"
            f"{_fmt(float(row['motion_fit_avg']))},{_fmt(float(row['overlap_fit_avg']))},"
            f"{_fmt(float(row['descent_fit_avg']))},{_fmt(float(row['leap_fit_avg']))},"
            f"{_fmt(float(row['counter_fit_avg']))},{row['common_weak_dimensions']}"
        )

    lines.extend(
        [
            "",
            "## Arrangement Contrast",
            "",
            "emotion,lead_density_delta,arp_density_delta,lead_register_delta,lead_velocity_delta,"
            "lead_beats_delta,lead_coverage_delta,chord_motion_delta,chorus_outro_density_delta,"
            "texture_span,issue_count,weak_flags,contrast_score",
        ]
    )
    for row in sorted(contrast_rows, key=lambda r: float(r["arrangement_contrast_score"])):
        lines.append(
            f"{row['emotion']},{_fmt(float(row['verse_to_chorus_lead_notes_per_bar_delta']))},"
            f"{_fmt(float(row['verse_to_chorus_arp_notes_per_bar_delta']))},"
            f"{_fmt(float(row['verse_to_chorus_lead_register_delta']))},"
            f"{_fmt(float(row['intro_to_chorus_lead_velocity_delta']))},"
            f"{_fmt(float(row['verse_to_chorus_lead_beats_per_bar_delta']))},"
            f"{_fmt(float(row['verse_to_chorus_lead_coverage_delta']))},"
            f"{_fmt(float(row['pre_to_chorus_chord_motion_delta']))},"
            f"{_fmt(float(row['chorus_to_outro_lead_notes_per_bar_delta']))},"
            f"{_fmt(float(row['texture_channel_span']))},"
            f"{int(row['contrast_issue_count'])},"
            f"{row['weak_contrast_flags']},"
            f"{_fmt(float(row['arrangement_contrast_score']))}"
        )

    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
