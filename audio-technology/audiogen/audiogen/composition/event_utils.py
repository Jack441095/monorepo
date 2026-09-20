# composition/event_utils.py
# ---------------------------------------------------------------------------
# Shared, dependency-free event-processing utilities.
#
# These helpers operate on the standard 6-tuple event format:
#     (channel, midi, velocity, start_beats, duration_beats, notes)
#
# Keep this module lightweight and free of CONFIG / data imports so it can
# be imported safely from any layer (evaluation, postprocess, planner).
# ---------------------------------------------------------------------------
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

# Canonical type alias for a single composition event.
Event = Tuple[Any, Any, Any, Any, Any, Any]


# ── pitch extraction ────────────────────────────────────────────────────────

def pitch_from_event(ev: Sequence[Any]) -> Optional[int]:
    """Extract the first MIDI pitch from an event's ``notes`` list.

    Returns ``None`` if *ev* is malformed or has no integer notes.
    """
    if not ev or len(ev) != 6:
        return None
    try:
        notes = ev[5]
        if isinstance(notes, (list, tuple)) and notes and isinstance(notes[0], int):
            return int(notes[0])
        return int(ev[1]) if isinstance(ev[1], int) and int(ev[1]) > 0 else None
    except Exception:
        return None


def lead_pitch(ev: Sequence[Any]) -> Optional[int]:
    """Like :func:`pitch_from_event` but only for lead events (channel 2)."""
    if not ev or len(ev) != 6:
        return None
    try:
        if int(ev[0]) != 2:
            return None
    except Exception:
        return None
    return pitch_from_event(ev)


# ── statistics ──────────────────────────────────────────────────────────────

def median_int(values: Sequence[int]) -> int:
    """Integer median; returns 72 for empty inputs."""
    xs = sorted(int(v) for v in values)
    if not xs:
        return 72
    return int(xs[len(xs) // 2])


def p95(vals: Sequence[float]) -> float:
    """95th-percentile of *vals*; returns 0.0 for empty inputs."""
    if not vals:
        return 0.0
    xs = sorted(float(x) for x in vals)
    k = int(round(0.95 * (len(xs) - 1)))
    k = max(0, min(len(xs) - 1, k))
    return float(xs[k])


# ── interval / occupancy helpers ────────────────────────────────────────────

def union_occupied(intervals: Sequence[Tuple[float, float]]) -> float:
    """Total occupied time after merging overlapping ``(start, end)`` pairs."""
    items = [(float(s), float(e)) for s, e in intervals if float(e) > float(s)]
    if not items:
        return 0.0
    items.sort(key=lambda t: t[0])
    occ = 0.0
    cur_s, cur_e = items[0]
    for s, e in items[1:]:
        if s <= cur_e + 1e-9:
            cur_e = max(cur_e, e)
        else:
            occ += max(0.0, cur_e - cur_s)
            cur_s, cur_e = s, e
    occ += max(0.0, cur_e - cur_s)
    return occ


def overlap_fraction(
    a: Sequence[Tuple[float, float]],
    b: Sequence[Tuple[float, float]],
    total_beats: float,
) -> float:
    """Fraction of *a*'s occupied time that overlaps with *b*."""
    if not a:
        return 0.0
    a2 = [(max(0.0, float(s)), min(float(total_beats), float(e))) for s, e in a if float(e) > float(s)]
    b2 = [(max(0.0, float(s)), min(float(total_beats), float(e))) for s, e in b if float(e) > float(s)]
    if not a2 or not b2:
        return 0.0
    a2.sort()
    b2.sort()
    i = j = 0
    ov = 0.0
    while i < len(a2) and j < len(b2):
        s1, e1 = a2[i]
        s2, e2 = b2[j]
        s = max(s1, s2)
        e = min(e1, e2)
        if e > s:
            ov += (e - s)
        if e1 <= e2:
            i += 1
        else:
            j += 1
    denom = max(1e-9, union_occupied(a2))
    return float(ov / denom)


# ── event partitioning ──────────────────────────────────────────────────────

def events_by_section(
    events: Sequence[Event],
    section_bars: Sequence[int],
    beats_per_bar: float = 4.0,
) -> List[List[Tuple]]:
    """Partition *events* into per-section buckets by beat offset.

    Returns a list of lists, one per section.  Events are shallow-copied into
    the bucket whose beat-window they fall in.
    """
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    windows: List[Tuple[float, float]] = []
    off = 0.0
    for bars in section_bars:
        span = float(max(0, int(bars))) * bpb
        windows.append((float(off), float(off + span)))
        off += span

    buckets: List[List[Tuple]] = [[] for _ in windows]
    for ev in events:
        if not ev or len(ev) != 6:
            continue
        try:
            st = float(ev[3])
        except Exception:
            continue
        for idx, (lo, hi) in enumerate(windows):
            if lo - 1e-6 <= st < hi - 1e-6:
                buckets[idx].append(tuple(ev))
                break
    return buckets


def section_beat_offsets(
    section_bars: Sequence[int],
    beats_per_bar: float = 4.0,
) -> List[float]:
    """Return the starting beat of each section."""
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts: List[float] = []
    acc = 0.0
    for bars in section_bars:
        starts.append(float(acc))
        acc += float(max(0, int(bars))) * bpb
    return starts


# ── occupancy by bar ────────────────────────────────────────────────────────

def occupancy_by_bar(
    intervals: Sequence[Tuple[float, float]],
    beats_per_bar: float = 4.0,
) -> Dict[int, float]:
    """Return occupied time per bar index."""
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    out: Dict[int, float] = {}
    for s, e in intervals:
        if float(e) <= float(s):
            continue
        bs = int(float(s) // bpb)
        be = int(float(e - 1e-9) // bpb)
        for b in range(bs, be + 1):
            lo = float(b) * bpb
            hi = lo + bpb
            seg = max(0.0, min(float(e), hi) - max(float(s), lo))
            if seg > 0:
                out[int(b)] = float(out.get(int(b), 0.0) + seg)
    return out
