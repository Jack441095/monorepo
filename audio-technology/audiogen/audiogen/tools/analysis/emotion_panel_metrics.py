"""Shared metrics for in-memory full-song emotion panels and seed audits."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from composition.song_postprocess import _section_starts
from data.emotion_aliases import canonical_emotion_name
from data.emotion_scales import emotion_scale_pitch_classes


def section_timing(
    specs: Sequence[Any], *, beats_per_bar: float = 4.0
) -> Tuple[List[float], List[float], List[int], List[str]]:
    bars = [int(s.bars) for s in specs]
    roots = [int(s.root_note) for s in specs]
    emos = [str(s.emotion_name) for s in specs]
    starts = _section_starts(bars, beats_per_bar=float(beats_per_bar))
    ends = [float(starts[i]) + float(bars[i]) * float(beats_per_bar) for i in range(len(starts))]
    return starts, ends, roots, emos


def event_pitch(ev: Tuple) -> Optional[int]:
    try:
        notes = ev[5]
        if isinstance(notes, list) and notes:
            return int(notes[0])
    except Exception:
        pass
    try:
        return int(ev[1])
    except Exception:
        return None


def section_for_time(st: float, starts: Sequence[float], ends: Sequence[float]) -> int:
    for i in range(len(starts)):
        if float(starts[i]) - 1e-6 <= float(st) < float(ends[i]) - 1e-6:
            return int(i)
    return max(0, len(starts) - 1)


def lead_tonality_metrics(
    events: Sequence[Tuple],
    *,
    specs: Sequence[Any],
    primary_emotion: str,
    beats_per_bar: float = 4.0,
) -> Dict[str, float]:
    """Lead-only thirds (interval from section root) and off-scale vs primary scale."""
    starts, ends, roots, _ = section_timing(specs, beats_per_bar=beats_per_bar)
    primary = canonical_emotion_name(str(primary_emotion or ""))
    intervals: Counter = Counter()
    out_scale = 0
    total = 0

    for ev in list(events or []):
        if not (isinstance(ev, tuple) and len(ev) >= 2) or int(ev[0]) != 2:
            continue
        pitch = event_pitch(ev)
        if pitch is None:
            continue
        try:
            st = float(ev[3])
        except Exception:
            continue
        sec = section_for_time(st, starts, ends)
        root = int(roots[sec])
        iv = int(pitch - root) % 12
        intervals[iv] += 1
        total += 1
        scale = set(
            emotion_scale_pitch_classes(
                emotion_or_name=str(primary),
                root_note=int(root),
            )
        )
        if int(pitch) % 12 not in scale:
            out_scale += 1

    total = max(1, int(total))
    return {
        "lead_min3_pct": 100.0 * float(intervals.get(3, 0)) / float(total),
        "lead_maj3_pct": 100.0 * float(intervals.get(4, 0)) / float(total),
        "lead_off_scale_pct": 100.0 * float(out_scale) / float(total),
        "lead_notes": float(total),
    }


def non_chorus_arp_pct(
    events: Sequence[Tuple],
    *,
    specs: Sequence[Any],
    roles: Sequence[str],
    beats_per_bar: float = 4.0,
) -> float:
    starts, ends, _, _ = section_timing(specs, beats_per_bar=beats_per_bar)
    non_ch = 0
    total = 0
    for ev in list(events or []):
        if not (isinstance(ev, tuple) and len(ev) >= 4) or int(ev[0]) != 3:
            continue
        try:
            st = float(ev[3])
        except Exception:
            continue
        sec = section_for_time(st, starts, ends)
        role = str(roles[sec] if sec < len(roles) else "").strip().lower()
        total += 1
        if role not in {"b", "chorus", "hook", "tag"}:
            non_ch += 1
    return 100.0 * float(non_ch) / float(total or 1)
