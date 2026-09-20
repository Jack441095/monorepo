"""Melody event repair: cadence, leaps, repeats, emotion smoothing."""

from __future__ import annotations
from audiogen_core.config import resolve_config

import math
from typing import Any, List, Optional, Tuple

from audiogen_core.composition_runtime_flags import phrase_length_bars_clamped
from midi.midi_range_limiter import RANGE_LIMITER

from ..section_plan import SectionPlan

def _repair_phrase_end_chord_tone_events(plan: SectionPlan, events: List[Tuple], *, channel: int = 2) -> List[Tuple]:
    """
    Final merged-event landing repair: keep phrase-ending and structural
    strong-beat lead notes on active chord tones after later polish passes run.
    """
    if not events:
        return list(events or [])
    enabled = resolve_config("composition", "melody_final_chord_tone_repair_enabled", True, bool)
    strength = resolve_config("composition", "melody_final_chord_tone_repair_strength", 1.0, float)
    configured_max_move = resolve_config("composition", "melody_final_chord_tone_repair_max_move_semitones", 12, int)
    strength = max(0.0, min(1.0, float(strength)))
    if not enabled or strength <= 1e-6:
        return list(events or [])
    try:
        bars = int(getattr(plan, "bars", 0) or 0)
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
    except Exception:
        bars, bpb = 0, 4.0
    if bars <= 0 or bpb <= 1e-9:
        return list(events or [])

    out = list(events)
    chord_pcs_by_bar: List[set[int]] = [set() for _ in range(bars)]
    chord_windows_by_bar: List[List[Tuple[float, float, set[int]]]] = [[] for _ in range(bars)]
    try:
        chosen = list(getattr(plan, "chosen_chord", []) or [])
        for bi in range(min(bars, len(chosen))):
            chord_pcs_by_bar[bi].update(
                int(n) % 12 for n in list(chosen[bi] or []) if isinstance(n, (int, float)) and int(n) > 0
            )
    except Exception:
        pass
    for ev in out:
        try:
            if int(ev[0]) != 1:
                continue
            bi = int(float(ev[3]) // bpb)
            if not (0 <= bi < bars):
                continue
            notes = list(ev[5] or [])
            pcs = {int(n) % 12 for n in notes if isinstance(n, (int, float)) and int(n) > 0}
            chord_pcs_by_bar[bi].update(set(pcs))
            if pcs:
                local_start = max(0.0, float(ev[3]) - float(bi) * float(bpb))
                local_end = min(float(bpb), max(float(local_start), float(local_start) + float(ev[4])))
                chord_windows_by_bar[bi].append((float(local_start), float(local_end), set(pcs)))
        except Exception:
            continue
    for bi in range(bars):
        try:
            chord_windows_by_bar[bi].sort(key=lambda item: float(item[0]))
        except Exception:
            pass

    try:
        phrase_len = phrase_length_bars_clamped(2, 8)
    except Exception:
        phrase_len = 4
    try:
        cad_win = list((getattr(plan, "timeline_targets", {}) or {}).get("cadence_window", []) or [])
    except Exception:
        cad_win = []
    role_lc = str(getattr(plan, "section_role", "") or "").strip().lower()
    emo_lc = str(getattr(getattr(plan, "emotion", None), "name", "") or "").strip().lower()
    roots = list(getattr(plan, "roots", []) or [])
    eps_beats = 0.90
    strong_eps = resolve_config("composition", "strong_beat_epsilon_beats", 0.06, float)
    strong_eps = max(0.06, min(0.14, float(strong_eps) + 0.02 * float(strength)))
    base_phrase_move = 10 if emo_lc in {
        "anger",
        "annoyance",
        "approval",
        "curiosity",
        "disgust",
        "fear",
        "gratitude",
        "joy",
        "love",
        "nervousness",
        "pride",
        "realization",
        "relief",
        "surprise",
    } else 8
    phrase_max_move = int(max(7, min(14, round(base_phrase_move + 2.0 * float(strength)))))
    strong_max_move = int(max(5, min(int(configured_max_move), round(7 + 3.0 * float(strength)))))
    phrase_max_move = int(max(strong_max_move, min(int(configured_max_move), int(phrase_max_move))))

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

    lead_indices = []
    for idx, ev in enumerate(out):
        try:
            if int(ev[0]) == int(channel):
                lead_indices.append(idx)
        except Exception:
            continue
    if not lead_indices:
        return out
    lead_indices.sort(key=lambda i: float(out[i][3]))

    def _neighbor_pitch(sorted_pos: int, offset: int) -> Optional[int]:
        j = int(sorted_pos) + int(offset)
        if not (0 <= j < len(lead_indices)):
            return None
        try:
            return int(out[lead_indices[j]][1])
        except Exception:
            return None

    def _candidate_midi_for_pc(cur: int, pc: int, prev_pitch: Optional[int], next_pitch: Optional[int]) -> int:
        cands = []
        for delta in range(-36, 37, 12):
            base = int(cur) + int(delta)
            x = base + ((int(pc) - (base % 12)) % 12)
            for y in (x, x - 12):
                try:
                    y2 = int(RANGE_LIMITER.clamp_note(int(y), int(channel)))
                except Exception:
                    y2 = int(y)
                cost = abs(y2 - int(cur))
                if prev_pitch is not None:
                    cost += max(0, abs(y2 - int(prev_pitch)) - 7) * 3
                if next_pitch is not None:
                    cost += max(0, abs(int(next_pitch) - y2) - 7) * 2
                cands.append((cost, abs(y2 - int(cur)), y2))
        if not cands:
            return int(cur)
        cands.sort(key=lambda t: (t[0], t[1]))
        return int(cands[0][2])

    def _active_chord_pcs_for_onset(bar: int, local_beat: float) -> set[int]:
        try:
            if 0 <= int(bar) < len(chord_windows_by_bar):
                for s0, s1, pcs in chord_windows_by_bar[int(bar)]:
                    if float(s0) - 1e-6 <= float(local_beat) <= float(s1) + 1e-6 and pcs:
                        return set(pcs)
        except Exception:
            pass
        try:
            if 0 <= int(bar) < len(chord_pcs_by_bar):
                return set(chord_pcs_by_bar[int(bar)] or set())
        except Exception:
            pass
        return set()

    def _preferred_target_pcs(pcs: set[int], *, bar: int, cur_pc: int, phrase_cadence: bool) -> set[int]:
        target_pcs = set(int(pc) % 12 for pc in pcs)
        if scale_pcs:
            in_scale = {int(pc) for pc in target_pcs if int(pc) in scale_pcs}
            if in_scale:
                target_pcs = in_scale
            elif emo_lc in {"gratitude", "relief"}:
                target_pcs = set(scale_pcs)
        tonic_pc = None
        try:
            if bar < len(roots):
                tonic_pc = int(roots[bar]) % 12
        except Exception:
            tonic_pc = None
        if phrase_cadence:
            if role_lc in {"b", "chorus", "hook", "tag", "outro", "ending"} and tonic_pc in target_pcs:
                target_pcs = {int(tonic_pc)}
            elif role_lc == "pre_chorus" and tonic_pc in target_pcs and len(target_pcs) > 1:
                target_pcs.discard(int(tonic_pc))
        if not target_pcs:
            return set(pcs)
        return set(target_pcs)

    def _retune_lead_at_sorted_pos(sorted_pos: int, pcs: set[int], *, phrase_cadence: bool, max_move: int) -> None:
        if sorted_pos is None:
            return
        idx = lead_indices[int(sorted_pos)]
        try:
            ev = out[idx]
            cur = int(ev[1])
        except Exception:
            return
        cur_pc = int(cur) % 12
        target_pcs = _preferred_target_pcs(set(pcs), bar=int(float(out[idx][3]) // bpb), cur_pc=cur_pc, phrase_cadence=phrase_cadence)
        if cur_pc in target_pcs:
            return
        best_pc = min(
            target_pcs,
            key=lambda pc: min(abs(int(pc) - cur_pc), 12 - abs(int(pc) - cur_pc)),
        )
        new_midi = _candidate_midi_for_pc(cur, int(best_pc), _neighbor_pitch(sorted_pos, -1), _neighbor_pitch(sorted_pos, 1))
        if int(new_midi) == int(cur):
            return
        if abs(int(new_midi) - int(cur)) > int(max_move):
            return
        try:
            ch_e, _m, vel, st, dur, notes = ev
            new_notes = list(notes or [])
            if new_notes:
                new_notes[0] = int(new_midi)
            else:
                new_notes = [int(new_midi)]
            out[idx] = (ch_e, int(new_midi), int(vel), float(st), float(dur), new_notes)
        except Exception:
            return

    for bar in range(bars):
        is_phrase_end = ((int(bar) + 1) % int(max(1, phrase_len))) == 0
        is_cad_bar = bool(bar < len(cad_win) and float(cad_win[bar] or 0.0) >= 0.45)
        bar_start = float(bar) * bpb
        bar_end = float(bar + 1) * bpb

        # Strong beats carry harmonic identity. Repair integer-beat starts,
        # leaving offbeat passing tones and pickups untouched.
        for pos, idx in enumerate(lead_indices):
            try:
                ev = out[idx]
                st = float(ev[3])
                dur = float(ev[4])
            except Exception:
                continue
            if st < bar_start - 1e-6 or st >= bar_end + 1e-6:
                continue
            beat = float(st - bar_start)
            nearest_beat = round(float(beat))
            if not (0 <= nearest_beat <= int(math.floor(float(bpb))) and abs(float(beat) - float(nearest_beat)) <= strong_eps):
                continue
            if float(dur) < 0.18:
                continue
            pcs = _active_chord_pcs_for_onset(int(bar), float(beat))
            if not pcs:
                continue
            _retune_lead_at_sorted_pos(pos, pcs, phrase_cadence=False, max_move=int(strong_max_move))

        if not (is_phrase_end or is_cad_bar or bar == bars - 1):
            continue
        cand_pos = None
        cand_start = -1.0
        fallback_pos = None
        fallback_start = -1.0
        for pos, idx in enumerate(lead_indices):
            try:
                ev = out[idx]
                st = float(ev[3])
                dur = float(ev[4])
            except Exception:
                continue
            if st < bar_start - 1e-6 or st >= bar_end + 1e-6:
                continue
            if st >= fallback_start:
                fallback_start = st
                fallback_pos = pos
            if st + dur < bar_end - eps_beats:
                continue
            if st >= cand_start:
                cand_start = st
                cand_pos = pos
        if cand_pos is None:
            # Phrase planners sometimes end a phrase before the literal bar end.
            # In that case, repair the latest lead onset in the phrase/cadence bar.
            cand_pos = fallback_pos
        if cand_pos is None:
            continue
        try:
            ev = out[lead_indices[int(cand_pos)]]
            local = float(ev[3]) - float(bar_start)
        except Exception:
            local = float(bpb)
        pcs = _active_chord_pcs_for_onset(int(bar), float(local))
        if not pcs:
            continue
        _retune_lead_at_sorted_pos(cand_pos, pcs, phrase_cadence=True, max_move=int(phrase_max_move))

    return out


def _cap_large_leaps_events(
    events: List[Tuple],
    *,
    emotion: Any,
    channel: int = 2,
    max_interval: int = 9,
) -> List[Tuple]:
    """Conservatively pull oversized adjacent lead leaps back into singable range."""
    if not events:
        return list(events or [])
    out = list(events)
    try:
        indices = sorted(
            (i for i, ev in enumerate(out) if isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == int(channel)),
            key=lambda i: float(out[i][3]),
        )
    except Exception:
        return out
    if len(indices) < 2:
        return out
    cap = max(5, min(14, int(max_interval)))
    _ = emotion

    for prev_idx, cur_idx in zip(indices, indices[1:]):
        try:
            prev = int(out[prev_idx][1])
            cur = int(out[cur_idx][1])
        except Exception:
            continue
        diff = int(cur) - int(prev)
        if abs(diff) <= cap:
            continue
        candidates = []
        for oct_shift in range(-3, 4):
            cand = int(cur) + 12 * int(oct_shift)
            try:
                cand = int(RANGE_LIMITER.clamp_note(int(cand), int(channel)))
            except Exception:
                cand = int(cand)
            interval = abs(int(cand) - int(prev))
            # Prefer preserving pitch class by octave displacement; this keeps
            # the emotional scale/key result from the melody generator intact.
            candidates.append((0 if interval <= cap else 1, interval, abs(int(cand) - int(cur)), int(cand)))
        candidates.sort(key=lambda t: (t[0], t[1] if t[0] == 0 else abs(t[1] - cap), t[2]))
        if not candidates:
            continue
        target = int(candidates[0][3])
        if int(target) == int(cur) or abs(int(target) - int(prev)) > int(cap):
            continue
        try:
            ch_e, _m, vel, st, dur, notes = out[cur_idx]
            new_notes = list(notes or [])
            if new_notes:
                new_notes[0] = int(target)
            else:
                new_notes = [int(target)]
            out[cur_idx] = (ch_e, int(target), int(vel), float(st), float(dur), new_notes)
        except Exception:
            continue
    return out


def _break_repeated_lead_notes_events(plan: SectionPlan, events: List[Tuple], *, channel: int = 2) -> List[Tuple]:
    """Final repeat cleanup that keeps replacements inside the chord/scale palette."""
    if not events:
        return list(events or [])
    out = list(events)
    try:
        bars = int(getattr(plan, "bars", 0) or 0)
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
    except Exception:
        bars, bpb = 0, 4.0
    if bars <= 0 or bpb <= 1e-9:
        return out

    chord_pcs_by_bar: List[set[int]] = [set() for _ in range(bars)]
    try:
        chosen = list(getattr(plan, "chosen_chord", []) or [])
        for bi in range(min(bars, len(chosen))):
            chord_pcs_by_bar[bi].update(
                int(n) % 12 for n in list(chosen[bi] or []) if isinstance(n, (int, float)) and int(n) > 0
            )
    except Exception:
        pass
    for ev in out:
        try:
            if int(ev[0]) != 1:
                continue
            bi = int(float(ev[3]) // bpb)
            if 0 <= bi < bars:
                chord_pcs_by_bar[bi].update(
                    int(n) % 12 for n in list(ev[5] or []) if isinstance(n, (int, float)) and int(n) > 0
                )
        except Exception:
            continue

    try:
        from data.emotion_scales import melody_scale_intervals_for_emotion

        intervals = list(melody_scale_intervals_for_emotion(getattr(plan, "emotion", None)) or [])
    except Exception:
        intervals = []
    if not intervals:
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

    try:
        indices = sorted(
            (i for i, ev in enumerate(out) if isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == int(channel)),
            key=lambda i: float(out[i][3]),
        )
    except Exception:
        return out
    if len(indices) < 2:
        return out

    def _candidate(cur: int, target_pcs: set[int], prev_pitch: Optional[int], next_pitch: Optional[int]) -> Optional[int]:
        cands = []
        for pc in sorted(int(x) % 12 for x in target_pcs):
            for delta in range(-24, 25, 12):
                base = int(cur) + int(delta)
                x = base + ((int(pc) - (base % 12)) % 12)
                for y in (x, x - 12):
                    try:
                        y2 = int(RANGE_LIMITER.clamp_note(int(y), int(channel)))
                    except Exception:
                        y2 = int(y)
                    if int(y2) == int(cur):
                        continue
                    move = abs(int(y2) - int(cur))
                    if move > 5:
                        continue
                    cost = move
                    if prev_pitch is not None:
                        cost += max(0, abs(int(y2) - int(prev_pitch)) - 7) * 4
                    if next_pitch is not None:
                        cost += max(0, abs(int(next_pitch) - int(y2)) - 7) * 3
                    cands.append((cost, move, int(y2)))
        if not cands:
            return None
        cands.sort(key=lambda t: (t[0], t[1]))
        return int(cands[0][2])

    prev_pitch: Optional[int] = None
    for pos, idx in enumerate(indices):
        try:
            cur = int(out[idx][1])
        except Exception:
            continue
        if prev_pitch is None:
            prev_pitch = int(cur)
            continue
        if int(cur) != int(prev_pitch):
            prev_pitch = int(cur)
            continue
        try:
            st = float(out[idx][3])
            bar = int(st // bpb)
        except Exception:
            bar = 0
        chord_pcs = set(chord_pcs_by_bar[bar] if 0 <= bar < bars else set())
        target_pcs = set(chord_pcs)
        if scale_pcs and target_pcs:
            both = {int(pc) for pc in target_pcs if int(pc) in scale_pcs}
            if both:
                target_pcs = both
        if not target_pcs and scale_pcs:
            target_pcs = set(scale_pcs)
        target_pcs = {int(pc) for pc in target_pcs if int(pc) != (int(cur) % 12)}
        if not target_pcs:
            prev_pitch = int(cur)
            continue
        next_pitch = None
        if pos + 1 < len(indices):
            try:
                next_pitch = int(out[indices[pos + 1]][1])
            except Exception:
                next_pitch = None
        new_midi = _candidate(int(cur), target_pcs, int(prev_pitch), next_pitch)
        if new_midi is None:
            prev_pitch = int(cur)
            continue
        try:
            ch_e, _m, vel, st, dur, notes = out[idx]
            new_notes = list(notes or [])
            if new_notes:
                new_notes[0] = int(new_midi)
            else:
                new_notes = [int(new_midi)]
            out[idx] = (ch_e, int(new_midi), int(vel), float(st), float(dur), new_notes)
            prev_pitch = int(new_midi)
        except Exception:
            prev_pitch = int(cur)
            continue
    return out


def _smooth_target_emotion_leaps_events(
    plan: SectionPlan,
    events: List[Tuple],
    *,
    channel: int = 2,
    max_interval: int = 8,
) -> List[Tuple]:
    """For sensitive emotions, retune oversized lead jumps to nearby chord/scale tones."""
    if not events:
        return list(events or [])
    out = list(events)
    try:
        bars = int(getattr(plan, "bars", 0) or 0)
        bpb = float(getattr(plan, "beats_per_bar", 4.0) or 4.0)
    except Exception:
        bars, bpb = 0, 4.0
    if bars <= 0 or bpb <= 1e-9:
        return out

    chord_pcs_by_bar: List[set[int]] = [set() for _ in range(bars)]
    try:
        chosen = list(getattr(plan, "chosen_chord", []) or [])
        for bi in range(min(bars, len(chosen))):
            chord_pcs_by_bar[bi].update(
                int(n) % 12 for n in list(chosen[bi] or []) if isinstance(n, (int, float)) and int(n) > 0
            )
    except Exception:
        pass
    for ev in out:
        try:
            if int(ev[0]) != 1:
                continue
            bi = int(float(ev[3]) // bpb)
            if 0 <= bi < bars:
                chord_pcs_by_bar[bi].update(
                    int(n) % 12 for n in list(ev[5] or []) if isinstance(n, (int, float)) and int(n) > 0
                )
        except Exception:
            continue

    try:
        from data.emotion_scales import melody_scale_intervals_for_emotion

        intervals = list(melody_scale_intervals_for_emotion(getattr(plan, "emotion", None)) or [])
    except Exception:
        intervals = []
    if not intervals:
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

    try:
        indices = sorted(
            (i for i, ev in enumerate(out) if isinstance(ev, tuple) and len(ev) == 6 and int(ev[0]) == int(channel)),
            key=lambda i: float(out[i][3]),
        )
    except Exception:
        return out
    if len(indices) < 2:
        return out

    cap = max(5, min(10, int(max_interval)))

    def _target_pcs_for_bar(bar: int, cur_pc: int) -> set[int]:
        pcs = set(chord_pcs_by_bar[bar] if 0 <= int(bar) < bars else set())
        if scale_pcs and pcs:
            both = {int(pc) for pc in pcs if int(pc) in scale_pcs}
            if both:
                pcs = both
        if not pcs and scale_pcs:
            pcs = set(scale_pcs)
        return {int(pc) for pc in pcs if int(pc) != int(cur_pc)}

    def _candidate(cur: int, prev_pitch: int, next_pitch: Optional[int], pcs: set[int]) -> Optional[int]:
        cands = []
        for pc in sorted(int(x) % 12 for x in pcs):
            for octave in range(-3, 4):
                base = (int(cur) // 12) * 12 + int(pc) + 12 * int(octave)
                for cand in (base, base - 12):
                    try:
                        c = int(RANGE_LIMITER.clamp_note(int(cand), int(channel)))
                    except Exception:
                        c = int(cand)
                    if int(c) == int(cur):
                        continue
                    interval = abs(int(c) - int(prev_pitch))
                    if interval > cap:
                        continue
                    move = abs(int(c) - int(cur))
                    if move > 7:
                        continue
                    cost = interval + move * 2
                    if next_pitch is not None:
                        cost += max(0, abs(int(next_pitch) - int(c)) - cap) * 3
                    cands.append((cost, move, interval, int(c)))
        if not cands:
            return None
        cands.sort(key=lambda t: (t[0], t[1], t[2]))
        return int(cands[0][3])

    for pos in range(1, len(indices)):
        prev_idx = indices[pos - 1]
        cur_idx = indices[pos]
        try:
            prev = int(out[prev_idx][1])
            cur = int(out[cur_idx][1])
            st = float(out[cur_idx][3])
        except Exception:
            continue
        if abs(int(cur) - int(prev)) <= cap:
            continue
        bar = int(st // bpb)
        pcs = _target_pcs_for_bar(bar, int(cur) % 12)
        if not pcs:
            continue
        next_pitch = None
        if pos + 1 < len(indices):
            try:
                next_pitch = int(out[indices[pos + 1]][1])
            except Exception:
                next_pitch = None
        new_midi = _candidate(int(cur), int(prev), next_pitch, pcs)
        if new_midi is None:
            continue
        try:
            ch_e, _m, vel, st, dur, notes = out[cur_idx]
            new_notes = list(notes or [])
            if new_notes:
                new_notes[0] = int(new_midi)
            else:
                new_notes = [int(new_midi)]
            out[cur_idx] = (ch_e, int(new_midi), int(vel), float(st), float(dur), new_notes)
        except Exception:
            continue
    return out