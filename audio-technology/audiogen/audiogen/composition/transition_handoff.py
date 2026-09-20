# composition/transition_handoff.py
# ---------------------------------------------------------------------------
# Harmonic context from the outgoing timeline for smoother emotion transitions.
# ---------------------------------------------------------------------------
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _bar_snapshot(
    events: List[Tuple],
    *,
    bar_start: float,
    bar_end: float,
) -> Tuple[Optional[frozenset[int]], Optional[int], Optional[int], bool]:
    pcs: Optional[frozenset[int]] = None
    bass: Optional[int] = None
    lead: Optional[int] = None
    note_list: List[int] = []
    found_any = False
    for ev in events:
        if not ev or len(ev) < 6:
            continue
        ch, midi, _vel, start, dur, notes = ev
        st = float(start)
        en = st + float(dur)
        if en <= bar_start + 1e-6 or st >= bar_end - 1e-6:
            continue
        found_any = True
        ch = int(ch)
        if ch == 1:
            if notes:
                for n in notes:
                    if isinstance(n, (int, float)):
                        note_list.append(int(n) % 12)
            elif isinstance(midi, (int, float)) and int(midi) > 0:
                note_list.append(int(midi) % 12)
        if ch == 0 and bass is None:
            if isinstance(midi, (int, float)):
                bass = int(midi)
            elif notes and isinstance(notes[0], (int, float)):
                bass = int(notes[0])
        if ch == 2 and lead is None:
            if isinstance(midi, (int, float)):
                lead = int(midi)
            elif notes and isinstance(notes[0], (int, float)):
                lead = int(notes[0])
    if note_list:
        pcs = frozenset(note_list)
    return pcs, bass, lead, found_any


def _choose_pivot_strategy(
    *,
    last_pcs: Optional[frozenset[int]],
    prev_pcs: Optional[frozenset[int]],
    last_bass: Optional[int],
    prev_bass: Optional[int],
) -> Tuple[str, int, int]:
    # Defaults to musically safe behavior.
    common = int(len(set(last_pcs or set()) & set(prev_pcs or set())))
    motion = 0
    if last_bass is not None and prev_bass is not None:
        d = abs(int(last_bass) - int(prev_bass)) % 12
        motion = int(min(d, 12 - d))
    # Pedal if bass is held and still inside the outgoing harmony.
    if (
        last_bass is not None
        and prev_bass is not None
        and (int(last_bass) % 12) == (int(prev_bass) % 12)
        and (not last_pcs or (int(last_bass) % 12) in set(last_pcs))
    ):
        return "pedal", int(common), int(motion)
    # Strong common-tone glue.
    if int(common) >= 2:
        return "common_tone", int(common), int(motion)
    # Dominant-like leap (P4/P5-ish) into cadence color.
    if int(motion) in {5, 7}:
        return "dominant_pivot", int(common), int(motion)
    # Small bass move: keep it stepwise.
    if int(motion) in {1, 2}:
        return "stepwise", int(common), int(motion)
    if int(common) <= 0 and int(motion) >= 4:
        return "chromatic", int(common), int(motion)
    return "common_tone", int(common), int(motion)


def extract_last_bar_harmonic_context(
    events: List[Tuple],
    total_bars: int,
    beats_per_bar: float = 4.0,
) -> Optional[Dict[str, Any]]:
    """
    Collect pitch classes from the last bar's chord voicing and the bass MIDI note
    so the next generated section can pivot / pedal more smoothly.
    """
    if not events or total_bars < 1:
        return None
    # Only consider events that overlap the final bar of the outgoing timeline.
    # This keeps handoffs local and avoids "teleporting" harmony from much earlier
    # material.
    bar_start = float((int(total_bars) - 1) * float(beats_per_bar))
    bar_end = bar_start + float(beats_per_bar)
    pcs, prev_bass, prev_lead, found_any = _bar_snapshot(events, bar_start=bar_start, bar_end=bar_end)
    if not found_any:
        return None
    if not pcs and prev_bass is None and prev_lead is None:
        return None
    # If we still couldn't capture chord pitch classes in the lookback window (e.g. very sparse
    # events or long held notes that don't overlap the scanned bars), fall back to the last
    # chord-like event anywhere in the timeline.
    if pcs is None:
        try:
            last_notes = None
            for ev in reversed(list(events)):
                if not ev or len(ev) < 6:
                    continue
                ch, _midi, _vel, _start, _dur, notes = ev
                if int(ch) != 1:
                    continue
                if notes:
                    last_notes = notes
                    break
            if last_notes:
                note_list: List[int] = []
                for n in last_notes:
                    if isinstance(n, (int, float)):
                        note_list.append(int(n) % 12)
                if note_list:
                    pcs = frozenset(note_list)
        except Exception:
            pcs = pcs
    prev_bar_pcs: Optional[frozenset[int]] = None
    prev_bar_bass: Optional[int] = None
    if int(total_bars) >= 2:
        p_start = float((int(total_bars) - 2) * float(beats_per_bar))
        p_end = p_start + float(beats_per_bar)
        try:
            prev_bar_pcs, prev_bar_bass, _pl, _pf = _bar_snapshot(events, bar_start=p_start, bar_end=p_end)
        except Exception:
            prev_bar_pcs, prev_bar_bass = None, None
    out: Dict[str, Any] = {}
    # Only return a handoff context when we have harmonic anchors (bass and/or chord pcs).
    # Lead-only snapshots were too weak and created brittle/odd transitions.
    if not pcs and prev_bass is None:
        return None
    if pcs:
        out["previous_chord_pcs"] = pcs
    if prev_bass is not None:
        out["previous_bass_midi"] = prev_bass
    if prev_lead is not None:
        out["previous_lead_midi"] = int(prev_lead)
        out["previous_lead_pc"] = int(prev_lead) % 12
    try:
        strat, common, motion = _choose_pivot_strategy(
            last_pcs=pcs,
            prev_pcs=prev_bar_pcs,
            last_bass=prev_bass,
            prev_bass=prev_bar_bass,
        )
        out["handoff_pivot_strategy"] = str(strat)
        out["handoff_common_tones"] = int(common)
        out["handoff_bass_motion_semitones"] = int(motion)
        anchor = 0.45 + 0.22 * min(2, int(common)) - 0.06 * min(6, int(motion))
        if str(strat) in {"pedal", "common_tone"}:
            anchor += 0.08
        out["handoff_anchor_strength"] = float(max(0.1, min(1.0, anchor)))
    except Exception:
        pass
    return out if out else None
