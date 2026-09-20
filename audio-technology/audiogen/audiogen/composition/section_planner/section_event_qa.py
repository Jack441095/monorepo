"""Typed Event QA passes (velocity, transitions, collisions, contrast)."""

from __future__ import annotations
from audiogen_core.config import resolve_config

from typing import Any, Dict, List, Optional, Tuple

from midi.midi_range_limiter import RANGE_LIMITER

from .chorus_hook_blueprint import _masking_focus_strength_for_emotion
from ..event import Event
from ..section_plan import SectionPlan

_CHANNEL_VEL_KEYS: Dict[int, str] = {
    0: "bass_vel_scale",
    1: "chord_vel_scale",
    2: "melody_vel_scale",
    3: "arp_vel_scale",
    4: "drone_vel_scale",
    5: "melody_vel_scale",
}
def _apply_arrangement_velocity(
    events: List[Tuple],
    curve: Dict[str, Any],
    *,
    handoff_bar0_velocity_mult: Optional[float] = None,
    beats_per_bar: float = 4.0,
    ) -> List[Tuple]:
    sec_dyn = float(curve.get("section_dynamic", 1.0))
    out: List[Tuple] = []
    for ev in events:
        if len(ev) != 6:
            out.append(ev)
            continue
        ch, midi, vel, start, dur, notes = ev
        key = _CHANNEL_VEL_KEYS.get(int(ch))
        m = float(curve.get(key, 1.0)) if key else 1.0
        soft = 1.0
        if (
            handoff_bar0_velocity_mult is not None
            and float(start) < float(beats_per_bar) - 1e-6
        ):
            soft = float(handoff_bar0_velocity_mult)
        nv = int(max(1, min(127, round(float(vel) * m * sec_dyn * soft))))
        out.append((ch, midi, nv, start, dur, notes))
    return out

def _apply_arrangement_velocity_typed(
    events: List[Event],
    curve: Dict[str, Any],
    *,
    handoff_bar0_velocity_mult: Optional[float] = None,
    beats_per_bar: float = 4.0,
    ) -> List[Event]:
    sec_dyn = float(curve.get("section_dynamic", 1.0))
    out: List[Event] = []
    for ev in events:
        key = _CHANNEL_VEL_KEYS.get(int(ev.channel))
        m = float(curve.get(key, 1.0)) if key else 1.0
        soft = 1.0
        if (
            handoff_bar0_velocity_mult is not None
            and float(ev.start_beats) < float(beats_per_bar) - 1e-6
        ):
            soft = float(handoff_bar0_velocity_mult)
        nv = int(max(1, min(127, round(float(ev.velocity) * m * sec_dyn * soft))))
        out.append(
            Event(
                channel=ev.channel,
                midi=ev.midi,
                velocity=nv,
                start_beats=ev.start_beats,
                duration_beats=ev.duration_beats,
                notes=list(ev.notes),
            )
        )
    return out

def _apply_section_transition_gestures_typed(
    events: List[Event],
    plan: SectionPlan,
    *,
    next_role: str,
    strength: float,
    ) -> List[Event]:
    """Write small final-bar handoff gestures so adjacent sections feel connected."""
    rows = list(events or [])
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6 or not rows:
        return rows
    role = str(getattr(plan, "section_role", "") or "").strip().lower()
    nr = str(next_role or "").strip().lower()
    if not role or not nr:
        return rows
    try:
        bars = int(getattr(plan, "bars", 0) or 0)
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
    except Exception:
        bars, bpb = 0, 4.0
    if bars <= 0 or bpb <= 1e-9:
        return rows

    final_bar = max(0, int(bars) - 1)
    final_start = float(final_bar) * float(bpb)
    final_end = float(final_start) + float(bpb)
    total_end = float(bars) * float(bpb)

    def _bar_idx(start_beats: float) -> int:
        return int(float(start_beats) // float(bpb))

    def _pos(start_beats: float) -> float:
        return float(start_beats) - float(_bar_idx(start_beats)) * float(bpb)

    def _clamp_vel(v: float) -> int:
        return int(max(1, min(127, round(float(v)))))

    def _notes_for_bar(bar: int) -> List[int]:
        try:
            notes = list(getattr(plan, "chosen_chord", []) or [])[int(bar)]
        except Exception:
            notes = []
        out = []
        for n in notes:
            try:
                out.append(int(RANGE_LIMITER.clamp_note(int(n), 1)))
            except Exception:
                pass
        return sorted(set(out))

    def _bass_for_bar(bar: int) -> int:
        try:
            note = int((getattr(plan, "chosen_bass", []) or [])[int(bar)])
        except Exception:
            try:
                note = int((getattr(plan, "roots", []) or [])[int(bar)])
            except Exception:
                note = 36
        return int(RANGE_LIMITER.clamp_note(int(note), 0))

    def _has_near(ch: int, start: float, eps: float = 0.04) -> bool:
        for ev in rows:
            try:
                if int(ev.channel) == int(ch) and abs(float(ev.start_beats) - float(start)) <= float(eps):
                    return True
            except Exception:
                continue
        return False

    def _add_event(ch: int, midi: int, vel: int, start: float, dur: float, notes: List[int]) -> None:
        if start < -1e-6 or start >= total_end - 1e-6 or dur <= 1e-6:
            return
        dur2 = min(float(dur), max(0.05, float(total_end) - float(start)))
        rows.append(
            Event(
                channel=int(ch),
                midi=int(midi),
                velocity=_clamp_vel(int(vel)),
                start_beats=float(start),
                duration_beats=float(dur2),
                notes=list(notes),
            )
        )

    def _add_chord_hit(start: float, dur: float, vel: int) -> None:
        notes = _notes_for_bar(final_bar)
        if not notes or _has_near(1, start):
            return
        _add_event(1, 0, int(vel), float(start), float(dur), notes)

    def _add_bass_pickups(pattern: List[Tuple[float, int, int]]) -> None:
        base = _bass_for_bar(final_bar)
        for off, semis, vel in pattern:
            st = float(final_start) + float(off)
            if _has_near(0, st):
                continue
            note = int(RANGE_LIMITER.clamp_note(int(base) + int(semis), 0))
            _add_event(0, note, int(vel), st, min(0.45, bpb * 0.125), [note])

    def _add_arp_lift_fill(start_offs: List[float], vel: int) -> None:
        notes = _notes_for_bar(final_bar)
        if not notes:
            return
        fill_notes = sorted({int(RANGE_LIMITER.clamp_note(int(n) + 12, 3)) for n in notes})
        if not fill_notes:
            return
        for i, off in enumerate(start_offs):
            st = float(final_start) + float(off)
            if _has_near(3, st):
                continue
            note = fill_notes[int(i) % len(fill_notes)]
            _add_event(3, int(note), int(vel) + int(i * 2), st, min(0.22, bpb * 0.08), [int(note)])

    def _trim_tail(channels: set[int], *, from_beat: float, vel_mult: float, keep_strong: bool) -> None:
        shaped: List[Event] = []
        cutoff = float(final_start) + float(from_beat)
        for ev in rows:
            try:
                ch = int(ev.channel)
                st = float(ev.start_beats)
                if ch not in channels or _bar_idx(st) != final_bar or st < cutoff:
                    shaped.append(ev)
                    continue
                pos = _pos(st)
                strong = abs(pos - 0.0) < 0.04 or abs(pos - 2.0) < 0.04
                if keep_strong and not strong and float(ev.duration_beats) < 0.85:
                    continue
                new_dur = min(float(ev.duration_beats), max(0.08, float(final_end) - st - 0.04))
                shaped.append(
                    Event(
                        channel=ev.channel,
                        midi=ev.midi,
                        velocity=_clamp_vel(float(ev.velocity) * float(vel_mult)),
                        start_beats=ev.start_beats,
                        duration_beats=float(new_dur),
                        notes=list(ev.notes),
                    )
                )
            except Exception:
                shaped.append(ev)
        rows[:] = shaped

    if role in {"a", "verse"} and nr == "pre_chorus":
        _trim_tail({3, 5}, from_beat=max(0.0, bpb - 1.0), vel_mult=0.92 + 0.05 * s, keep_strong=False)
        _add_bass_pickups([(max(0.0, bpb - 1.0), 0, 58 + int(8 * s)), (max(0.0, bpb - 0.5), 2, 61 + int(10 * s))])
        _add_chord_hit(final_start + max(0.0, bpb - 0.5), min(0.45, bpb * 0.18), 62 + int(12 * s))
    elif role == "pre_chorus" and nr in {"b", "chorus", "hook", "tag"}:
        _trim_tail({3, 5}, from_beat=max(0.0, bpb - 0.75), vel_mult=0.88, keep_strong=False)
        _add_bass_pickups(
            [
                (max(0.0, bpb - 1.0), 0, 62 + int(8 * s)),
                (max(0.0, bpb - 0.5), 2, 66 + int(10 * s)),
                (max(0.0, bpb - 0.25), 7, 69 + int(12 * s)),
            ]
        )
        _add_chord_hit(final_start + max(0.0, bpb - 0.5), min(0.45, bpb * 0.18), 68 + int(14 * s))
        _add_arp_lift_fill([max(0.0, bpb - 1.0), max(0.0, bpb - 0.5), max(0.0, bpb - 0.25)], 66 + int(10 * s))
    elif role in {"b", "chorus", "hook", "tag"} and nr in {"a", "verse", "outro", "ending"}:
        _trim_tail({1, 3, 5}, from_beat=max(0.0, bpb - 1.0), vel_mult=0.78 + 0.08 * (1.0 - s), keep_strong=True)
        _add_chord_hit(final_start, min(float(bpb), 2.0), 64 + int(8 * s))
    elif nr in {"b", "chorus", "hook", "tag"}:
        _add_bass_pickups([(max(0.0, bpb - 0.5), 2, 62 + int(8 * s))])
        _add_arp_lift_fill([max(0.0, bpb - 0.5), max(0.0, bpb - 0.25)], 62 + int(8 * s))

    return rows

def _apply_phrase_vocal_grammar_typed(
    events: List[Event],
    plan: SectionPlan,
    *,
    strength: float,
    ) -> List[Event]:
    """Shape lead events into clearer vocal-like phrases without changing harmony."""
    rows = list(events or [])
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6 or not rows:
        return rows
    role = str(getattr(plan, "section_role", "") or "").strip().lower()
    if role in {"intro", "outro", "ending"}:
        return rows
    try:
        bars = int(getattr(plan, "bars", 0) or 0)
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        targets = getattr(plan, "timeline_targets", None) or {}
        phrase_roles = list(targets.get("phrase_role_by_bar", []) or [])
        cadence = list(targets.get("cadence_window", []) or [])
        breath = list(targets.get("breath_window", []) or [])
    except Exception:
        bars, bpb, phrase_roles, cadence, breath = 0, 4.0, [], [], []
    if bars <= 0 or bpb <= 1e-9:
        return rows

    def _bar_idx(st: float) -> int:
        return int(float(st) // float(bpb))

    def _bar_start(bar: int) -> float:
        return float(bar) * float(bpb)

    def _clamp_vel(v: float) -> int:
        return int(max(1, min(127, round(float(v)))))

    def _lead_events_in_bar(bar: int) -> List[tuple[int, Event]]:
        out: List[tuple[int, Event]] = []
        for i, ev in enumerate(rows):
            try:
                if int(ev.channel) == 2 and _bar_idx(float(ev.start_beats)) == int(bar):
                    out.append((int(i), ev))
            except Exception:
                continue
        out.sort(key=lambda x: float(x[1].start_beats))
        return out

    # 1) Cadence bars need a held target note, not only short fragments.
    for bar in range(bars):
        try:
            pr = str(phrase_roles[bar] if bar < len(phrase_roles) else "").strip().lower()
        except Exception:
            pr = ""
        try:
            cw = float(cadence[bar] if bar < len(cadence) else 0.0)
        except Exception:
            cw = 0.0
        if pr != "cadence" and cw < 0.85 and bar != bars - 1:
            continue
        lead = _lead_events_in_bar(bar)
        if not lead:
            continue
        idx, ev = lead[-1]
        bar_end = _bar_start(bar + 1)
        st = float(ev.start_beats)
        desired = min(1.35, max(0.65, (bar_end - st) - 0.04))
        if desired > float(ev.duration_beats) + 1e-6:
            rows[idx] = Event(
                channel=ev.channel,
                midi=ev.midi,
                velocity=_clamp_vel(float(ev.velocity) * (1.0 + 0.04 * s)),
                start_beats=ev.start_beats,
                duration_beats=float((1.0 - s) * float(ev.duration_beats) + s * float(desired)),
                notes=list(ev.notes),
            )

    # 2) Answer phrases should leave a small breath before entering.
    for bar in range(1, bars):
        try:
            pr = str(phrase_roles[bar] if bar < len(phrase_roles) else "").strip().lower()
        except Exception:
            pr = ""
        try:
            bw_prev = float(breath[bar - 1] if (bar - 1) < len(breath) else 0.0)
        except Exception:
            bw_prev = 0.0
        if pr not in {"answer", "continuation"} or bw_prev < 0.45:
            continue
        lead = _lead_events_in_bar(bar)
        if not lead:
            continue
        idx, ev = lead[0]
        bar0 = _bar_start(bar)
        pos = float(ev.start_beats) - float(bar0)
        target_pos = min(0.5, float(bpb) * 0.125)
        if pos < target_pos - 1e-6:
            rows[idx] = Event(
                channel=ev.channel,
                midi=ev.midi,
                velocity=ev.velocity,
                start_beats=float(bar0 + (1.0 - s) * pos + s * target_pos),
                duration_beats=ev.duration_beats,
                notes=list(ev.notes),
            )

    return rows

def _apply_post_generation_qa_typed(
    events: List[Event],
    plan: SectionPlan,
    *,
    strength: float,
    ) -> List[Event]:
    """Conservative repairs for obvious full-song failures after generation."""
    rows = list(events or [])
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return rows
    role = str(getattr(plan, "section_role", "") or "").strip().lower()
    if role in {"intro", "outro", "ending"}:
        return rows
    try:
        bars = int(getattr(plan, "bars", 0) or 0)
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        roots = list(getattr(plan, "roots", []) or [])
        chords = list(getattr(plan, "chosen_chord", []) or [])
    except Exception:
        bars, bpb, roots, chords = 0, 4.0, [], []
    if bars <= 0 or bpb <= 1e-9:
        return rows

    def _bar_idx(st: float) -> int:
        return int(float(st) // float(bpb))

    def _bar_start(bar: int) -> float:
        return float(bar) * float(bpb)

    def _has_channel_in_bar(ch: int, bar: int) -> bool:
        for ev in rows:
            try:
                if int(ev.channel) == int(ch) and _bar_idx(float(ev.start_beats)) == int(bar):
                    return True
            except Exception:
                continue
        return False

    def _lead_note_for_bar(bar: int) -> int:
        try:
            chord_notes = [int(n) for n in list(chords[bar] or []) if isinstance(n, int)]
        except Exception:
            chord_notes = []
        if chord_notes:
            # Prefer upper-middle chord tone for singable guide repair.
            n = sorted(chord_notes)[len(chord_notes) // 2]
        else:
            try:
                n = int(roots[bar]) + 12
            except Exception:
                n = int(getattr(plan, "root_note", 60) or 60) + 12
        return int(RANGE_LIMITER.clamp_note(int(n), 2))

    # Lead QA: if a core section has totally empty lead bars, add sparse guide
    # notes only in the emptiest bars. This repairs "not enough melody" without
    # making the line mechanically dense.
    lead_counts = [0 for _ in range(bars)]
    for ev in rows:
        try:
            if int(ev.channel) == 2:
                bi = _bar_idx(float(ev.start_beats))
                if 0 <= bi < bars:
                    lead_counts[bi] += 1
        except Exception:
            continue
    empty_bars = [i for i, c in enumerate(lead_counts) if int(c) == 0]
    max_repairs = int(max(1, round(float(bars) * (0.18 + 0.20 * s))))
    if empty_bars and sum(lead_counts) < max(2, int(round(float(bars) * 1.25))):
        for bar in empty_bars[:max_repairs]:
            note = _lead_note_for_bar(bar)
            rows.append(
                Event(
                    channel=2,
                    midi=int(note),
                    velocity=72,
                    start_beats=float(_bar_start(bar) + min(0.5, bpb * 0.125)),
                    duration_beats=min(0.95, bpb * 0.35),
                    notes=[int(note)],
                )
            )

    # Bass QA: core sections need at least a root support on empty bars.
    if role in {"a", "verse", "pre_chorus", "b", "chorus", "hook", "tag", "a_prime"}:
        for bar in range(bars):
            if _has_channel_in_bar(0, bar):
                continue
            try:
                root = int(roots[bar])
            except Exception:
                root = int(getattr(plan, "root_note", 48) or 48)
            note = int(RANGE_LIMITER.clamp_note(int(root), 0))
            rows.append(
                Event(
                    channel=0,
                    midi=int(note),
                    velocity=58,
                    start_beats=float(_bar_start(bar)),
                    duration_beats=float(bpb),
                    notes=[int(note)],
                )
            )

    rows.sort(key=lambda e: float(e.start_beats))
    return rows

def _apply_slow_emotion_melody_interest_typed(
    events: List[Event],
    plan: SectionPlan,
    *,
    strength: float,
    ) -> List[Event]:
    """Add sparse melodic interest to slow emotions without making them busy."""
    rows = list(events or [])
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return rows
    try:
        emo = str(getattr(getattr(plan, "emotion", None), "name", "") or "").strip().lower()
    except Exception:
        emo = ""
    slow_emotions = {"sadness", "grief", "remorse", "disappointment", "relief"}
    if emo not in slow_emotions:
        return rows
    role = str(getattr(plan, "section_role", "") or "").strip().lower()
    if role in {"intro", "outro", "ending"}:
        return rows
    try:
        bars = int(getattr(plan, "bars", 0) or 0)
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        chords = list(getattr(plan, "chosen_chord", []) or [])
        roots = list(getattr(plan, "roots", []) or [])
        targets = getattr(plan, "timeline_targets", None) or {}
        cadence = list(targets.get("cadence_window", []) or [])
        tension = list(targets.get("tension", []) or [])
    except Exception:
        bars, bpb, chords, roots, cadence, tension = 0, 4.0, [], [], [], []
    if bars <= 0 or bpb <= 1e-9:
        return rows

    def _bar_idx(st: float) -> int:
        return int(float(st) // float(bpb))

    def _bar_start(bar: int) -> float:
        return float(bar) * float(bpb)

    def _clamp_vel(v: float) -> int:
        return int(max(1, min(127, round(float(v)))))

    def _lead_in_bar(bar: int) -> List[Event]:
        out = []
        for ev in rows:
            try:
                if int(ev.channel) == 2 and _bar_idx(float(ev.start_beats)) == int(bar):
                    out.append(ev)
            except Exception:
                continue
        return sorted(out, key=lambda e: float(e.start_beats))

    def _chord_tones_for_bar(bar: int) -> List[int]:
        tones = []
        try:
            tones = [int(n) for n in list(chords[int(bar)] or []) if isinstance(n, (int, float)) and int(n) > 0]
        except Exception:
            tones = []
        if not tones:
            try:
                root = int(roots[int(bar)])
            except Exception:
                root = int(getattr(plan, "root_note", 60) or 60)
            tones = [root + 12, root + 15, root + 19]
        scale_pcs: set[int] = set()
        try:
            from data.emotion_scales import melody_scale_intervals_for_emotion

            intervals = list(melody_scale_intervals_for_emotion(getattr(plan, "emotion", None)) or [])
        except Exception:
            try:
                intervals = list(getattr(getattr(plan, "emotion", None), "melody_scale_intervals", None) or [])
            except Exception:
                intervals = []
        if not intervals:
            try:
                intervals = list(getattr(getattr(plan, "emotion", None), "scale_intervals", None) or [])
            except Exception:
                intervals = []
        try:
            root_pc = int(getattr(plan, "root_note", 60) or 60) % 12
            scale_pcs = {(int(root_pc) + int(iv)) % 12 for iv in intervals}
        except Exception:
            scale_pcs = set()
        if scale_pcs:
            scale_tones = [int(n) for n in tones if int(n) % 12 in scale_pcs]
            if scale_tones:
                tones = scale_tones
        # Keep the added lead in an emotional upper-mid register.
        out = []
        for n in tones:
            x = int(n)
            while x < 60:
                x += 12
            while x > 84:
                x -= 12
            out.append(int(RANGE_LIMITER.clamp_note(int(x), 2)))
        return sorted(set(out))

    def _nearest_tone(target: int, tones: List[int]) -> int:
        if not tones:
            return int(RANGE_LIMITER.clamp_note(int(target), 2))
        pool = []
        for t in tones:
            for d in (-12, 0, 12):
                pool.append(int(RANGE_LIMITER.clamp_note(int(t) + int(d), 2)))
        return int(min(pool, key=lambda n: abs(int(n) - int(target))))

    def _has_near_lead(start: float, eps: float = 0.18) -> bool:
        for ev in rows:
            try:
                if int(ev.channel) == 2 and abs(float(ev.start_beats) - float(start)) <= float(eps):
                    return True
            except Exception:
                continue
        return False

    lead_counts = [0 for _ in range(bars)]
    lead_dur = [0.0 for _ in range(bars)]
    for ev in rows:
        try:
            if int(ev.channel) != 2:
                continue
            st = float(ev.start_beats)
            dur = float(ev.duration_beats)
            b0 = _bar_idx(st)
            b1 = _bar_idx(max(st, st + max(0.0, dur) - 1e-6))
            for bi in range(max(0, b0), min(bars, b1 + 1)):
                lo = _bar_start(bi)
                hi = lo + bpb
                seg = max(0.0, min(st + dur, hi) - max(st, lo))
                if seg > 0:
                    lead_dur[bi] += seg
            if 0 <= b0 < bars:
                lead_counts[b0] += 1
        except Exception:
            continue

    avg_count = sum(lead_counts) / max(1, bars)
    role_floor = 2 if role in {"b", "chorus", "hook", "tag", "pre_chorus"} else 1
    max_add = int(max(1, round(float(bars) * (0.22 + 0.20 * s))))
    if avg_count < 1.15:
        max_add += int(max(1, round(float(bars) * 0.12)))
    added = 0

    prev_pitch = None
    try:
        all_lead = sorted((ev for ev in rows if int(ev.channel) == 2), key=lambda e: float(e.start_beats))
        if all_lead:
            prev_pitch = int(all_lead[-1].midi)
    except Exception:
        prev_pitch = None

    for bar in range(bars):
        if added >= max_add:
            break
        lc = int(lead_counts[bar])
        occ = float(lead_dur[bar]) / float(bpb)
        try:
            cw = float(cadence[bar] if bar < len(cadence) else 0.0)
        except Exception:
            cw = 0.0
        try:
            ten = float(tension[bar] if bar < len(tension) else 0.0)
        except Exception:
            ten = 0.0
        floor = int(role_floor)
        if cw >= 0.85:
            floor = max(1, floor - 1)
        if ten >= 0.62 and role in {"pre_chorus", "b", "chorus", "hook", "tag"}:
            floor += 1
        underfilled = lc < floor or (lc <= 1 and occ < 0.32)
        if not underfilled:
            continue

        tones = _chord_tones_for_bar(bar)
        existing = _lead_in_bar(bar)
        if existing:
            try:
                anchor = int(existing[-1].midi)
            except Exception:
                anchor = prev_pitch if prev_pitch is not None else tones[len(tones) // 2]
        else:
            anchor = prev_pitch if prev_pitch is not None else tones[len(tones) // 2]

        offsets = [1.5, 2.5] if role in {"a", "verse", "a_prime"} else [1.0, 2.0, 2.75]
        if cw >= 0.65:
            offsets = [max(0.0, bpb - 1.0)]
        for off in offsets:
            if added >= max_add:
                break
            if lead_counts[bar] >= floor:
                break
            st = _bar_start(bar) + min(max(0.0, float(off)), max(0.0, bpb - 0.35))
            if _has_near_lead(st):
                continue
            # Step/passing feel: aim one chord tone near the prior melody, then let
            # existing final cadence repair handle the phrase-ending resolution.
            direction = 1 if (bar + added) % 2 == 0 else -1
            target = int(anchor) + int(direction) * (2 if emo in {"sadness", "grief", "remorse"} else 3)
            note = _nearest_tone(target, tones)
            if abs(int(note) - int(anchor)) > 7:
                note = _nearest_tone(int(anchor), tones)
            vel_base = 58 if emo in {"grief", "remorse"} else 62
            if role in {"b", "chorus", "hook", "tag"}:
                vel_base += 5
            dur = 0.48 if role in {"a", "verse", "a_prime"} else 0.38
            if cw >= 0.65:
                dur = min(0.72, max(0.42, bpb - (st - _bar_start(bar)) - 0.08))
            rows.append(
                Event(
                    channel=2,
                    midi=int(note),
                    velocity=_clamp_vel(float(vel_base) * (0.92 + 0.12 * s)),
                    start_beats=float(st),
                    duration_beats=float(dur),
                    notes=[int(note)],
                )
            )
            lead_counts[bar] += 1
            lead_dur[bar] += float(dur)
            prev_pitch = int(note)
            anchor = int(note)
            added += 1

    rows.sort(key=lambda e: float(e.start_beats))
    return rows

def _apply_melody_action_qa_typed(
    events: List[Event],
    plan: SectionPlan,
    *,
    strength: float,
    ) -> List[Event]:
    """Late melody action repair for sections that became too static."""
    rows = list(events or [])
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6 or not rows:
        return rows
    role = str(getattr(plan, "section_role", "") or "").strip().lower()
    if role in {"intro", "outro", "ending", "silence"}:
        return rows
    try:
        bars = int(getattr(plan, "bars", 0) or 0)
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
        chords = list(getattr(plan, "chosen_chord", []) or [])
        roots = list(getattr(plan, "roots", []) or [])
        targets = getattr(plan, "timeline_targets", None) or {}
        cadence = list(targets.get("cadence_window", []) or [])
        tension = list(targets.get("tension", []) or [])
    except Exception:
        bars, bpb, chords, roots, cadence, tension = 0, 4.0, [], [], [], []
    if bars <= 0 or bpb <= 1e-9:
        return rows

    def _bar_idx(st: float) -> int:
        return int(float(st) // float(bpb))

    def _bar_start(bar: int) -> float:
        return float(bar) * float(bpb)

    def _clamp_vel(v: float) -> int:
        return int(max(1, min(127, round(float(v)))))

    def _scale_pcs() -> set[int]:
        try:
            from data.emotion_scales import melody_scale_intervals_for_emotion

            intervals = list(melody_scale_intervals_for_emotion(getattr(plan, "emotion", None)) or [])
        except Exception:
            try:
                intervals = list(getattr(getattr(plan, "emotion", None), "melody_scale_intervals", None) or [])
            except Exception:
                intervals = []
        if not intervals:
            try:
                intervals = list(getattr(getattr(plan, "emotion", None), "scale_intervals", None) or [])
            except Exception:
                intervals = []
        try:
            root_pc = int(getattr(plan, "root_note", 60) or 60) % 12
            return {(int(root_pc) + int(iv)) % 12 for iv in intervals}
        except Exception:
            return set()

    scale_pcs = _scale_pcs()

    def _tones_for_bar(bar: int) -> List[int]:
        try:
            raw = [int(n) for n in list(chords[int(bar)] or []) if isinstance(n, (int, float)) and int(n) > 0]
        except Exception:
            raw = []
        if not raw:
            try:
                root = int(roots[int(bar)])
            except Exception:
                root = int(getattr(plan, "root_note", 60) or 60)
            raw = [root + 12, root + 15, root + 19]
        tones: set[int] = set()
        for n in raw:
            x = int(n)
            while x < 62:
                x += 12
            while x > 86:
                x -= 12
            tones.add(int(RANGE_LIMITER.clamp_note(int(x), 2)))
            for step in (-2, 2):
                y = int(RANGE_LIMITER.clamp_note(int(x) + int(step), 2))
                if not scale_pcs or int(y) % 12 in scale_pcs:
                    tones.add(int(y))
        if scale_pcs:
            filtered = {int(n) for n in tones if int(n) % 12 in scale_pcs}
            if filtered:
                tones = filtered
        return sorted(tones)

    def _nearest(target: int, tones: List[int]) -> int:
        if not tones:
            return int(RANGE_LIMITER.clamp_note(int(target), 2))
        pool = []
        for t in tones:
            for d in (-12, 0, 12):
                pool.append(int(RANGE_LIMITER.clamp_note(int(t) + int(d), 2)))
        return int(min(pool, key=lambda n: (abs(int(n) - int(target)), abs(int(n) - 74))))

    def _has_near_lead(start: float, eps: float = 0.16) -> bool:
        for ev in rows:
            try:
                if int(ev.channel) == 2 and abs(float(ev.start_beats) - float(start)) <= float(eps):
                    return True
            except Exception:
                continue
        return False

    lead_counts = [0 for _ in range(bars)]
    lead_dur = [0.0 for _ in range(bars)]
    all_lead: List[Event] = []
    for ev in rows:
        try:
            if int(ev.channel) != 2:
                continue
            all_lead.append(ev)
            st = float(ev.start_beats)
            dur = float(ev.duration_beats)
            b0 = _bar_idx(st)
            b1 = _bar_idx(max(st, st + max(0.0, dur) - 1e-6))
            for bi in range(max(0, b0), min(bars, b1 + 1)):
                lo = _bar_start(bi)
                hi = lo + bpb
                lead_dur[bi] += max(0.0, min(st + dur, hi) - max(st, lo))
            if 0 <= b0 < bars:
                lead_counts[b0] += 1
        except Exception:
            continue
    if not all_lead:
        return rows

    chorus_like = role in {"b", "chorus", "hook", "tag"}
    pre_like = role in {"pre_chorus", "pre"}
    verse_like = role in {"a", "verse", "a_prime"}
    if chorus_like:
        floor_base = 5
        target_avg = 5.85 + 0.35 * s
        offsets = [0.5, 1.0, 1.75, 2.5, 3.25]
        max_add = int(max(1, round(float(bars) * (0.85 + 0.60 * s))))
    elif pre_like:
        floor_base = 4
        target_avg = 5.15 + 0.25 * s
        offsets = [0.5, 1.25, 2.0, 3.0]
        max_add = int(max(1, round(float(bars) * (0.55 + 0.42 * s))))
    elif verse_like:
        floor_base = 3
        target_avg = 4.45 + 0.22 * s
        offsets = [0.75, 1.5, 2.5, 3.25]
        max_add = int(max(1, round(float(bars) * (0.38 + 0.34 * s))))
    else:
        floor_base = 3
        target_avg = 4.25 + 0.20 * s
        offsets = [0.75, 1.5, 2.5, 3.25]
        max_add = int(max(1, round(float(bars) * (0.32 + 0.28 * s))))

    try:
        emo = str(getattr(getattr(plan, "emotion", None), "name", "") or "").strip().lower()
    except Exception:
        emo = ""
    if emo in {"sadness", "grief", "remorse", "disappointment", "relief", "love", "caring"}:
        target_avg += 0.25

    added = 0
    try:
        prev_pitch = int(sorted(all_lead, key=lambda e: float(e.start_beats))[-1].midi)
    except Exception:
        prev_pitch = 74

    def _add_note(bar: int, off: float, *, prefer_up: bool) -> bool:
        nonlocal added, prev_pitch
        if added >= max_add:
            return False
        st = _bar_start(bar) + min(max(0.0, float(off)), max(0.0, bpb - 0.28))
        if _has_near_lead(st):
            return False
        tones = _tones_for_bar(bar)
        direction = 1 if prefer_up else -1
        target = int(prev_pitch) + direction * (2 if emo in {"sadness", "grief", "remorse"} else 3)
        note = _nearest(int(target), tones)
        if abs(int(note) - int(prev_pitch)) > 8:
            note = _nearest(int(prev_pitch), tones)
        try:
            ten = float(tension[int(bar)] if int(bar) < len(tension) else 0.0)
        except Exception:
            ten = 0.0
        vel = 63 + (7 if chorus_like else 2) + (4 if ten >= 0.62 else 0)
        dur = 0.34 if chorus_like else 0.42
        if emo in {"sadness", "grief", "remorse"}:
            dur += 0.08
            vel -= 4
        rows.append(
            Event(
                channel=2,
                midi=int(note),
                velocity=_clamp_vel(float(vel)),
                start_beats=float(st),
                duration_beats=float(dur),
                notes=[int(note)],
            )
        )
        lead_counts[bar] += 1
        lead_dur[bar] += float(dur)
        prev_pitch = int(note)
        added += 1
        return True

    for bar in range(bars):
        if added >= max_add:
            break
        try:
            cw = float(cadence[bar] if bar < len(cadence) else 0.0)
        except Exception:
            cw = 0.0
        floor = int(floor_base)
        if cw >= 0.85:
            floor = max(2 if chorus_like else 1, floor - 2)
        elif cw >= 0.55:
            floor = max(2 if chorus_like else 1, floor - 1)
        if float(lead_dur[bar]) / float(bpb) >= 0.88 and int(lead_counts[bar]) >= max(2, floor - 1):
            continue
        for off in offsets:
            if int(lead_counts[bar]) >= floor or added >= max_add:
                break
            _add_note(bar, off, prefer_up=((bar + added) % 2 == 0))

    target_total = int(round(float(bars) * float(target_avg)))
    if sum(lead_counts) < target_total and added < max_add:
        bar_order = sorted(range(bars), key=lambda bi: (int(lead_counts[bi]), float(lead_dur[bi])))
        for bar in bar_order:
            if sum(lead_counts) >= target_total or added >= max_add:
                break
            try:
                cw = float(cadence[bar] if bar < len(cadence) else 0.0)
            except Exception:
                cw = 0.0
            if cw >= 0.9:
                continue
            for off in offsets:
                if _add_note(bar, off, prefer_up=((bar + added) % 2 == 0)):
                    break

    rows.sort(key=lambda e: float(e.start_beats))
    return rows

def _apply_hook_strength_qa_typed(
    events: List[Event],
    plan: SectionPlan,
    *,
    strength: float,
    ) -> List[Event]:
    """Make chorus hooks more recognizable by restating weak bar-2 answers."""
    rows = list(events or [])
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6 or not rows:
        return rows
    role = str(getattr(plan, "section_role", "") or "").strip().lower()
    if role not in {"b", "chorus", "hook", "tag"}:
        return rows
    try:
        bars = int(getattr(plan, "bars", 0) or 0)
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
    except Exception:
        bars, bpb = 0, 4.0
    if bars < 2 or bpb <= 1e-9:
        return rows

    def _bar_idx(st: float) -> int:
        return int(float(st) // float(bpb))

    def _bar_start(bar: int) -> float:
        return float(bar) * float(bpb)

    def _lead_in_bar(bar: int) -> List[Event]:
        out = []
        for ev in rows:
            try:
                if int(ev.channel) == 2 and _bar_idx(float(ev.start_beats)) == int(bar):
                    out.append(ev)
            except Exception:
                continue
        return sorted(out, key=lambda e: float(e.start_beats))

    first = _lead_in_bar(0)
    second = _lead_in_bar(1)
    if len(first) < 2:
        return rows

    first_sig = {
        round(float(ev.start_beats) - _bar_start(0), 2)
        for ev in first
        if 0.0 <= (float(ev.start_beats) - _bar_start(0)) < float(bpb)
    }
    second_sig = {
        round(float(ev.start_beats) - _bar_start(1), 2)
        for ev in second
        if 0.0 <= (float(ev.start_beats) - _bar_start(1)) < float(bpb)
    }
    overlap = len(first_sig.intersection(second_sig))
    weak_answer = len(second) < max(2, int(round(len(first) * 0.5))) or overlap < min(2, len(first_sig))
    if not weak_answer:
        return rows

    # Replace only a weak bar-2 lead answer. Other layers remain untouched.
    kept: List[Event] = []
    for ev in rows:
        try:
            if int(ev.channel) == 2 and _bar_idx(float(ev.start_beats)) == 1:
                continue
        except Exception:
            pass
        kept.append(ev)

    copied: List[Event] = []
    max_notes = max(2, min(6, int(round(2 + 4 * s))))
    for ev in first[:max_notes]:
        try:
            pos = float(ev.start_beats) - _bar_start(0)
            if pos < -1e-6 or pos >= float(bpb):
                continue
            note = int(RANGE_LIMITER.clamp_note(int(ev.midi), 2))
            copied.append(
                Event(
                    channel=2,
                    midi=int(note),
                    velocity=int(max(1, min(127, round(float(ev.velocity) * (0.94 + 0.04 * s))))),
                    start_beats=float(_bar_start(1) + pos),
                    duration_beats=float(min(float(ev.duration_beats), max(0.12, float(bpb) - pos - 0.04))),
                    notes=[int(note)],
                )
            )
        except Exception:
            continue
    if not copied:
        return rows
    out = kept + copied
    out.sort(key=lambda e: float(e.start_beats))
    return out

def _apply_arrangement_collision_manager_typed(
    events: List[Event],
    plan: SectionPlan,
    *,
    strength: float,
    ) -> List[Event]:
    """Thin/soften accompaniment that masks the lead in busy bars.

    Priority is intentionally musical and conservative:
    - keep bass and lead intact;
    - keep structural chord downbeats;
    - thin short arp/counter gestures first;
    - soften chord stabs that sit directly on top of lead onsets.
    """
    rows = list(events or [])
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6 or not rows:
        return rows
    layers_indep = resolve_config("composition", "arp_melody_layers_fully_independent", True, bool)
    role = str(getattr(plan, "section_role", "") or "").strip().lower()
    try:
        bars = int(getattr(plan, "bars", 0) or 0)
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
    except Exception:
        bars, bpb = 0, 4.0
    if bars <= 0 or bpb <= 1e-9:
        return rows
    try:
        emotion_lc = str(getattr(getattr(plan, "emotion", None), "name", "") or "").strip().lower()
    except Exception:
        emotion_lc = ""
    masking_focus = _masking_focus_strength_for_emotion(emotion_lc, section_role=role)
    if emotion_lc == "gratitude" and role in {"b", "chorus", "hook", "tag"}:
        masking_focus = max(float(masking_focus), 0.25)
    if emotion_lc == "pride" and role in {"b", "chorus", "hook", "tag"}:
        masking_focus = max(float(masking_focus), 0.18)
    if emotion_lc == "disapproval" and role in {"b", "chorus", "hook", "tag"}:
        masking_focus = max(float(masking_focus), 0.46)
    if emotion_lc == "approval" and role in {"b", "chorus", "hook", "tag"}:
        masking_focus = max(float(masking_focus), 0.24)
    if emotion_lc == "optimism" and role in {"b", "chorus", "hook", "tag"}:
        masking_focus = max(float(masking_focus), 0.18)

    grid = 0.25
    lead_onsets: Dict[int, List[float]] = {i: [] for i in range(bars)}
    lead_steps: Dict[int, set[int]] = {i: set() for i in range(bars)}
    lead_midis: Dict[int, List[int]] = {i: [] for i in range(bars)}
    layer_counts: Dict[int, Dict[int, int]] = {i: {1: 0, 2: 0, 3: 0, 5: 0} for i in range(bars)}
    for ev in rows:
        try:
            ch = int(ev.channel)
            bi = int(float(ev.start_beats) // float(bpb))
            if not (0 <= bi < bars):
                continue
            if ch in layer_counts[bi]:
                layer_counts[bi][ch] += 1
            if ch != 2:
                continue
            pos = float(ev.start_beats) - float(bi) * float(bpb)
            lead_onsets[bi].append(float(pos))
            lead_steps[bi].add(int(round(float(pos) / float(grid))))
            if isinstance(ev.midi, (int, float)):
                lead_midis[bi].append(int(ev.midi))
            for note in list(ev.notes or []):
                if isinstance(note, (int, float)):
                    lead_midis[bi].append(int(note))
        except Exception:
            continue

    def _clamp_vel(v: float) -> int:
        return int(max(1, min(127, round(float(v)))))

    def _event_midis(ev: Event) -> List[int]:
        vals: List[int] = []
        try:
            if isinstance(ev.midi, (int, float)) and int(ev.midi) > 0:
                vals.append(int(ev.midi))
        except Exception:
            pass
        for note in list(ev.notes or []):
            try:
                if isinstance(note, (int, float)) and int(note) > 0:
                    vals.append(int(note))
            except Exception:
                continue
        return vals

    def _register_close(ev: Event, bi: int) -> bool:
        leads = list(lead_midis.get(int(bi), []) or [])
        notes = _event_midis(ev)
        if not leads or not notes:
            return False
        try:
            return min(abs(int(a) - int(b)) for a in leads for b in notes) <= 5
        except Exception:
            return False

    def _strong_pos(pos: float) -> bool:
        return abs(float(pos) - 0.0) <= 0.04 or abs(float(pos) - 2.0) <= 0.04


    # Debug counters: how often we thin/soften arp in chorus roles.
    dbg_soft_arp = 0
    dbg_drop_arp = 0
    dbg_soft_arp_v_before_min = 999
    dbg_soft_arp_v_before_max = -1
    dbg_soft_arp_v_after_min = 999
    dbg_soft_arp_v_after_max = -1

    managed: List[Event] = []
    for ev in rows:
        try:
            ch = int(ev.channel)
            st = float(ev.start_beats)
            bi = int(st // float(bpb))
            pos = st - float(bi) * float(bpb)
            if bi < 0 or bi >= bars:
                managed.append(ev)
                continue
            lead_count = len(lead_onsets.get(bi, []))
            # Treat >=2 lead onsets as "dense" across roles so collision thinning
            # does not disproportionately strip chorus arps compared to verses.
            dense_threshold = 2
            dense_lead = lead_count >= dense_threshold
            step = int(round(float(pos) / float(grid)))
            near_lead = any(abs(int(step) - int(lp)) <= 1 for lp in lead_steps.get(bi, set()))
            exact_lead = any(abs(float(pos) - float(p)) <= 0.06 for p in lead_onsets.get(bi, []))
            reg_close = _register_close(ev, bi)
            total_companion = int(layer_counts.get(bi, {}).get(3, 0)) + int(layer_counts.get(bi, {}).get(5, 0))
            companion_busy = total_companion >= (6 if role in {"b", "chorus", "hook", "tag"} else 4)
            clutter = (dense_lead and near_lead) or (companion_busy and exact_lead) or (dense_lead and reg_close and near_lead)
            # When arp+melody layers are configured as "fully independent", keep the arp
            # bed untouched for non-chorus roles. Chorus-like roles still allow thinning
            # so hooks remain intelligible under dense toplines.
            if layers_indep and ch == 3 and role not in {"b", "chorus", "hook", "tag"}:
                managed.append(ev)
                continue
            # When the lead is already busy, thin *all* short arp / counter blips, not
            # only those that land on a grid cell adjacent to a lead step (a later arp
            # can still sit on a “free” 16th and read as clutter).
            arp_clash = bool(dense_lead) and ch in {3, 5} and float(ev.duration_beats) < 1.25

            if (clutter or arp_clash) and ch in {3, 5} and float(ev.duration_beats) < 1.25:
                # Chorus continuity rule: never drop the dedicated arp bed (ch=3) in chorus roles.
                # Instead, keep a strong anchor hit (downbeat/half-bar) and soften it so it supports
                # rather than masks the lead. Non-anchor blips are thinned like counterlines.
                if ch == 3 and role in {"b", "chorus", "hook", "tag"}:
                    # Bar-end anchor protection: never drop arp hits in the final
                    # quarter of the bar (>= bpb - 1.0 beats). This keeps the arp
                    # "finishing the bar" so it doesn't sound like a dropout.
                    is_bar_end_anchor = float(pos) >= max(0.0, float(bpb) - 1.0)
                    if (
                        float(masking_focus) > 1e-6
                        and dense_lead
                        and (near_lead or exact_lead or reg_close)
                        and (not _strong_pos(pos))
                        and (not is_bar_end_anchor)
                        and float(ev.duration_beats) < 0.85
                    ):
                        dbg_drop_arp += 1
                        continue
                    # Keep only structural arp anchors when things get cluttered.
                    # Only thin very short blips; keep longer arp tones so chorus register
                    # and perceived "bed" energy stays high.
                    # If the bar only has a couple of very short companion blips, thin them
                    # aggressively so a busy lead reads clearly. When the arp bed is already
                    # established (many companion hits), prefer softening over dropping so
                    # choruses stay energetic.
                    if (
                        (not _strong_pos(pos))
                        and (not is_bar_end_anchor)
                        and float(ev.duration_beats) <= 0.30
                        and total_companion <= 3
                    ):
                        dbg_drop_arp += 1
                        continue
                    # More reduction when we're close to lead onsets/register; less otherwise.
                    red = 0.12
                    if dense_lead and (near_lead or exact_lead or reg_close):
                        red = 0.32
                    elif dense_lead:
                        red = 0.22
                    try:
                        dbg_soft_arp_v_before_min = min(int(dbg_soft_arp_v_before_min), int(ev.velocity))
                        dbg_soft_arp_v_before_max = max(int(dbg_soft_arp_v_before_max), int(ev.velocity))
                    except Exception:
                        pass
                    v2 = _clamp_vel(float(ev.velocity) * (1.0 - float(red) * s))
                    try:
                        dbg_soft_arp_v_after_min = min(int(dbg_soft_arp_v_after_min), int(v2))
                        dbg_soft_arp_v_after_max = max(int(dbg_soft_arp_v_after_max), int(v2))
                    except Exception:
                        pass
                    managed.append(
                        Event(
                            channel=ev.channel,
                            midi=ev.midi,
                            velocity=int(v2),
                            start_beats=ev.start_beats,
                            duration_beats=ev.duration_beats,
                            notes=list(ev.notes),
                        )
                    )
                    dbg_soft_arp += 1
                    continue
                # Non-chorus (or counterline): allow thinning, except keep the
                # bar-end anchor for ch3 so the arp bed always finishes the bar.
                if ch == 3:
                    is_bar_end_anchor = float(pos) >= max(0.0, float(bpb) - 1.0)
                    if is_bar_end_anchor:
                        managed.append(ev)
                        continue
                    dbg_drop_arp += 1
                continue
            if clutter and ch == 1:
                strong = _strong_pos(pos)
                if not strong and float(ev.duration_beats) < 0.9:
                    continue
                managed.append(
                    Event(
                        channel=ev.channel,
                        midi=ev.midi,
                        velocity=_clamp_vel(float(ev.velocity) * (1.0 - (0.22 if reg_close else 0.14) * s)),
                        start_beats=ev.start_beats,
                        duration_beats=ev.duration_beats,
                        notes=list(ev.notes),
                    )
                )
                continue
            if dense_lead and ch == 5 and role in {"intro", "a", "verse", "outro", "ending"}:
                # Counterline should answer, not shadow, in sparse/intimate roles.
                if near_lead and not _strong_pos(pos):
                    continue
            if ch == 3 and role in {"intro", "a", "verse", "pre_chorus", "a_prime", "outro", "ending"}:
                # Call/response lift: only bring the arp forward in true empty
                # lead bars. The broader version also lifted around sparse lead
                # phrases and raised overlap/phrase-end regressions in audits.
                if lead_count == 0 and (not near_lead) and (not exact_lead):
                    lift = 0.05 if role in {"intro", "outro", "ending"} else 0.08
                    managed.append(
                        Event(
                            channel=ev.channel,
                            midi=ev.midi,
                            velocity=_clamp_vel(float(ev.velocity) * (1.0 + float(lift) * s)),
                            start_beats=ev.start_beats,
                            duration_beats=ev.duration_beats,
                            notes=list(ev.notes),
                        )
                    )
                    continue
        except Exception:
            pass
        managed.append(ev)
    managed.sort(key=lambda e: float(e.start_beats))

    return managed

def _apply_section_contrast_qa_typed(
    events: List[Event],
    plan: SectionPlan,
    *,
    strength: float,
    ) -> List[Event]:
    """Preserve verse space and reinforce chorus arrival without changing notes."""
    rows = list(events or [])
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6 or not rows:
        return rows
    role = str(getattr(plan, "section_role", "") or "").strip().lower()
    if role in {"intro", "outro", "ending"}:
        return rows
    try:
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
    except Exception:
        bpb = 4.0
    if bpb <= 1e-9:
        return rows

    def _clamp_vel(v: float) -> int:
        return int(max(1, min(127, round(float(v)))))

    out: List[Event] = []
    for ev in rows:
        try:
            ch = int(ev.channel)
            st = float(ev.start_beats)
            bi = int(st // float(bpb))
            pos = st - float(bi) * float(bpb)
            if role in {"a", "verse"} and bi == 0 and ch in {3, 5} and pos > 0.04 and float(ev.duration_beats) < 0.9:
                continue
            # Chorus impact: make bar-1 downbeat feel like a single event (layers land together).
            # Include arp + counter in the "hit" and gently snap near-downbeat onsets onto beat 1.
            if role in {"b", "chorus", "hook", "tag"} and bi == 0 and ch in {0, 1, 2, 3, 5} and abs(pos) <= 0.12:
                bar0 = float(bi) * float(bpb)
                st2 = bar0 if abs(pos) <= 0.12 else st
                out.append(
                    Event(
                        channel=ev.channel,
                        midi=ev.midi,
                        velocity=_clamp_vel(float(ev.velocity) * (1.0 + 0.12 * s)),
                        start_beats=float(st2),
                        duration_beats=ev.duration_beats,
                        notes=list(ev.notes),
                    )
                )
                continue
        except Exception:
            pass
        out.append(ev)
    out.sort(key=lambda e: float(e.start_beats))
    return out
def _apply_stability_contract_typed(events: List[Event], *, plan: SectionPlan) -> List[Event]:
    """
    Fast, quality-preserving invariants to prevent realtime degenerate payloads.

    - Chord poly hits use (channel=1, midi=0, notes=[...]). Ensure >=2 notes.
    - Track long arp pitch-repeat runs (channel=3) for observability.
    """
    out: List[Event] = []
    chord_one_note_fixes = 0
    arp_repeat_runs = 0
    last_arp = None
    run = 0

    for ev in events:
        try:
            ch = int(ev.channel)
        except Exception:
            out.append(ev)
            continue

        if ch == 1:
            try:
                is_poly = int(ev.midi) == 0 and isinstance(ev.notes, list)
            except Exception:
                is_poly = False
            if is_poly:
                nn = [int(n) for n in (ev.notes or []) if isinstance(n, int)]
                if 0 < len(nn) < 2:
                    base = int(nn[0])
                    nn2 = sorted({base, int(base + 12)})
                    chord_one_note_fixes += 1
                    out.append(
                        Event(
                            channel=ev.channel,
                            midi=ev.midi,
                            velocity=ev.velocity,
                            start_beats=ev.start_beats,
                            duration_beats=ev.duration_beats,
                            notes=list(nn2),
                        )
                    )
                    continue

        if ch == 3:
            try:
                midi = int(ev.midi)
            except Exception:
                midi = None
            if midi is not None and last_arp is not None and int(midi) == int(last_arp):
                run += 1
            else:
                if run >= 7:
                    arp_repeat_runs += 1
                run = 0
            last_arp = midi

        out.append(ev)

    if run >= 7:
        arp_repeat_runs += 1

    try:
        setattr(plan, "_debug_stability_chord_one_note_fixes", int(chord_one_note_fixes))
    except Exception:
        pass
    try:
        setattr(plan, "_debug_stability_arp_repeat_runs", int(arp_repeat_runs))
    except Exception:
        pass
    return out

def _apply_velocity_curves_typed(
    events: List[Event],
    *,
    plan: SectionPlan,
    strength: float = 0.85,
    ) -> List[Event]:
    """
    Apply subtle per-part dynamics curves using section timeline + tension.

    Channels:
      3 arp: mild ramp within each 4-bar phrase
      2 melody: peak near phrase climax
      1 chords: softer toward cadences (bar 4 of phrase)
      0 bass: slight support under cadences
    """
    bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
    tension = list((getattr(plan, "timeline_targets", None) or {}).get("tension", []) or [])
    strength = max(0.0, min(1.0, float(strength)))

    def _tbar(bar: int) -> float:
        if tension and 0 <= bar < len(tension):
            try:
                return max(0.0, min(1.25, float(tension[bar])))
            except Exception:
                return 1.0
        return 1.0

    out: List[Event] = []
    for ev in events:
        try:
            bar = int(float(ev.start_beats) // bpb) if bpb > 1e-9 else 0
        except Exception:
            bar = 0
        bar_in_phrase = int(bar % 4)
        t = _tbar(bar)
        # Normalize tension into ~0..1
        t01 = float(max(0.0, min(1.0, t / 1.25)))

        mult = 1.0
        ch = int(ev.channel)
        if ch == 3:
            # Arp: slight crescendo into bar 4 of phrase (performed bed).
            ramp = 0.93 + 0.05 * float(bar_in_phrase)  # 0.93..1.08
            mult *= ramp
            mult *= (0.96 + 0.10 * t01)
        elif ch == 2:
            # Melody: peak near phrase climax (around bar 3).
            # weights: bar 0 low, bar 1 mid, bar 2 high, bar 3 release.
            peak = {0: 0.94, 1: 1.00, 2: 1.08, 3: 0.98}.get(bar_in_phrase, 1.0)
            mult *= peak
            mult *= (0.98 + 0.14 * t01)
        elif ch == 1:
            # Chords: soften toward cadence bar, but let tension lift slightly.
            cad = {0: 1.02, 1: 1.00, 2: 0.98, 3: 0.92}.get(bar_in_phrase, 0.98)
            mult *= cad
            mult *= (0.98 + 0.08 * t01)
        elif ch == 0:
            # Bass: keep stable; tiny support into cadence.
            sup = {0: 1.00, 1: 1.00, 2: 1.01, 3: 1.04}.get(bar_in_phrase, 1.0)
            mult *= sup
            mult *= (0.99 + 0.05 * t01)

        # Blend toward 1.0 if strength < 1.
        mult = 1.0 + (float(mult) - 1.0) * float(strength)
        nv = int(max(1, min(127, round(float(ev.velocity) * float(mult)))))
        out.append(
            Event(
                channel=ev.channel,
                midi=ev.midi,
                velocity=int(nv),
                start_beats=ev.start_beats,
                duration_beats=ev.duration_beats,
                notes=list(ev.notes),
            )
        )
    return out