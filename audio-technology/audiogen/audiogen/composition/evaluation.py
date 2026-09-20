from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from composition.event_utils import (
    occupancy_by_bar as _occ_by_bar_shared,
    overlap_fraction as _overlap_frac_shared,
    p95 as _p95,
    union_occupied as _union_occupied,
)


@dataclass(frozen=True)
class SongMetrics:
    total_events: int
    events_per_channel: Dict[int, int]
    lead_activity: float
    counter_activity: float
    chord_change_rate_per_bar: float
    # Extra quality signals (lead-focused).
    lead_pitch_range: int
    lead_repeat_frac: float
    # Density / masking signals.
    arp_activity: float
    lead_arp_overlap: float
    lead_counter_overlap: float
    chord_repeat_frac: float
    # Harshness / jumpiness signals.
    lead_abs_interval_p95: float = 0.0
    lead_max_leap: int = 0
    chord_center_jump_p95: float = 0.0
    activity_jump_p95: float = 0.0
    velocity_jump_p95: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_events": int(self.total_events),
            "events_per_channel": {int(k): int(v) for k, v in self.events_per_channel.items()},
            "lead_activity": float(self.lead_activity),
            "counter_activity": float(self.counter_activity),
            "chord_change_rate_per_bar": float(self.chord_change_rate_per_bar),
            "lead_pitch_range": int(self.lead_pitch_range),
            "lead_repeat_frac": float(self.lead_repeat_frac),
            "arp_activity": float(self.arp_activity),
            "lead_arp_overlap": float(self.lead_arp_overlap),
            "lead_counter_overlap": float(self.lead_counter_overlap),
            "chord_repeat_frac": float(self.chord_repeat_frac),
            "lead_abs_interval_p95": float(self.lead_abs_interval_p95),
            "lead_max_leap": int(self.lead_max_leap),
            "chord_center_jump_p95": float(self.chord_center_jump_p95),
            "activity_jump_p95": float(self.activity_jump_p95),
            "velocity_jump_p95": float(self.velocity_jump_p95),
        }


def evaluate_song(
    events: Sequence[Sequence[Any]],
    *,
    beats_per_bar: float = 4.0,
    bars: Optional[int] = None,
) -> SongMetrics:
    """
    Lightweight, dependency-free metrics for regression tracking and rerank hooks.

    Expects events in 6-tuple shape: (channel, midi, velocity, start_beats, duration_beats, notes).
    """
    total = 0
    per_ch: Dict[int, int] = {}
    lead_intervals: List[Tuple[float, float]] = []
    counter_intervals: List[Tuple[float, float]] = []
    arp_intervals: List[Tuple[float, float]] = []
    chord_starts: List[float] = []
    chord_shapes: List[Tuple[int, ...]] = []
    lead_pitches: List[int] = []
    lead_vel_by_bar: Dict[int, List[int]] = {}
    chord_vel_by_bar: Dict[int, List[int]] = {}
    arp_vel_by_bar: Dict[int, List[int]] = {}
    max_beat = 0.0

    for ev in events:
        if not ev or len(ev) != 6:
            continue
        ch = int(ev[0])
        st = float(ev[3])
        dur = float(ev[4])
        en = st + max(0.0, dur)
        max_beat = max(max_beat, en)
        total += 1
        per_ch[ch] = per_ch.get(ch, 0) + 1
        bar = int(float(st) // max(1e-6, float(beats_per_bar) if beats_per_bar else 4.0))
        if ch == 2 and dur > 0:
            lead_intervals.append((st, en))
            try:
                notes = ev[5]
                if notes and isinstance(notes, list):
                    lead_pitches.append(int(notes[0]))
            except Exception:
                pass
            try:
                lead_vel_by_bar.setdefault(int(bar), []).append(int(ev[2]))
            except Exception:
                pass
        elif ch == 5 and dur > 0:
            counter_intervals.append((st, en))
        elif ch == 3 and dur > 0:
            arp_intervals.append((st, en))
            try:
                arp_vel_by_bar.setdefault(int(bar), []).append(int(ev[2]))
            except Exception:
                pass
        elif ch == 1:
            chord_starts.append(st)
            try:
                notes = ev[5]
                if notes and isinstance(notes, list):
                    chord_shapes.append(tuple(int(n) for n in notes if isinstance(n, int)))
            except Exception:
                pass
            try:
                chord_vel_by_bar.setdefault(int(bar), []).append(int(ev[2]))
            except Exception:
                pass

    bpb = float(beats_per_bar) if beats_per_bar else 4.0
    if bars is None:
        bars = int(max(1.0, max_beat / max(1e-6, bpb) + 1e-9))

    total_beats = float(bars) * bpb
    lead_occ = _union_occupied([(max(0.0, s), min(total_beats, e)) for s, e in lead_intervals])
    counter_occ = _union_occupied([(max(0.0, s), min(total_beats, e)) for s, e in counter_intervals])
    arp_occ = _union_occupied([(max(0.0, s), min(total_beats, e)) for s, e in arp_intervals])

    # Overlap (masking proxy): fraction of lead time covered by other layers.
    lead_arp_overlap = _overlap_frac_shared(lead_intervals, arp_intervals, total_beats)
    lead_counter_overlap = _overlap_frac_shared(lead_intervals, counter_intervals, total_beats)

    # Chord change rate: count distinct start beats on channel 1 per bar.
    chord_starts = sorted(float(s) for s in chord_starts if s >= -1e-9)
    unique_starts = []
    last = None
    for s in chord_starts:
        if last is None or abs(s - last) > 1e-6:
            unique_starts.append(s)
            last = s
    chord_changes = max(0, len(unique_starts))
    rate = chord_changes / max(1, int(bars))

    # Lead range + repetition.
    lead_pitch_range = (max(lead_pitches) - min(lead_pitches)) if lead_pitches else 0
    same_adj = 0
    if len(lead_pitches) >= 2:
        for a, b in zip(lead_pitches, lead_pitches[1:]):
            if int(a) == int(b):
                same_adj += 1
    lead_repeat_frac = float(same_adj / max(1, (len(lead_pitches) - 1))) if len(lead_pitches) >= 2 else 0.0

    # Lead leap harshness: adjacent absolute intervals.
    abs_ints: List[float] = []
    max_leap = 0
    if len(lead_pitches) >= 2:
        for a, b in zip(lead_pitches, lead_pitches[1:]):
            d = abs(int(b) - int(a))
            abs_ints.append(float(d))
            if d > max_leap:
                max_leap = int(d)
    lead_abs_interval_p95 = _p95(abs_ints)
    lead_max_leap = int(max_leap)

    # Chord repeat fraction: consecutive identical chord voicings on channel 1.
    chord_repeat = 0
    if len(chord_shapes) >= 2:
        for a, b in zip(chord_shapes, chord_shapes[1:]):
            if a == b:
                chord_repeat += 1
    chord_repeat_frac = float(chord_repeat / max(1, (len(chord_shapes) - 1))) if len(chord_shapes) >= 2 else 0.0

    # Chord center jumps: median note per chord-shape, then adjacent diffs.
    centers: List[int] = []
    for shp in chord_shapes:
        if not shp:
            continue
        ss = sorted(int(n) for n in shp)
        centers.append(int(ss[len(ss) // 2]))
    ch_jumps = [float(abs(int(b) - int(a))) for a, b in zip(centers, centers[1:])] if len(centers) >= 2 else []
    chord_center_jump_p95 = _p95(ch_jumps)

    # Per-bar activity jumpiness: compute occupancy per bar (lead+arp+counter) then p95 of first differences.
    occ = _occ_by_bar_shared(lead_intervals, bpb)
    occ2 = _occ_by_bar_shared(arp_intervals, bpb)
    occ3 = _occ_by_bar_shared(counter_intervals, bpb)
    act_by_bar: List[float] = []
    for b in range(int(bars)):
        v = float(occ.get(b, 0.0) + occ2.get(b, 0.0) + occ3.get(b, 0.0)) / float(bpb)
        act_by_bar.append(v)
    act_jumps = [abs(float(b) - float(a)) for a, b in zip(act_by_bar, act_by_bar[1:])] if len(act_by_bar) >= 2 else []
    activity_jump_p95 = _p95(act_jumps)

    # Per-bar velocity jumpiness: mean vel over (lead+arp+chords), then p95 of ratios.
    def _mean_vel(d: Dict[int, List[int]], b: int) -> Optional[float]:
        xs = d.get(int(b)) or []
        if not xs:
            return None
        return float(sum(int(x) for x in xs) / max(1, len(xs)))

    vel_series: List[float] = []
    for b in range(int(bars)):
        vals = []
        for d in (lead_vel_by_bar, arp_vel_by_bar, chord_vel_by_bar):
            mv = _mean_vel(d, b)
            if mv is not None:
                vals.append(float(mv))
        vel_series.append(float(sum(vals) / max(1, len(vals))) if vals else 0.0)
    vel_jumps = [abs(float(b) - float(a)) for a, b in zip(vel_series, vel_series[1:])] if len(vel_series) >= 2 else []
    velocity_jump_p95 = _p95(vel_jumps)

    return SongMetrics(
        total_events=int(total),
        events_per_channel=per_ch,
        lead_activity=float(lead_occ / total_beats) if total_beats > 0 else 0.0,
        counter_activity=float(counter_occ / total_beats) if total_beats > 0 else 0.0,
        chord_change_rate_per_bar=float(rate),
        lead_pitch_range=int(lead_pitch_range),
        lead_repeat_frac=float(lead_repeat_frac),
        arp_activity=float(arp_occ / total_beats) if total_beats > 0 else 0.0,
        lead_arp_overlap=float(lead_arp_overlap),
        lead_counter_overlap=float(lead_counter_overlap),
        chord_repeat_frac=float(chord_repeat_frac),
        lead_abs_interval_p95=float(lead_abs_interval_p95),
        lead_max_leap=int(lead_max_leap),
        chord_center_jump_p95=float(chord_center_jump_p95),
        activity_jump_p95=float(activity_jump_p95),
        velocity_jump_p95=float(velocity_jump_p95),
    )


def score_song(
    events: Sequence[Sequence[Any]],
    *,
    beats_per_bar: float = 4.0,
    bars: Optional[int] = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    Return (score, details). Higher is better.
    """
    m = evaluate_song(events, beats_per_bar=beats_per_bar, bars=bars)
    score = 0.0

    # Core: want clear, present lead.
    score += 1.25 * float(m.lead_activity)
    # Harmony motion is good up to a point.
    score += 0.25 * float(m.chord_change_rate_per_bar)
    score -= 0.22 * max(0.0, float(m.chord_change_rate_per_bar) - 1.75)
    # Avoid stuck lead + too-narrow range.
    score -= 0.85 * max(0.0, float(m.lead_repeat_frac) - 0.18)
    score += 0.12 * min(24.0, float(m.lead_pitch_range)) / 24.0
    score -= 0.30 * max(0.0, (8.0 - float(m.lead_pitch_range)) / 8.0)
    # Masking penalties: arp/counter overlapping lead too much.
    score -= 0.55 * max(0.0, float(m.lead_arp_overlap) - 0.55)
    score -= 0.65 * max(0.0, float(m.lead_counter_overlap) - 0.48)
    # If arp is extremely dense, it usually muddies.
    score -= 0.18 * max(0.0, float(m.arp_activity) - 0.62)
    # Chord repetition (same voicing over and over) feels static.
    score -= 0.20 * max(0.0, float(m.chord_repeat_frac) - 0.55)
    # Counter should exist but not dominate.
    score -= 0.55 * max(0.0, float(m.counter_activity) - 0.32)
    # Harshness penalties: big melodic leaps, chord register jumps, jumpy density/dynamics.
    score -= 0.10 * max(0.0, float(m.lead_abs_interval_p95) - 7.0) / 7.0
    score -= 0.08 * max(0.0, float(m.lead_max_leap) - 12.0) / 12.0
    score -= 0.10 * max(0.0, float(m.chord_center_jump_p95) - 9.0) / 9.0
    score -= 0.20 * max(0.0, float(m.activity_jump_p95) - 0.55) / 0.55
    score -= 0.10 * max(0.0, float(m.velocity_jump_p95) - 9.0) / 9.0

    details = m.to_dict()
    details["score"] = float(score)
    return float(score), details


def quality_report(
    events: Sequence[Sequence[Any]],
    *,
    section_roles: Optional[Sequence[str]] = None,
    section_bars: Optional[Sequence[int]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    beats_per_bar: float = 4.0,
    bars: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Song-level musical QA signals for reports and future repair gates.

    This intentionally stays dependency-free and conservative: it does not judge
    style, only obvious identity/contrast/singability/static-risk signals.
    """
    metrics = evaluate_song(events, beats_per_bar=beats_per_bar, bars=bars)
    roles = [str(r or "") for r in list(section_roles or [])]
    sec_bars = [max(1, int(b)) for b in list(section_bars or [])]
    if roles and not sec_bars:
        sec_bars = [int(max(1, int((bars or len(roles)) / max(1, len(roles))))) for _ in roles]
    nsec = min(len(roles), len(sec_bars))
    bpb = float(beats_per_bar) if beats_per_bar else 4.0

    lead_counts = [0 for _ in range(nsec)]
    bass_pitches_by_section: List[set[int]] = [set() for _ in range(nsec)]
    windows: List[Tuple[float, float]] = []
    off = 0.0
    for i in range(nsec):
        span = float(sec_bars[i]) * bpb
        windows.append((float(off), float(off + span)))
        off += span

    for ev in events:
        if not ev or len(ev) != 6:
            continue
        try:
            ch = int(ev[0])
            st = float(ev[3])
        except Exception:
            continue
        sec_idx = None
        for i, (lo, hi) in enumerate(windows):
            if float(lo) - 1e-6 <= st < float(hi) - 1e-6:
                sec_idx = int(i)
                break
        if sec_idx is None:
            continue
        if ch == 2:
            lead_counts[sec_idx] += 1
        elif ch == 0:
            try:
                notes = ev[5]
                if isinstance(notes, list) and notes:
                    bass_pitches_by_section[sec_idx].add(int(notes[0]))
                else:
                    bass_pitches_by_section[sec_idx].add(int(ev[1]))
            except Exception:
                pass

    lead_notes_per_bar = [
        float(lead_counts[i] / max(1, int(sec_bars[i]))) for i in range(nsec)
    ]
    verse_vals = [
        lead_notes_per_bar[i]
        for i, r in enumerate(roles[:nsec])
        if str(r).lower() in {"a", "verse", "a_prime"}
    ]
    chorus_vals = [
        lead_notes_per_bar[i]
        for i, r in enumerate(roles[:nsec])
        if str(r).lower() in {"b", "chorus", "hook", "tag"}
    ]
    avg_verse = float(sum(verse_vals) / max(1, len(verse_vals))) if verse_vals else 0.0
    avg_chorus = float(sum(chorus_vals) / max(1, len(chorus_vals))) if chorus_vals else 0.0

    md = dict(metadata or {})
    motif_dev = list(md.get("motif_development", []) or [])
    chorus_motif_slots = 0
    chorus_statement_slots = 0
    for row in motif_dev:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role", "") or "").lower()
        if role not in {"b", "chorus", "hook", "tag"}:
            continue
        chorus_motif_slots += int(row.get("slot_count", 0) or 0)
        variants = row.get("variants", {}) or {}
        if isinstance(variants, dict):
            chorus_statement_slots += int(variants.get("statement", 0) or 0)

    bass_static_sections = []
    for i, r in enumerate(roles[:nsec]):
        if int(sec_bars[i]) < 2:
            continue
        if str(r).lower() in {"intro", "outro"}:
            continue
        unique_bass = len(bass_pitches_by_section[i])
        if unique_bass <= 1:
            bass_static_sections.append(int(i))

    checks = {
        "memorable_hook": bool(chorus_motif_slots > 0 and chorus_statement_slots > 0),
        "chorus_stronger_than_verse": bool((not chorus_vals or not verse_vals) or avg_chorus >= avg_verse * 0.90),
        "singable_lead_range": bool(5 <= int(metrics.lead_pitch_range) <= 24 and int(metrics.lead_max_leap) <= 14),
        "lead_not_too_empty": bool(float(metrics.lead_activity) >= 0.05 or sum(lead_counts) >= max(4, nsec * 2)),
        "bass_not_static": bool(not bass_static_sections),
    }
    recommendations: List[str] = []
    if not checks["memorable_hook"]:
        recommendations.append("add or strengthen chorus motif statement slots")
    if not checks["chorus_stronger_than_verse"]:
        recommendations.append("increase chorus lead density or reduce verse density")
    if not checks["singable_lead_range"]:
        recommendations.append("constrain lead range/leaps for singability")
    if not checks["lead_not_too_empty"]:
        recommendations.append("repair empty lead bars or raise phrase activity")
    if not checks["bass_not_static"]:
        recommendations.append("add stepwise bass motion in static core sections")

    passed = sum(1 for v in checks.values() if bool(v))
    total = max(1, len(checks))
    return {
        "schema_version": 1,
        "score": float(passed / total),
        "checks": checks,
        "recommendations": recommendations,
        "values": {
            "lead_pitch_range": int(metrics.lead_pitch_range),
            "lead_max_leap": int(metrics.lead_max_leap),
            "lead_activity": float(metrics.lead_activity),
            "avg_verse_lead_notes_per_bar": float(avg_verse),
            "avg_chorus_lead_notes_per_bar": float(avg_chorus),
            "chorus_motif_slots": int(chorus_motif_slots),
            "chorus_statement_slots": int(chorus_statement_slots),
            "bass_static_sections": list(bass_static_sections),
        },
    }
