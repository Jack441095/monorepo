# composition/song_postprocess/_common.py

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


Event = Tuple[Any, Any, Any, Any, Any, Any]


def _lead_pitch(ev: Sequence[Any]) -> Optional[int]:
    if not ev or len(ev) != 6:
        return None
    try:
        if int(ev[0]) != 2:
            return None
        notes = ev[5]
        if isinstance(notes, list) and notes:
            return int(notes[0])
        return int(ev[1])
    except Exception:
        return None


def _clamp_lead_pitch(midi: int) -> int:
    return int(max(48, min(84, int(midi))))


def _section_starts(section_bars: Sequence[int], *, beats_per_bar: float) -> List[float]:
    starts: List[float] = []
    acc = 0.0
    for bars in list(section_bars or []):
        starts.append(float(acc))
        try:
            acc += float(int(bars)) * float(beats_per_bar)
        except Exception:
            acc += float(beats_per_bar)
    return starts


def _lead_between(events: Sequence[Event], start: float, end: float) -> List[Tuple]:
    rows: List[Tuple] = []
    for ev in events:
        if _lead_pitch(ev) is None:
            continue
        try:
            st = float(ev[3])
            dur = float(ev[4])
        except Exception:
            continue
        if st < float(end) - 1e-6 and (st + dur) > float(start) + 1e-6:
            rows.append(tuple(ev))
    rows.sort(key=lambda e: float(e[3]))
    return rows


def _rhythm_bucket(value: float) -> float:
    try:
        v = max(0.125, min(4.0, float(value)))
    except Exception:
        v = 0.5
    if v <= 0.25 + 1e-9:
        return 0.25
    if v <= 0.5 + 1e-9:
        return 0.5
    if v <= 1.0 + 1e-9:
        return 1.0
    if v <= 2.0 + 1e-9:
        return 2.0
    return 4.0


def _select_reprise_motif_cell(
    candidates: Sequence[Tuple[float, float, int, int]],
    *,
    strength: float,
    beats_per_bar: float,
    hook_target: bool,
) -> Tuple[List[Tuple[float, float, int, int]], Dict[str, Any]]:
    """Pick the most memorable contiguous source cell for full-song reprises."""

    rows = [(float(a), float(b), int(c), int(d)) for a, b, c, d in list(candidates or [])]
    if len(rows) < 3:
        return list(rows), {"cell_start": 0, "cell_notes": int(len(rows)), "cell_score": 0.0}

    s = max(0.0, min(1.0, float(strength)))
    max_len = min(8 if hook_target else 6, len(rows))
    target_len = 6 if s >= 0.88 and hook_target else (5 if hook_target else 4)
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0

    best_rows = list(rows[: min(max_len, len(rows))])
    best_meta: Dict[str, Any] = {"cell_start": 0, "cell_notes": int(len(best_rows)), "cell_score": -1e9}

    for start_i in range(0, len(rows) - 2):
        for length in range(3, max_len + 1):
            end_i = int(start_i) + int(length)
            if end_i > len(rows):
                continue
            cell = rows[start_i:end_i]
            rel0 = float(cell[0][0])
            span_beats = float(cell[-1][0]) + float(cell[-1][1]) - float(cell[0][0])
            if span_beats > (3.0 * bpb if hook_target else 2.5 * bpb) + 1e-6:
                continue
            pitches = [int(rp) for _rs, _dur, rp, _vel in cell]
            durs = [_rhythm_bucket(float(dur)) for _rs, dur, _rp, _vel in cell]
            intervals = [abs(int(b) - int(a)) for a, b in zip(pitches, pitches[1:])]
            if not intervals:
                continue
            pitch_span = max(pitches) - min(pitches)
            total_motion = sum(int(v) for v in intervals)
            unique_pitches = len(set(pitches))
            if pitch_span <= 1 or total_motion <= 1 or unique_pitches <= 1:
                continue
            step_frac = sum(1 for iv in intervals if int(iv) <= 2) / float(len(intervals))
            zero_intervals = sum(1 for iv in intervals if int(iv) == 0)
            leap_penalty = sum(max(0, int(iv) - 7) for iv in intervals)
            rhythm_vocab = len(set(durs))
            rhythm_repeat = 1.0 - min(1.0, max(0, rhythm_vocab - 1) / 5.0)
            length_fit = 1.0 - min(1.0, abs(float(length) - float(target_len)) / max(1.0, float(target_len)))
            downbeat_bonus = 1.0 if abs((rel0 % bpb) - 0.0) <= 0.08 else 0.0
            score = 1.0
            score += 0.28 * float(min(length, 6))
            score += 0.30 * float(unique_pitches)
            score += 0.32 * float(step_frac)
            score += 0.22 * float(rhythm_repeat)
            score += 0.26 * float(length_fit)
            score += 0.18 * float(downbeat_bonus)
            score -= 0.46 * float(zero_intervals)
            score -= 0.18 * float(leap_penalty)
            score -= 0.05 * float(start_i)
            score -= 0.015 * float(max(0.0, rel0))
            if score > float(best_meta["cell_score"]):
                best_rows = list(cell)
                best_meta = {
                    "cell_start": int(start_i),
                    "cell_notes": int(length),
                    "cell_score": float(score),
                    "cell_span_beats": float(span_beats),
                    "cell_pitch_span": int(pitch_span),
                }

    # Normalize the chosen cell so reprises enter at the target section opening.
    if best_rows:
        offset = float(best_rows[0][0])
        pitch_offset = int(best_rows[0][2])
        best_rows = [
            (float(rs) - float(offset), float(dur), int(rp) - int(pitch_offset), int(vel))
            for rs, dur, rp, vel in list(best_rows)
        ]
    return list(best_rows), dict(best_meta)


def _theme_cell_identity_score(cell: Sequence[Tuple[float, float, int, int]], meta: Dict[str, Any]) -> float:
    rows = [(float(a), float(b), int(c), int(d)) for a, b, c, d in list(cell or [])]
    if len(rows) < 3:
        return 0.0
    try:
        base_score = float(meta.get("cell_score", 0.0) or 0.0)
    except Exception:
        base_score = 0.0
    offsets = [int(rp) for _rs, _dur, rp, _vel in rows]
    intervals = [abs(int(b) - int(a)) for a, b in zip(offsets, offsets[1:])]
    pitch_span = max(offsets) - min(offsets) if offsets else 0
    unique_pitches = len(set(offsets))
    unique_rhythms = len({_rhythm_bucket(float(dur)) for _rs, dur, _rp, _vel in rows})
    repeated_offsets = max(0, len(offsets) - unique_pitches)
    return float(base_score) + 0.18 * float(pitch_span) + 0.16 * float(unique_rhythms) - 0.24 * float(repeated_offsets) + 0.08 * float(sum(1 for iv in intervals if 1 <= int(iv) <= 5))


def _blend_theme_cell_with_planned_profile(
    extracted_cell: Sequence[Tuple[float, float, int, int]],
    extracted_meta: Dict[str, Any],
    planned_cell: Sequence[Tuple[float, float, int, int]],
    *,
    strength: float,
) -> Tuple[List[Tuple[float, float, int, int]], Dict[str, Any]]:
    """Fuse generated phrase DNA with the emotion profile when the source hook is weak."""

    extracted = [(float(a), float(b), int(c), int(d)) for a, b, c, d in list(extracted_cell or [])]
    planned = [(float(a), float(b), int(c), int(d)) for a, b, c, d in list(planned_cell or [])]
    if not planned:
        meta = dict(extracted_meta or {})
        meta["theme_source"] = "extracted"
        return list(extracted), meta
    if not extracted:
        meta = dict(extracted_meta or {})
        meta["theme_source"] = "planned"
        return list(planned), meta

    identity_score = _theme_cell_identity_score(extracted, dict(extracted_meta or {}))
    try:
        pitch_span = int(extracted_meta.get("cell_pitch_span", 0) or 0)
    except Exception:
        pitch_span = 0
    source_is_weak = bool(identity_score < 4.0 or pitch_span <= 2 or len(extracted) < 5)
    s = max(0.0, min(1.0, float(strength)))

    if source_is_weak:
        chosen = list(planned)
        source = "planned"
    else:
        count = min(max(len(planned), 4), min(8, max(len(extracted), len(planned))))
        chosen = []
        for i in range(count):
            prs, pdur, prp, pvel = planned[min(i, len(planned) - 1)]
            ers, edur, erp, evel = extracted[min(i, len(extracted) - 1)]
            # Profile rhythm keeps hook shape clear; extracted pitch keeps song-specific DNA.
            rel_start = float(prs if s >= 0.62 else ers)
            dur = float(pdur if s >= 0.62 else edur)
            rel_pitch = int(round((0.58 * int(erp)) + (0.42 * int(prp))))
            vel = int(round((int(evel) + int(pvel)) / 2.0))
            chosen.append((float(rel_start), max(0.18, min(1.5, float(dur))), int(rel_pitch), int(vel)))
        # Preserve the planned cadence so the emotional family remains audible.
        if chosen and planned:
            last = planned[min(len(chosen), len(planned)) - 1]
            prs, pdur, prp, pvel = last
            chosen[-1] = (float(chosen[-1][0]), float(chosen[-1][1] or pdur), int(prp), int(chosen[-1][3] or pvel))
        source = "blended"

    meta = dict(extracted_meta or {})
    meta["theme_source"] = str(source)
    meta["extracted_identity_score"] = float(identity_score)
    meta["planned_profile_used"] = bool(source != "extracted")
    return list(chosen), meta


def _build_chord_windows(events: Sequence[Event]) -> List[Tuple[float, float, set[int]]]:
    rows: List[Tuple[float, float, set[int]]] = []
    for ev in events:
        if not ev or len(ev) != 6:
            continue
        try:
            if int(ev[0]) != 1:
                continue
            st = float(ev[3])
            dur = float(ev[4])
            notes = ev[5]
        except Exception:
            continue
        if dur <= 1e-6 or not isinstance(notes, list):
            continue
        pcs = {int(n) % 12 for n in notes if isinstance(n, int)}
        if pcs:
            rows.append((float(st), float(st) + float(dur), set(pcs)))
    rows.sort(key=lambda x: (float(x[0]), float(x[1])))
    return rows


def _active_chord_pcs_at(
    chord_windows: Sequence[Tuple[float, float, set[int]]],
    start_beat: float,
    *,
    beats_per_bar: float,
) -> set[int]:
    t = float(start_beat)
    for st, en, pcs in chord_windows:
        if float(st) - 1e-6 <= t <= float(en) + 1e-6:
            return set(pcs)
    if chord_windows:
        try:
            bar_start = float(int(t // float(beats_per_bar)) * float(beats_per_bar))
            bar_end = bar_start + float(beats_per_bar)
            for st, _en, pcs in chord_windows:
                if bar_start - 1e-6 <= float(st) < bar_end + 1e-6:
                    return set(pcs)
        except Exception:
            pass
    return set()


def _nearest_pitch_for_pcs(midi: int, pcs: set[int]) -> int:
    target = int(midi)
    best = target
    best_dist = 10**9
    for cand in range(int(target) - 12, int(target) + 13):
        if int(cand) % 12 not in pcs:
            continue
        dist = abs(int(cand) - int(target))
        if dist < best_dist:
            best_dist = dist
            best = int(cand)
    return int(best)


def _reharmonize_inserted_lead_pitch(
    midi: int,
    *,
    start_beat: float,
    duration_beats: float,
    chord_windows: Sequence[Tuple[float, float, set[int]]],
    beats_per_bar: float,
    force: bool = False,
) -> int:
    pcs = _active_chord_pcs_at(chord_windows, float(start_beat), beats_per_bar=float(beats_per_bar))
    if not pcs:
        return _clamp_lead_pitch(int(midi))
    local_beat = float(start_beat) % float(beats_per_bar if beats_per_bar > 1e-9 else 4.0)
    strong = abs(local_beat - 0.0) <= 0.08 or abs(local_beat - 2.0) <= 0.08
    long_note = float(duration_beats) >= 0.5 - 1e-9
    pitch = int(midi)
    if bool(force) or bool(strong) or bool(long_note) or (int(pitch) % 12) not in pcs:
        pitch = _nearest_pitch_for_pcs(int(pitch), set(pcs))
    return _clamp_lead_pitch(int(pitch))


def _scale_emotion_name_for_section(
    *,
    section_emotions: Sequence[str],
    section_index: int,
    primary_emotion: str = "",
) -> str:
    """Prefer the song primary adjective for scale locks (not arc-colored sections)."""
    try:
        from data.emotion_aliases import canonical_emotion_name

        primary = canonical_emotion_name(str(primary_emotion or ""))
    except Exception:
        primary = str(primary_emotion or "").strip().lower()
    if primary:
        return str(primary)
    return str(list(section_emotions)[int(section_index)])


def _emotion_scale_pcs_for_section(
    *,
    emotion_name: str,
    root_note: int,
) -> set[int]:
    try:
        from data.music_data import EMOTION_BY_NAME
        from data.emotion_scales import melody_scale_intervals_for_emotion

        emo = EMOTION_BY_NAME.get(str(emotion_name or "").strip().lower())
        intervals = list(melody_scale_intervals_for_emotion(emo) or []) if emo is not None else []
        if not intervals and emo is not None:
            intervals = list(getattr(emo, "scale_intervals", []) or [])
    except Exception:
        intervals = []
    try:
        root_pc = int(root_note) % 12
        return {(int(root_pc) + int(iv)) % 12 for iv in list(intervals or [])}
    except Exception:
        return set()


def _snap_inserted_pitch_to_section_scale(
    midi: int,
    *,
    scale_pcs: set[int],
    chord_pcs: set[int],
) -> int:
    if not scale_pcs or int(midi) % 12 in scale_pcs:
        return _clamp_lead_pitch(int(midi))

    target = int(midi)
    cands: List[Tuple[float, int]] = []
    for cand in range(int(target) - 12, int(target) + 13):
        if int(cand) < 48 or int(cand) > 84:
            continue
        if int(cand) % 12 not in scale_pcs:
            continue
        move = abs(int(cand) - int(target))
        chord_cost = 0.0 if not chord_pcs or int(cand) % 12 in chord_pcs else 0.65
        cands.append((float(move) + float(chord_cost), int(cand)))
    if not cands:
        for cand in range(48, 85):
            if int(cand) % 12 not in scale_pcs:
                continue
            move = abs(int(cand) - int(target))
            chord_cost = 0.0 if not chord_pcs or int(cand) % 12 in chord_pcs else 0.65
            cands.append((float(move) + float(chord_cost), int(cand)))
    if not cands:
        return _clamp_lead_pitch(int(midi))
    cands.sort(key=lambda item: (float(item[0]), abs(int(item[1]) - int(target))))
    return int(cands[0][1])


def _nearest_scale_pitch(
    midi: int,
    *,
    scale_pcs: set[int],
    prefer_direction: int = 0,
) -> int:
    if not scale_pcs:
        return _clamp_lead_pitch(int(midi))
    target = _clamp_lead_pitch(int(midi))
    cands: List[Tuple[float, int]] = []
    for cand in range(int(target) - 12, int(target) + 13):
        if int(cand) < 48 or int(cand) > 84:
            continue
        if int(cand) % 12 not in scale_pcs:
            continue
        direction_penalty = 0.0
        if int(prefer_direction) < 0 and int(cand) > int(target):
            direction_penalty = 0.35
        elif int(prefer_direction) > 0 and int(cand) < int(target):
            direction_penalty = 0.35
        cands.append((abs(int(cand) - int(target)) + direction_penalty, int(cand)))
    if not cands:
        return _clamp_lead_pitch(int(midi))
    cands.sort(key=lambda item: (float(item[0]), abs(int(item[1]) - int(target))))
    return int(cands[0][1])


def _emotion_contour_bias(emotion_name: str, role: str) -> Tuple[int, float]:
    emo = str(emotion_name or "").strip().lower()
    role0 = str(role or "").strip().lower()
    if emo in {"grief", "remorse"}:
        return (-3 if role0 in {"b", "chorus", "hook", "tag"} else -2, 0.36)
    if emo == "sadness":
        return (-3 if role0 in {"b", "chorus", "hook", "tag"} else -2, 0.40)
    descending = {
        "disappointment", "disapproval",
        "disgust", "embarrassment", "annoyance",
    }
    sighing = {"caring", "love", "desire", "relief", "gratitude", "admiration"}
    lifting = {"joy", "amusement", "excitement", "optimism", "pride", "approval", "surprise"}
    uncertain = {"fear", "nervousness", "confusion", "curiosity", "realization"}
    if emo in descending:
        return (-2 if role0 in {"b", "chorus", "hook", "tag"} else -1, 0.58)
    if emo in sighing:
        return (-1, 0.66)
    if emo in lifting:
        return (2 if role0 in {"b", "chorus", "hook", "tag"} else 1, 0.62)
    if emo in uncertain:
        return (-1, 0.72)
    if emo == "anger":
        return (-1 if role0 in {"b", "chorus", "hook", "tag"} else 0, 0.54)
    return (0, 1.1)


def _primary_register_center_offset(primary_emotion: str) -> int:
    """Shift professionalizer target registers so opposite-valence songs diverge."""
    emo = str(primary_emotion or "").strip().lower()
    if not emo:
        return 0
    try:
        from data.melody_emotion_profiles import melody_emotion_profile_for_emotion

        prof = melody_emotion_profile_for_emotion(emo)
        shift = int(getattr(prof, "register_shift_semitones", 0) or 0)
        valence = float(getattr(prof, "valence", 0.0) or 0.0)
    except Exception:
        return 0
    # Generation already applies full register_shift; professionalizer only nudges centers.
    profile_nudge = int(round(float(shift) * 0.35))
    valence_nudge = int(round(float(valence) * 5.0))
    return int(max(-9, min(9, profile_nudge + valence_nudge)))


