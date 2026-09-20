# composition/section_planner/motif_bus.py
"""Cross-lane motif summary from lead melody events (hook / recall plumbing)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def cross_lane_motif_bus_from_melody(
    melody_events: List[Tuple],
    *,
    bars: int,
    beats_per_bar: float,
    section_role: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not melody_events or bars <= 0 or beats_per_bar <= 1e-9:
        return None
    role = str(section_role or "").strip().lower()
    cand_bars = [0, 1, 2] if role in {"intro"} else [0, 1]
    lead_by_bar: Dict[int, List[Tuple[float, float, int]]] = {}
    for ev in list(melody_events or []):
        try:
            if not (isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == 2):
                continue
            st = float(ev[3])
            dur = float(ev[4])
            if dur <= 1e-9:
                continue
            bar = int(st // float(beats_per_bar))
            if bar < 0 or bar >= int(bars):
                continue
            midi = int(ev[5][0]) if isinstance(ev[5], list) and ev[5] else int(ev[1])
            lead_by_bar.setdefault(int(bar), []).append((st, dur, midi))
        except Exception:
            continue
    src_bar = None
    for b in list(cand_bars):
        if b in lead_by_bar and len(list(lead_by_bar.get(b) or [])) >= 2:
            src_bar = int(b)
            break
    if src_bar is None:
        if not lead_by_bar:
            return None
        src_bar = max(lead_by_bar.keys(), key=lambda k: len(lead_by_bar.get(k) or []))
    seq = sorted(list(lead_by_bar.get(int(src_bar), []) or []), key=lambda x: float(x[0]))
    if len(seq) < 2:
        return None
    bar_end = float(src_bar + 1) * float(beats_per_bar)
    mids: List[int] = []
    rh: List[float] = []
    for st, dur, midi in seq:
        if st >= bar_end - 1e-6:
            break
        dur_c = max(0.125, min(float(dur), bar_end - float(st)))
        mids.append(int(midi))
        allowed = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0)
        qd = min(allowed, key=lambda a: abs(float(a) - float(dur_c)))
        rh.append(float(qd))
        if sum(float(x) for x in rh) >= float(beats_per_bar) - 1e-6:
            break
    if len(mids) < 2 or len(rh) < 2:
        return None
    rsum = float(sum(rh))
    if rsum > 1e-9:
        tail = max(0.25, min(4.0, float(beats_per_bar) - (rsum - float(rh[-1]))))
        rh[-1] = float(min((0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0), key=lambda a: abs(float(a) - tail)))
    intervals: List[int] = []
    for i in range(1, len(mids)):
        d = int(mids[i]) - int(mids[i - 1])
        if d > 12:
            d -= 12
        if d < -12:
            d += 12
        intervals.append(int(max(-7, min(7, d // 2 if abs(d) > 1 else d))))
    if not intervals:
        intervals = [0]
    contour = "static"
    if sum(int(v) for v in intervals) >= 2:
        contour = "asc"
    elif sum(int(v) for v in intervals) <= -2:
        contour = "desc"
    elif any(int(v) > 0 for v in intervals) and any(int(v) < 0 for v in intervals):
        contour = "arch"
    return {
        "intervals": [int(v) for v in intervals],
        "rhythms": [float(v) for v in rh],
        "contour": str(contour),
        "source_bar": int(src_bar),
    }


def motif_hook_from_cross_lane_bus(bus: Optional[Dict[str, Any]]):
    if not isinstance(bus, dict):
        return None
    try:
        from composition.motif_plan import SongHookMotif

        iv = [int(v) for v in list(bus.get("intervals", []) or [])]
        rh = [float(v) for v in list(bus.get("rhythms", []) or [])]
        contour = str(bus.get("contour", "") or "")
        if len(iv) >= 1 and len(rh) >= 2:
            return SongHookMotif(intervals=list(iv), rhythms=list(rh), contour=str(contour))
    except Exception:
        return None
    return None
