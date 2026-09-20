# ai/markov/melody/generation/phrase_generation.py
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ai.markov.melody.contour import recompute_beat_positions
from ai.markov.melody.embellishments import apply_embellishments
from ai.markov.melody.generation.phrase_scoring import (
    melody_accept_heuristic,
    score_phrase_candidate,
)
from ai.markov.melody.utils import build_chord_weights_per_bar
from data.emotion_melody_priors import emotion_melody_prior_for

logger = logging.getLogger(__name__)


def _degree_step_toward(source: int, target: int) -> int:
    src = int(source) % 7
    tgt = int(target) % 7
    up = (tgt - src) % 7
    down = (src - tgt) % 7
    if up == 0 and down == 0:
        return 0
    return 1 if up <= down else -1


def _phrase_motion_stats(tokens: List[Tuple[int, float]]) -> Tuple[float, int]:
    degrees = [int(d) % 7 for d, _dur in list(tokens or []) if isinstance(d, int) and int(d) >= 0]
    if len(degrees) < 2:
        return 0.0, len(degrees)
    intervals = [((degrees[i] - degrees[i - 1] + 3) % 7) - 3 for i in range(1, len(degrees))]
    movement_rate = sum(1 for iv in intervals if int(iv) != 0) / float(max(1, len(intervals)))
    run = 1
    max_run = 1
    for prev, cur in zip(degrees, degrees[1:]):
        if int(prev) == int(cur):
            run += 1
        else:
            max_run = max(max_run, run)
            run = 1
    max_run = max(max_run, run)
    return float(movement_rate), int(max_run)


def _arc_target_for_position(plan, pos: float, fallback: int) -> int:
    try:
        waypoints = list(getattr(plan, "arc_waypoints", None) or [])
    except Exception:
        waypoints = []
    if waypoints:
        try:
            p = max(0.0, min(1.0, float(pos)))
            _wp_pos, wp_degree, _strength = min(
                waypoints,
                key=lambda row: abs(float(row[0]) - p),
            )
            return int(wp_degree) % 7
        except Exception:
            pass
    if pos >= 0.78 and getattr(plan, "pre_cadence_degree", None) is not None:
        return int(getattr(plan, "pre_cadence_degree")) % 7
    if pos >= 0.52 and getattr(plan, "target_climax", None) is not None:
        return int(getattr(plan, "target_climax")) % 7
    if getattr(plan, "entry_degree", None) is not None:
        return int(getattr(plan, "entry_degree")) % 7
    return int(fallback) % 7


def _nearest_allowed_degree(degree: int, allowed: List[int]) -> int:
    current = int(degree) % 7
    if not allowed:
        return current
    return min(
        [int(a) % 7 for a in allowed],
        key=lambda cand: (min(abs(cand - current), 7 - abs(cand - current)), abs(cand - current)),
    )


_CHORUS_SECTION_ROLES = frozenset({"b", "chorus", "hook", "tag"})


def _active_joint_hook_degrees(gen) -> List[int]:
    try:
        from audiogen_core.config import CONFIG

        if not bool(getattr(CONFIG.composition, "joint_plan_markov_conditioning_enabled", False)):
            return []
    except Exception:
        return []
    raw = getattr(gen, "_joint_hook_degrees", None) or []
    out: List[int] = []
    for item in list(raw):
        try:
            out.append(int(item) % 7)
        except Exception:
            continue
    return out


def _lock_chorus_pitch_cell(
    phrase: List[Tuple[int, float]],
    *,
    plan=None,
    gen=None,
) -> List[Tuple[int, float]]:
    """Restrict chorus lead degrees to the joint-plan hook cell when enabled."""
    if not phrase:
        return phrase
    allowed = _active_joint_hook_degrees(gen)
    if len(allowed) < 2:
        return phrase
    try:
        role_lc = str(getattr(plan, "section_role", "") or "").strip().lower() if plan is not None else ""
    except Exception:
        role_lc = ""
    if role_lc not in _CHORUS_SECTION_ROLES:
        return phrase

    voiced_positions = [i for i, (d, _dur) in enumerate(phrase) if isinstance(d, int) and int(d) >= 0]
    if len(voiced_positions) < 2:
        return phrase

    out: List[Tuple[int, float]] = []
    for degree, dur in list(phrase or []):
        if not isinstance(degree, int) or int(degree) < 0:
            out.append((degree, float(dur)))
            continue
        deg = int(degree) % 7
        if deg in allowed:
            out.append((deg, float(dur)))
        else:
            out.append((int(_nearest_allowed_degree(deg, allowed)), float(dur)))
    return out


def _repair_static_phrase_motion(
    phrase: List[Tuple[int, float]],
    *,
    plan=None,
    emotion=None,
) -> List[Tuple[int, float]]:
    """Break over-flat phrase interiors while preserving rhythm and cadence."""

    if not phrase:
        return phrase
    out: List[Tuple[int, float]] = [(int(d), float(dur)) for d, dur in list(phrase or [])]
    voiced_idx = [i for i, (d, _dur) in enumerate(out) if int(d) >= 0]
    if len(voiced_idx) < 4:
        return out

    descending_pull = False
    repeat_mult = 1.0
    try:
        emotion_name = str(getattr(emotion, "name", None) or emotion or "")
        prior = emotion_melody_prior_for(emotion_name)
        base_dir = 1 if float(prior.ascending_mult) >= float(prior.descending_mult) else -1
        descending_pull = float(prior.descending_mult) >= float(prior.ascending_mult) * 1.10
        repeat_mult = float(prior.repeat_mult)
    except Exception:
        base_dir = 1
    movement_rate, max_run = _phrase_motion_stats(out)
    # v012b+: annoyance/confusion still show elevated repeat rates. Make phrase-level
    # static-run breaking stricter for those (and for low repeat_mult in general).
    try:
        en = str(emotion_name).strip().lower()
    except Exception:
        en = ""
    target_max_run = 2 if repeat_mult <= 0.82 else 4
    if en in {"annoyance", "confusion"}:
        target_max_run = 2
    # v012d: a few emotions still show rare very-long static runs in full diagnostics.
    # These aren't "repeat-prone" in the same way; they just occasionally get stuck.
    # Tighten max-run and move sooner only when the phrase is actually stuck.
    if en in {"neutral", "realization", "gratitude", "desire", "grief", "embarrassment"} and int(max_run) >= 5:
        target_max_run = min(int(target_max_run), 3)
    if movement_rate >= 0.30 and max_run <= target_max_run:
        return out
    contour = str(getattr(plan, "contour", "") or "").strip().lower()
    if contour == "asc":
        base_dir = 1
    elif contour == "desc":
        base_dir = -1

    run_len = 1
    last_degree = int(out[voiced_idx[0]][0]) % 7

    # v012e: if the phrase *starts* with a long static run, the main loop below
    # can miss it because it preserves the first voiced note and cadence note.
    # Break the entry run early (only for the long-static-run bucket set).
    if en in {"neutral", "realization", "gratitude", "desire", "grief"} and int(max_run) >= 5:
        try:
            if len(voiced_idx) >= 4:
                d0 = int(out[voiced_idx[0]][0]) % 7
                d1 = int(out[voiced_idx[1]][0]) % 7
                d2 = int(out[voiced_idx[2]][0]) % 7
                if d0 == d1 == d2:
                    contour_dir0 = 1
                    contour0 = str(getattr(plan, "contour", "") or "").strip().lower()
                    if contour0 == "desc":
                        contour_dir0 = -1
                    elif contour0 == "asc":
                        contour_dir0 = 1
                    elif contour0 == "arch":
                        contour_dir0 = 1
                    else:
                        contour_dir0 = int(base_dir)
                    out[voiced_idx[1]] = (int((d0 + int(contour_dir0)) % 7), float(out[voiced_idx[1]][1]))
        except Exception:
            pass
    for local_pos, idx in enumerate(voiced_idx[1:-1], start=1):
        total_steps = max(1, len(voiced_idx) - 1)
        pos = float(local_pos) / float(total_steps)
        prev_idx = voiced_idx[local_pos - 1]
        prev_degree = int(out[prev_idx][0]) % 7
        cur_degree = int(out[idx][0]) % 7
        if cur_degree == last_degree:
            run_len += 1
        else:
            run_len = 1
        last_degree = cur_degree

        if contour == "arch":
            contour_dir = 1 if pos < 0.55 else -1
        elif contour == "static":
            contour_dir = 1 if (local_pos % 2) else -1
        else:
            contour_dir = int(base_dir)
        target = _arc_target_for_position(plan, pos, cur_degree)
        target_dir = _degree_step_toward(prev_degree, target)
        if descending_pull and pos >= 0.30 and contour in {"asc", "arch", "static"} and target_dir >= 0:
            target_dir = -1
        step_dir = target_dir if target_dir != 0 else contour_dir

        if en in {"annoyance", "confusion"}:
            should_move = run_len >= 2 or (movement_rate < 0.33 and local_pos % 2 == 0)
        elif en in {"neutral", "realization", "gratitude", "desire", "grief", "embarrassment"} and int(max_run) >= 5:
            should_move = run_len >= 2 or (movement_rate < 0.30 and local_pos % 2 == 0)
        else:
            should_move = run_len >= 3 or (movement_rate < 0.30 and local_pos % 2 == 0)
        if should_move and step_dir:
            out[idx] = (int((prev_degree + int(step_dir)) % 7), float(out[idx][1]))
            run_len = 1

    # A second deterministic pass catches phrases like 4-4-4-4 where the
    # first pass could still leave a long held target after cadence steering.
    movement_rate, max_run = _phrase_motion_stats(out)
    if movement_rate < 0.25 or max_run > 4:
        for local_pos, idx in enumerate(voiced_idx[2:-1], start=2):
            prev_idx = voiced_idx[local_pos - 1]
            if int(out[idx][0]) % 7 != int(out[prev_idx][0]) % 7:
                continue
            pos = float(local_pos) / float(max(1, len(voiced_idx) - 1))
            direction = int(base_dir)
            if contour == "arch":
                direction = 1 if pos < 0.55 else -1
            elif contour == "static":
                direction = 1 if (local_pos % 2) else -1
            target = _arc_target_for_position(plan, pos, int(out[idx][0]))
            target_dir = _degree_step_toward(int(out[prev_idx][0]), target)
            if descending_pull and pos >= 0.30 and contour in {"asc", "arch", "static"} and target_dir >= 0:
                target_dir = -1
            if target_dir:
                direction = target_dir
            out[idx] = (int((int(out[prev_idx][0]) + int(direction)) % 7), float(out[idx][1]))

    # v012e: final sweep for the long-static-run bucket set. If we still have a
    # very long static run, break it even if it spans earlier indices.
    if en in {"neutral", "realization", "gratitude", "desire", "grief", "embarrassment"}:
        _mv, _mr = _phrase_motion_stats(out)
        if int(_mr) >= 5:
            try:
                last = int(out[voiced_idx[0]][0]) % 7
                rlen = 1
                for j in range(1, len(voiced_idx) - 1):
                    ii = voiced_idx[j]
                    cur = int(out[ii][0]) % 7
                    if cur == last:
                        rlen += 1
                    else:
                        rlen = 1
                    last = cur
                    # For a subset that is still tripping diagnostics, break sooner.
                    rlen_thr = 2 if en in {"realization", "embarrassment", "desire"} else 3
                    if rlen >= int(rlen_thr):
                        prev = int(out[voiced_idx[j - 1]][0]) % 7
                        direction = 1 if int(base_dir) >= 0 else -1
                        out[ii] = (int((prev + int(direction)) % 7), float(out[ii][1]))
                        rlen = 1
            except Exception:
                pass

    return out


def _merge_repeated_short_notes_for_long_breath(
    phrase: List[Tuple[int, float]],
    *,
    emotion=None,
) -> List[Tuple[int, float]]:
    if not phrase:
        return phrase
    try:
        emotion_name = str(getattr(emotion, "name", None) or emotion or "")
        prior = emotion_melody_prior_for(emotion_name)
        long_breathed = float(prior.long_rhythm_mult) >= float(prior.short_rhythm_mult) * 1.20
    except Exception:
        long_breathed = False
        emotion_name = ""
    if not long_breathed:
        # v012_emotion_calibration: some tender emotions are only barely missing
        # the long-breath target; give them a mild merge assist.
        tender_assist = {"love", "sadness", "desire", "remorse"}
        # v012b: admiration/neutral are still slightly short-heavy in diagnostics;
        # allow a gentle assist here too.
        borderline_assist = {"admiration", "neutral"}
        try:
            en = str(emotion_name).strip().lower()
            if en in tender_assist or en in borderline_assist:
                long_breathed = True
        except Exception:
            long_breathed = False
        if not long_breathed:
            return phrase

    out: List[Tuple[int, float]] = []
    # Slightly more permissive merge for the assisted set (still capped so phrases
    # don’t turn into one giant held note).
    assist_more = False
    assist_borderline = False
    try:
        en = str(emotion_name).strip().lower()
        assist_more = en in {"love", "sadness", "desire", "remorse"}
        assist_borderline = en in {"admiration", "neutral"}
    except Exception:
        assist_more = False
        assist_borderline = False
    max_merge = 2.25 if assist_more else 2.0
    max_prev = 1.75 if assist_more else 1.5
    max_added = 0.90 if assist_more else 0.75
    if assist_borderline and not assist_more:
        max_merge = 2.10
        max_prev = 1.60
        max_added = 0.80
    for degree, duration in list(phrase or []):
        d = int(degree)
        dur = float(duration)
        if (
            out
            and d >= 0
            and int(out[-1][0]) == d
            and float(out[-1][1]) <= float(max_prev) + 1e-9
            and dur <= float(max_added) + 1e-9
            and float(out[-1][1]) + dur <= float(max_merge) + 1e-9
        ):
            out[-1] = (int(out[-1][0]), float(out[-1][1]) + float(dur))
        else:
            out.append((int(d), float(dur)))
    return out


def _tilt_rising_motion_for_emotion(
    phrase: List[Tuple[int, float]],
    *,
    emotion=None,
) -> List[Tuple[int, float]]:
    """Strengthen rising identity for emotions that should arc upward."""
    if not phrase:
        return phrase
    try:
        emotion_name = str(getattr(emotion, "name", None) or emotion or "")
        prior = emotion_melody_prior_for(emotion_name)
        wants_rise = float(prior.ascending_mult) > float(prior.descending_mult) * 1.12
    except Exception:
        wants_rise = False
        emotion_name = ""
    # v012: explicitly assist the known weak rising buckets.
    try:
        if str(emotion_name).strip().lower() in {"pride", "amusement", "optimism"}:
            wants_rise = True
    except Exception:
        pass
    if not wants_rise:
        return phrase

    out: List[Tuple[int, float]] = [(int(d), float(dur)) for d, dur in list(phrase or [])]
    voiced_idx = [i for i, (d, _dur) in enumerate(out) if int(d) >= 0]
    if len(voiced_idx) < 4:
        return out
    degrees = [int(out[i][0]) for i in voiced_idx]
    asc = sum(1 for i in range(1, len(degrees)) if int(degrees[i]) > int(degrees[i - 1]))
    desc = sum(1 for i in range(1, len(degrees)) if int(degrees[i]) < int(degrees[i - 1]))
    if asc > desc:
        return out

    # Nudge interior notes upward in small steps while preserving the final cadence.
    last_fixed = int(out[voiced_idx[-1]][0])
    for local_pos in range(1, len(voiced_idx) - 1):
        prev_idx = voiced_idx[local_pos - 1]
        cur_idx = voiced_idx[local_pos]
        prev_degree = int(out[prev_idx][0])
        cur_degree = int(out[cur_idx][0])
        if cur_degree <= prev_degree and prev_degree < 6:
            out[cur_idx] = (min(6, int(prev_degree) + 1), float(out[cur_idx][1]))
    out[voiced_idx[-1]] = (int(last_fixed), float(out[voiced_idx[-1]][1]))
    return out


def _pride_broad_arc_smoothing(
    phrase: List[Tuple[int, float]],
    *,
    plan=None,
    emotion=None,
) -> List[Tuple[int, float]]:
    """Pride-specific broad upward arcs: reduce jaggedness and long static holds."""
    if not phrase:
        return phrase
    try:
        emotion_name = str(getattr(emotion, "name", None) or emotion or "")
    except Exception:
        emotion_name = ""
    if str(emotion_name).strip().lower() != "pride":
        return phrase

    out: List[Tuple[int, float]] = [(int(d), float(dur)) for d, dur in list(phrase or [])]
    voiced_idx = [i for i, (d, _dur) in enumerate(out) if int(d) >= 0]
    if len(voiced_idx) < 5:
        return out
    movement_rate, max_run = _phrase_motion_stats(out)
    if movement_rate >= 0.30 and max_run <= 4:
        return out

    contour = str(getattr(plan, "contour", "") or "").strip().lower()
    if contour in {"desc"}:
        return out

    # Create a slow staircase upward across the phrase interior.
    last_fixed = int(out[voiced_idx[-1]][0])
    step_every = 2
    for local_pos in range(1, len(voiced_idx) - 1):
        if local_pos % step_every != 0:
            continue
        prev_idx = voiced_idx[local_pos - 1]
        cur_idx = voiced_idx[local_pos]
        prev_degree = int(out[prev_idx][0])
        cur_degree = int(out[cur_idx][0])
        if cur_degree == prev_degree and prev_degree < 6:
            out[cur_idx] = (min(6, int(prev_degree) + 1), float(out[cur_idx][1]))

    out = _repair_static_phrase_motion(out, plan=plan, emotion=emotion)
    out = _tilt_rising_motion_for_emotion(out, emotion=emotion)
    out[voiced_idx[-1]] = (int(last_fixed), float(out[voiced_idx[-1]][1]))
    return out


def _apply_signature_leap_if_needed(
    phrase: List[Tuple[int, float]],
    *,
    emotion=None,
) -> List[Tuple[int, float]]:
    if not phrase:
        return phrase
    try:
        emotion_name = str(getattr(emotion, "name", None) or emotion or "")
        prior = emotion_melody_prior_for(emotion_name)
        wants_leap = float(prior.interval_large_leap_mult) > 1.14
    except Exception:
        wants_leap = False
        prior = None
    if not wants_leap:
        return phrase

    out: List[Tuple[int, float]] = [(int(d), float(dur)) for d, dur in list(phrase or [])]
    voiced_idx = [i for i, (d, _dur) in enumerate(out) if int(d) >= 0]
    if len(voiced_idx) < 4:
        return out
    degrees = [int(out[i][0]) for i in voiced_idx]
    if any(abs(int(degrees[i]) - int(degrees[i - 1])) >= 4 for i in range(1, len(degrees))):
        return out

    target_local = max(1, min(len(voiced_idx) - 2, int(round((len(voiced_idx) - 1) * 0.55))))
    idx = voiced_idx[target_local]
    prev_idx = voiced_idx[target_local - 1]
    prev_degree = int(out[prev_idx][0])
    try:
        prefer_up = float(prior.ascending_mult) >= float(prior.descending_mult)
    except Exception:
        prefer_up = True
    if prefer_up:
        target = 6 if prev_degree <= 2 else 0
    else:
        target = 0 if prev_degree >= 4 else 6
    if abs(int(target) - int(prev_degree)) < 4:
        target = 0 if target == 6 else 6
    if abs(int(target) - int(prev_degree)) >= 4:
        out[idx] = (int(target), float(out[idx][1]))
    return out


def _smooth_unwanted_large_leaps(
    phrase: List[Tuple[int, float]],
    *,
    emotion=None,
) -> List[Tuple[int, float]]:
    if not phrase:
        return phrase
    try:
        emotion_name = str(getattr(emotion, "name", None) or emotion or "")
        prior = emotion_melody_prior_for(emotion_name)
        smooth_large = float(prior.interval_large_leap_mult) < 0.70
    except Exception:
        smooth_large = False
    if not smooth_large:
        return phrase

    out: List[Tuple[int, float]] = [(int(d), float(dur)) for d, dur in list(phrase or [])]
    voiced_idx = [i for i, (d, _dur) in enumerate(out) if int(d) >= 0]
    if len(voiced_idx) < 3:
        return out

    for local_pos in range(1, len(voiced_idx)):
        prev_idx = voiced_idx[local_pos - 1]
        cur_idx = voiced_idx[local_pos]
        prev_degree = int(out[prev_idx][0])
        cur_degree = int(out[cur_idx][0])
        diff = int(cur_degree) - int(prev_degree)
        if abs(diff) < 4:
            continue

        if local_pos == len(voiced_idx) - 1 and local_pos >= 2:
            # Preserve final cadence target; smooth the approach note instead.
            before_idx = voiced_idx[local_pos - 2]
            before_degree = int(out[before_idx][0])
            candidates = [
                max(0, min(6, int(cur_degree) - 1)),
                max(0, min(6, int(cur_degree) + 1)),
                max(0, min(6, int(cur_degree) - 2)),
                max(0, min(6, int(cur_degree) + 2)),
            ]
            candidates = list(dict.fromkeys(candidates))
            replacement = min(candidates, key=lambda d: abs(int(d) - int(before_degree)))
            out[prev_idx] = (int(replacement), float(out[prev_idx][1]))
            continue

        direction = 1 if diff > 0 else -1
        replacement = int(prev_degree) + int(direction)
        replacement = max(0, min(6, int(replacement)))
        out[cur_idx] = (int(replacement), float(out[cur_idx][1]))
    return out


def _tilt_falling_motion_for_emotion(
    phrase: List[Tuple[int, float]],
    *,
    emotion=None,
) -> List[Tuple[int, float]]:
    if not phrase:
        return phrase
    try:
        emotion_name = str(getattr(emotion, "name", None) or emotion or "")
        prior = emotion_melody_prior_for(emotion_name)
        wants_fall = float(prior.descending_mult) > float(prior.ascending_mult) * 1.12
    except Exception:
        wants_fall = False
    if not wants_fall:
        return phrase

    out: List[Tuple[int, float]] = [(int(d), float(dur)) for d, dur in list(phrase or [])]
    voiced_idx = [i for i, (d, _dur) in enumerate(out) if int(d) >= 0]
    if len(voiced_idx) < 3:
        return out
    degrees = [int(out[i][0]) for i in voiced_idx]
    asc = sum(1 for i in range(1, len(degrees)) if int(degrees[i]) > int(degrees[i - 1]))
    desc = sum(1 for i in range(1, len(degrees)) if int(degrees[i]) < int(degrees[i - 1]))
    if desc > asc:
        return out

    first_idx = voiced_idx[0]
    if int(out[first_idx][0]) < 3:
        out[first_idx] = (min(6, int(out[first_idx][0]) + 3), float(out[first_idx][1]))

    for local_pos in range(1, len(voiced_idx) - 1):
        prev_idx = voiced_idx[local_pos - 1]
        cur_idx = voiced_idx[local_pos]
        prev_degree = int(out[prev_idx][0])
        cur_degree = int(out[cur_idx][0])
        if cur_degree >= prev_degree and prev_degree > 0:
            out[cur_idx] = (max(0, int(prev_degree) - 1), float(out[cur_idx][1]))
    return out


def generate_with_phrases(
    gen,
    phrase_contours: List[str],
    start_degree: int,
    notes_per_phrase: List[int],
    temperature: float = 1.0,
    emotion=None,
    chords: Optional[List[str]] = None,
    roots: Optional[List[int]] = None,
    bass_notes: Optional[List[int]] = None,
    total_beats: Optional[int] = None,
    target_melody_notes: Optional[List[int]] = None,
    *,
    section_role: Optional[str] = None,
    output_channel: int = 2,
    occupied_intervals: Optional[List[Tuple[float, float]]] = None,
    runtime_mode: Optional[str] = None,
    breath_window_by_bar: Optional[List[float]] = None,
    voiced_chords_per_bar: Optional[List[List[int]]] = None,
    bar_intent_by_bar: Optional[List[Dict]] = None,
) -> List[Tuple[int, float]]:
    """Generate melody using the composed modules."""
    melody = []
    current_degree = start_degree
    expected_total = sum(notes_per_phrase)

    # Ensure enough contours
    required = len(notes_per_phrase)
    if len(phrase_contours) < required:
        last = phrase_contours[-1] if phrase_contours else 'static'
        while len(phrase_contours) < required:
            phrase_contours.append(last)

    current_beat = 0.0
    beats_per_bar = 4.0
    grid = 0.25

    # Build a lightweight per-step occupancy weight map from occupied_intervals (e.g. arp bed).
    # This is used only for phrase-level rerank scoring (cheap, RT-safe).
    occ_step_weights: Dict[int, float] = {}
    if occupied_intervals:
        try:
            for item in list(occupied_intervals):
                if item is None:
                    continue
                try:
                    if isinstance(item, dict):
                        s0 = float(item.get("start", item.get("s")))
                        e0 = float(item.get("end", item.get("e")))
                        w = float(item.get("w", 1.0) or 1.0)
                    else:
                        seq = list(item)
                        if len(seq) < 2:
                            continue
                        s0 = float(seq[0])
                        e0 = float(seq[1])
                        w = float(seq[2]) if len(seq) >= 3 and seq[2] is not None else 1.0
                except Exception:
                    continue
                if e0 <= s0 + 1e-9:
                    continue
                w = max(0.0, min(1.25, float(w)))
                i0 = int(max(0, round(float(s0) / float(grid))))
                i1 = int(max(0, round(float(e0) / float(grid))))
                for i in range(i0, i1 + 1):
                    ii = int(i)
                    occ_step_weights[ii] = max(float(occ_step_weights.get(ii, 0.0)), float(w))
        except Exception:
            occ_step_weights = {}

    # Prepare chord weights per bar — must be indexed by bar number, not
    # phrase number.  Using phrase count here caused IndexErrors whenever
    # the number of bars exceeded the number of phrases.
    scale_iv = list(getattr(emotion, "scale_intervals", []) or []) if emotion else []
    chord_weights_per_bar = build_chord_weights_per_bar(
        list(chords) if chords else None,
        list(roots) if roots else None,
        scale_iv if scale_iv else None,
        voiced_chords_per_bar,
    )
    if not chord_weights_per_bar:
        n_bars = len(chords) if chords else 64
        chord_weights_per_bar = [{} for _ in range(max(1, int(n_bars)))]

    beat_positions = []
    all_intervals = []
    all_rhythms = []

    # Optional: composition-level per-bar intent (function/cadence/tension/etc.).
    # We keep this as an opaque list of dicts so the Markov layer does not
    # depend on composition dataclasses.
    intent_rows = list(bar_intent_by_bar or [])

    def _bar_intent(bar_idx: int) -> Optional[Dict]:
        if not intent_rows:
            return None
        try:
            i = int(bar_idx)
        except Exception:
            return None
        if i < 0 or i >= len(intent_rows):
            return None
        row = intent_rows[i]
        return row if isinstance(row, dict) else None

    # Per-bar temperature shaping from timeline intent (tension / melody activity).
    # This makes form arcs audible as "risk vs stability" in the Markov sampler.
    try:
        from audiogen_core.config import CONFIG

        t_on = bool(getattr(CONFIG.composition, "melody_bar_temperature_scaling_enabled", True))
        t_st = float(getattr(CONFIG.composition, "melody_bar_temperature_scaling_strength", 0.22) or 0.22)
        t_ref = float(getattr(CONFIG.composition, "melody_bar_temperature_tension_ref", 0.85) or 0.85)
        act_ref = float(getattr(CONFIG.composition, "melody_bar_temperature_activity_ref", 1.0) or 1.0)
        act_w = float(getattr(CONFIG.composition, "melody_bar_temperature_activity_weight", 0.12) or 0.12)
        t_min = float(getattr(CONFIG.composition, "melody_bar_temperature_mult_min", 0.80) or 0.80)
        t_max = float(getattr(CONFIG.composition, "melody_bar_temperature_mult_max", 1.35) or 1.35)
    except Exception:
        t_on = True
        t_st = 0.22
        t_ref = 0.85
        act_ref = 1.0
        act_w = 0.12
        t_min = 0.80
        t_max = 1.35
    t_st = max(0.0, min(1.0, float(t_st)))
    act_w = max(0.0, min(0.5, float(act_w)))
    t_min = max(0.35, min(2.0, float(t_min)))
    t_max = max(float(t_min), min(2.0, float(t_max)))

    def _temp_for_bar(bar_idx: int) -> float:
        if not t_on or t_st <= 1e-9:
            return float(temperature)
        row = _bar_intent(int(bar_idx)) or {}
        try:
            ten = float(row.get("tension", row.get("tension_target", row.get("tension_value", 0.85))) or 0.85)
        except Exception:
            ten = 0.85
        try:
            act = float(row.get("melody_activity_target", row.get("melody_density", row.get("melody_activity", 1.0))) or 1.0)
        except Exception:
            act = 1.0
        ten = max(0.0, min(1.35, float(ten)))
        act = max(0.0, min(2.25, float(act)))
        # Map (ten - ref) to a multiplier around 1.0.
        # Positive tension -> slightly higher temp; lower tension -> slightly lower temp.
        dt = float(ten) - float(t_ref)
        da = float(act) - float(act_ref)
        mult = 1.0 + float(t_st) * (0.90 * float(dt) + float(act_w) * float(da))
        mult = max(float(t_min), min(float(t_max), float(mult)))
        return float(temperature) * float(mult)

    # Optional: debug trace of intent + effective temperature.
    try:
        from audiogen_core.config import CONFIG

        trace_on = bool(getattr(CONFIG.composition, "debug_melody_intent_trace_enabled", False))
    except Exception:
        trace_on = False
    if trace_on:
        try:
            setattr(gen, "_debug_melody_intent_trace_by_bar", [])
        except Exception:
            pass

    # Generate phrase plans (handoff-aware).
    handoff_entry_degree = None
    try:
        # Composition layer may set this on the generator instance for live handoffs.
        ctx = getattr(gen, "transition_handoff_context", None) or getattr(gen, "_transition_handoff_context", None) or {}
        pc = ctx.get("previous_lead_pc")
        if pc is not None and roots and emotion and getattr(emotion, "scale_intervals", None):
            root0 = int(roots[0])
            scale_pcs = [int(iv) % 12 for iv in list(getattr(emotion, "scale_intervals", []) or [])]
            if scale_pcs:
                rel = (int(pc) - (root0 % 12)) % 12
                def _cdist(a: int, b: int) -> int:
                    d = abs(int(a) - int(b)) % 12
                    return min(d, 12 - d)
                handoff_entry_degree = int(min(range(len(scale_pcs)), key=lambda i: _cdist(rel, scale_pcs[i]))) % 7
    except Exception:
        handoff_entry_degree = None

    # Generate phrase plans
    joint_hook_degrees = _active_joint_hook_degrees(gen)
    plans = gen.planner.generate_plans(
        phrase_contours,
        len(notes_per_phrase),
        emotion,
        section_role=section_role,
        output_channel=int(output_channel),
        handoff_entry_degree=handoff_entry_degree,
        joint_hook_degrees=joint_hook_degrees or None,
    )
    role_lc = str(section_role or "").strip().lower()
    if joint_hook_degrees and role_lc in _CHORUS_SECTION_ROLES and handoff_entry_degree is None:
        current_degree = int(joint_hook_degrees[0]) % 7
    # Expose phrase intent for composition-level tooling (motif placement, debug).
    # Keep it best-effort: consumers should tolerate missing/partial plans.
    try:
        setattr(gen, "_last_phrase_plans", list(plans))
        setattr(gen, "_last_phrase_contours", list(phrase_contours))
        setattr(gen, "_last_notes_per_phrase", list(notes_per_phrase))
    except Exception:
        pass

    if total_beats is None:
        total_beats = int(sum(notes_per_phrase) * 2)

    # Phrase-length target in beats, used to keep phrase endings aligned to
    # musical time. This does not force bar alignment in the harmony layer,
    # but it gives the melody consistent "sentence" lengths and lets cadences
    # land with more intention.
    phrase_target_beats: Optional[float] = None
    if notes_per_phrase:
        phrase_target_beats = float(total_beats) / float(len(notes_per_phrase))

    truncated = False
    length_may_change = False
    phrase_history: List[List[Tuple[int, float]]] = []

    for phrase_idx, (plan, n_notes) in enumerate(zip(plans, notes_per_phrase)):
        # Stop if we've already exceeded total beats
        if total_beats is not None and current_beat >= total_beats:
            logger.debug(f"Stopping generation: current_beat {current_beat} >= total_beats {total_beats}")
            truncated = True
            break

        init_interval_ctx = all_intervals[-gen.markov.interval.order:] if len(all_intervals) >= gen.markov.interval.order else all_intervals[:]
        init_rhythm_ctx = all_rhythms[-gen.markov.rhythm.order:] if len(all_rhythms) >= gen.markov.rhythm.order else all_rhythms[:]

        phrase_beat_start_idx = len(beat_positions)  # snapshot before this phrase
        phrase_start_beat = current_beat
        phrase_end_beat = None
        if phrase_target_beats is not None:
            phrase_end_beat = phrase_start_beat + phrase_target_beats

        # ------------------------------------------------------------------
        # Phrase-level beam rerank (wider frontier + shortlist + lookahead).
        # ------------------------------------------------------------------
        try:
            from audiogen_core.config import CONFIG

            mpp = CONFIG.composition.melody_phrase_planning
            phrase_k = int(mpp.phrase_k_samples)
            beam_enabled = bool(mpp.beam_enabled)
            beam_width = int(mpp.beam_width)
            beam_keep = int(mpp.beam_keep)
            beam_div_w = float(mpp.beam_diversity_weight)
            beam_lh_w = float(mpp.beam_lookahead_weight)
            oq_on = bool(mpp.offline_quality_render_enabled)
            oq_k_scale = float(mpp.offline_quality_k_scale)
            oq_beam_width = int(mpp.offline_quality_beam_width)
            entry_pen = float(mpp.rerank_entry_leap_penalty)
            leap_pen = float(mpp.rerank_large_leap_penalty)
            leap_thr = int(mpp.rerank_large_leap_threshold)
            cad_land = float(mpp.rerank_cadence_land_bonus)
            cad_app = float(mpp.rerank_cadence_approach_bonus)
            cad_miss = float(mpp.rerank_cadence_miss_penalty)
        except Exception:
            phrase_k = 1
            beam_enabled = True
            beam_width = 7
            beam_keep = 3
            beam_div_w = 0.12
            beam_lh_w = 0.18
            oq_on = False
            oq_k_scale = 1.6
            oq_beam_width = 10
            entry_pen = 0.20
            leap_pen = 0.06
            leap_thr = 4
            cad_land = 0.35
            cad_app = 0.18
            cad_miss = 0.25

        # Adaptive CPU guardrail: in realtime "safe/balanced/emergency" modes,
        # do not multiply phrase-generation cost by K.
        rm = (runtime_mode or "").strip().lower()
        if rm in {"safe", "balanced", "emergency", "preview", "cold_preview"}:
            phrase_k = 1
            beam_enabled = False
        if oq_on and rm not in {"safe", "balanced", "emergency", "preview", "cold_preview"}:
            phrase_k = max(int(phrase_k), int(round(float(phrase_k) * max(1.0, float(oq_k_scale)))))
            beam_width = max(int(beam_width), int(oq_beam_width))

        phrase_k = max(1, int(phrase_k))
        beam_width = max(int(phrase_k), int(max(1, beam_width)))
        beam_keep = max(1, min(int(beam_width), int(beam_keep)))
        beam_div_w = max(0.0, min(1.0, float(beam_div_w)))
        beam_lh_w = max(0.0, min(1.0, float(beam_lh_w)))

        best = None
        best_score = -1e18
        cand_rows = []

        def _voiced_degrees(tokens: List[Tuple[int, float]]) -> List[int]:
            out = []
            for d, _dur in list(tokens or []):
                if isinstance(d, int) and int(d) >= 0:
                    out.append(int(d) % 7)
            return out

        def _simple_signature(tokens: List[Tuple[int, float]]) -> Tuple[Tuple[int, ...], Tuple[float, ...]]:
            degs: List[int] = []
            rhs: List[float] = []
            for d, dur in list(tokens or []):
                if isinstance(d, int) and int(d) >= 0:
                    degs.append(int(d) % 7)
                try:
                    rr = float(dur)
                except Exception:
                    rr = 0.5
                if rr <= 0.25 + 1e-9:
                    rb = 0.25
                elif rr <= 0.5 + 1e-9:
                    rb = 0.5
                elif rr <= 1.0 + 1e-9:
                    rb = 1.0
                elif rr <= 2.0 + 1e-9:
                    rb = 2.0
                else:
                    rb = 4.0
                rhs.append(float(rb))
            return tuple(degs), tuple(rhs)

        def _sim(sig_a: Tuple[Tuple[int, ...], Tuple[float, ...]], sig_b: Tuple[Tuple[int, ...], Tuple[float, ...]]) -> float:
            a_deg, a_rh = sig_a
            b_deg, b_rh = sig_b
            if not a_deg or not b_deg:
                return 0.0
            n = max(1, min(len(a_deg), len(b_deg)))
            deg_match = 0.0
            for i in range(n):
                da, db = int(a_deg[i]), int(b_deg[i])
                d = abs(int(da) - int(db))
                d = min(d, 7 - d)
                deg_match += max(0.0, 1.0 - 0.5 * float(d))
            deg_match /= float(n)
            m = max(1, min(len(a_rh), len(b_rh)))
            rh_match = 0.0
            for i in range(m):
                ra, rb = float(a_rh[i]), float(b_rh[i])
                if abs(ra - rb) <= 1e-9:
                    rh_match += 1.0
                elif abs(ra - rb) <= 0.5 + 1e-9:
                    rh_match += 0.5
            rh_match /= float(m)
            return float(0.67 * deg_match + 0.33 * rh_match)

        # Sample candidates without polluting global beat_positions until chosen.
        # We snapshot RNG state so K-sampling is deterministic given the seed.
        try:
            rng_state0 = gen.rng.getstate()
        except Exception:
            rng_state0 = None

        cand_n = int(beam_width if beam_enabled else phrase_k)
        for ki in range(cand_n):
            if rng_state0 is not None and ki > 0:
                # Restore the initial RNG state then advance deterministically by one draw
                # per candidate so candidates differ but remain reproducible.
                try:
                    gen.rng.setstate(rng_state0)
                    for _ in range(int(ki)):
                        _ = gen.rng.random()
                except Exception:
                    pass
            tmp_beats: List[float] = []
            # Use the bar at the phrase start for temperature shaping (cheap, stable).
            try:
                bar0 = int(float(current_beat) // float(beats_per_bar))
            except Exception:
                bar0 = 0
            temp_eff = _temp_for_bar(int(bar0))
            if trace_on:
                try:
                    trace = getattr(gen, "_debug_melody_intent_trace_by_bar", None)
                except Exception:
                    trace = None
                if not isinstance(trace, list):
                    trace = []
                # Ensure list is long enough.
                while len(trace) <= int(bar0):
                    trace.append({})
                row0 = dict(_bar_intent(int(bar0)) or {})
                try:
                    row0["bar_index"] = int(bar0)
                    row0["temperature_in"] = float(temperature)
                    row0["temperature_eff"] = float(temp_eff)
                    row0["section_role"] = str(section_role or "")
                except Exception:
                    pass
                trace[int(bar0)] = row0
                try:
                    setattr(gen, "_debug_melody_intent_trace_by_bar", trace)
                except Exception:
                    pass
            ph, ints, rhys = gen.note_gen.generate_phrase(
                start_degree=current_degree,
                num_notes=n_notes,
                plan=plan,
                temperature=float(temp_eff),
                emotion=emotion,
                start_beat=current_beat,
                chords=chords,
                roots=roots,
                beats_per_bar=beats_per_bar,
                chord_weights_per_bar=chord_weights_per_bar,
                beat_positions_out=tmp_beats,
                grid=grid,
                initial_interval_context=init_interval_ctx,
                initial_rhythm_context=init_rhythm_ctx,
                bass_notes=bass_notes,
                total_beats=total_beats,
                target_melody_notes=target_melody_notes,
                phrase_end_beat=phrase_end_beat,
                occupied_intervals=occupied_intervals,
                breath_window_by_bar=breath_window_by_bar,
                bar_intent_by_bar=intent_rows if intent_rows else None,
                voiced_chords_per_bar=voiced_chords_per_bar,
            )
            sc = score_phrase_candidate(
                ph,
                current_degree=int(current_degree),
                phrase_start_beat=float(phrase_start_beat),
                beats_per_bar=float(beats_per_bar),
                chord_weights_per_bar=list(chord_weights_per_bar or []),
                plan=plan,
                entry_pen=float(entry_pen),
                leap_pen=float(leap_pen),
                leap_thr=int(leap_thr),
                cad_land=float(cad_land),
                cad_app=float(cad_app),
                cad_miss=float(cad_miss),
                occ_step_weights=occ_step_weights,
                grid=float(grid),
                emotion=emotion,
                prior_phrases=list(phrase_history or []),
            )
            if sc > best_score:
                best_score = sc
                best = (ph, ints, rhys, tmp_beats)
            cand_rows.append((float(sc), ph, ints, rhys, tmp_beats, _simple_signature(ph)))

        if beam_enabled and cand_rows:
            # Stage 1: shortlist by base score.
            cand_rows = sorted(cand_rows, key=lambda x: float(x[0]), reverse=True)[: int(beam_keep)]
            # Stage 2: rerank shortlist with diversity + lookahead compatibility.
            next_plan = plans[phrase_idx + 1] if (phrase_idx + 1) < len(plans) else None
            reranked = []
            for row in list(cand_rows):
                sc0, ph, ints, rhys, tmp_beats, sig = row
                bonus = 0.0
                # Diversity: avoid near-duplicate phrases in the same frontier.
                if float(beam_div_w) > 1e-6:
                    sims = []
                    for other in list(cand_rows):
                        if other is row:
                            continue
                        sims.append(float(_sim(sig, other[5])))
                    if sims:
                        max_sim = max(float(v) for v in sims)
                        bonus += float(beam_div_w) * float(0.8 - max_sim)
                # Lookahead: align phrase end toward next phrase entry target.
                if float(beam_lh_w) > 1e-6 and next_plan is not None:
                    try:
                        vdeg = _voiced_degrees(ph)
                        if vdeg:
                            last_deg = int(vdeg[-1]) % 7
                            tgt = getattr(next_plan, "entry_degree", None)
                            if tgt is not None:
                                tgt = int(tgt) % 7
                                d = abs(int(last_deg) - int(tgt))
                                d = min(d, 7 - d)
                                bonus += float(beam_lh_w) * float(max(0.0, 1.0 - 0.33 * float(d)))
                    except Exception:
                        pass
                reranked.append((float(sc0) + float(bonus), ph, ints, rhys, tmp_beats))
            reranked.sort(key=lambda x: float(x[0]), reverse=True)
            if reranked:
                _sc, ph, ints, rhys, tmp_beats = reranked[0]
                best = (ph, ints, rhys, tmp_beats)
                best_score = float(_sc)

        if best is None:
            phrase_melody, phrase_intervals, phrase_rhythms, tmp_beats = [], [], [], []
        else:
            phrase_melody, phrase_intervals, phrase_rhythms, tmp_beats = best
        beat_positions.extend(list(tmp_beats or []))

        # Apply phrase repetition (if enabled).
        # _maybe_repeat_phrase can change the melody length (e.g. augment,
        # retrograde), which would leave beat_positions out of sync.
        # We re-derive positions for the modified phrase if needed.
        if emotion:
            original_length = len(phrase_melody)
            # Deterministic phrase restatement schedule (section-role aware).
            # This runs before probabilistic section form so hook sections can
            # reliably restate their opening idea (A -> A') even when RNG is unlucky.
            try:
                phrase_melody = gen._apply_explicit_restatement_schedule(
                    phrase_melody,
                    phrase_history,
                    phrase_idx=phrase_idx,
                    total_phrases=len(plans),
                    contour=plan.contour,
                    emotion_name=emotion.name,
                    plan=plan,
                )
            except Exception:
                pass
            phrase_melody = gen._maybe_apply_section_form(
                phrase_melody,
                phrase_history,
                phrase_idx,
                len(plans),
                plan.contour,
                emotion.name,
                plan=plan,
            )
            phrase_melody = gen._maybe_repeat_phrase(phrase_melody, plan.contour, emotion.name)
            if len(phrase_melody) != original_length:
                del beat_positions[phrase_beat_start_idx:]
                beat_positions.extend(
                    recompute_beat_positions(phrase_melody, phrase_start_beat)
                )
            # Cadence lock: phrase-level transformations (restatement / form / repeat)
            # can move the final note away from the planned cadence degree.
            try:
                pr0 = str(getattr(plan, "phrase_role", "") or "").strip().lower()
                cad0 = getattr(plan, "cadence_degree", None)
                if pr0 == "cadence" and cad0 is not None and phrase_melody:
                    tgt = int(cad0) % 7
                    last_idx = None
                    for j in range(len(phrase_melody) - 1, -1, -1):
                        d, _dur = phrase_melody[j]
                        if isinstance(d, int) and int(d) >= 0:
                            last_idx = j
                            break
                    if last_idx is not None:
                        d0, dur0 = phrase_melody[last_idx]
                        if int(d0) % 7 != int(tgt):
                            phrase_melody[last_idx] = (int(tgt), float(dur0))
                            # keep beat_positions consistent if we changed a note (durations unchanged)
            except Exception:
                pass

        try:
            from audiogen_core.config import CONFIG

            repair_stack_on = bool(CONFIG.composition.melody_phrase_planning.repair_stack_enabled)
        except Exception:
            repair_stack_on = True

        if phrase_melody and repair_stack_on:
            phrase_changed = False
            merged_phrase = _merge_repeated_short_notes_for_long_breath(
                phrase_melody,
                emotion=emotion,
            )
            if merged_phrase != phrase_melody:
                phrase_melody = merged_phrase
                phrase_changed = True
                truncated = True
                del beat_positions[phrase_beat_start_idx:]
                beat_positions.extend(
                    recompute_beat_positions(phrase_melody, phrase_start_beat)
                )
            repaired_phrase = _repair_static_phrase_motion(
                phrase_melody,
                plan=plan,
                emotion=emotion,
            )
            if repaired_phrase != phrase_melody:
                phrase_melody = repaired_phrase
                phrase_changed = True
            pride_arc_phrase = _pride_broad_arc_smoothing(
                phrase_melody,
                plan=plan,
                emotion=emotion,
            )
            if pride_arc_phrase != phrase_melody:
                phrase_melody = pride_arc_phrase
                phrase_changed = True
            smoothed_phrase = _smooth_unwanted_large_leaps(
                phrase_melody,
                emotion=emotion,
            )
            if smoothed_phrase != phrase_melody:
                phrase_melody = smoothed_phrase
                phrase_changed = True
            rising_phrase = _tilt_rising_motion_for_emotion(
                phrase_melody,
                emotion=emotion,
            )
            if rising_phrase != phrase_melody:
                phrase_melody = rising_phrase
                phrase_changed = True
            falling_phrase = _tilt_falling_motion_for_emotion(
                phrase_melody,
                emotion=emotion,
            )
            if falling_phrase != phrase_melody:
                phrase_melody = falling_phrase
                phrase_changed = True
            chorus_locked = _lock_chorus_pitch_cell(
                phrase_melody,
                plan=plan,
                gen=gen,
            )
            if chorus_locked != phrase_melody:
                phrase_melody = chorus_locked
                phrase_changed = True
            leaped_phrase = _apply_signature_leap_if_needed(
                phrase_melody,
                emotion=emotion,
            )
            if leaped_phrase != phrase_melody:
                phrase_melody = leaped_phrase
                phrase_changed = True
            if phrase_changed:
                phrase_intervals = []
                last_deg = int(current_degree)
                for d, _dur in list(phrase_melody or []):
                    if isinstance(d, int) and int(d) >= 0:
                        phrase_intervals.append(int(d) - int(last_deg))
                        last_deg = int(d)

        if phrase_melody:
            # Runtime motif feedback: treat freshly generated phrases as a short
            # "motif buffer" so later phrases can quote/restate recent material.
            # This makes output read more intentional without requiring retraining.
            try:
                from audiogen_core.config import CONFIG

                mf_on = bool(getattr(CONFIG.composition, "melody_runtime_motif_feedback_enabled", True))
                mf_prob = float(getattr(CONFIG.composition, "melody_runtime_motif_feedback_prob", 0.65) or 0.65)
                mf_min = int(getattr(CONFIG.composition, "melody_runtime_motif_feedback_min_voiced_notes", 4) or 4)
            except Exception:
                mf_on = True
                mf_prob = 0.65
                mf_min = 4
            mf_prob = max(0.0, min(1.0, float(mf_prob)))
            try:
                voiced_n = sum(1 for d, _dur in list(phrase_melody or []) if isinstance(d, int) and int(d) >= 0)
            except Exception:
                voiced_n = 0
            if mf_on and voiced_n >= int(mf_min) and gen is not None and hasattr(gen, "motif") and emotion is not None:
                try:
                    # Small throttle per generation call (avoid unbounded library growth).
                    used = int(getattr(gen, "_runtime_motif_feedback_used", 0) or 0)
                    cap = int(getattr(CONFIG.composition, "melody_runtime_motif_feedback_max_phrases", 8) or 8)
                except Exception:
                    used = int(getattr(gen, "_runtime_motif_feedback_used", 0) or 0)
                    cap = 8
                if used < cap and (gen.rng.random() < mf_prob):
                    try:
                        # Build a small “motif buffer” from this phrase and inject it
                        # directly into the library (no min-occurrence requirement).
                        lib = getattr(getattr(gen, "motif", None), "motif_library", None)
                        if lib is not None and hasattr(lib, "add_motif") and hasattr(lib, "motif_lengths"):
                            voiced = [(int(d), float(dur)) for d, dur in list(phrase_melody or []) if isinstance(d, int) and int(d) >= 0]
                            emo_name = str(getattr(emotion, "name", "") or "neutral").lower()
                            motif_lengths = list(getattr(lib, "motif_lengths", []) or [])
                            if not motif_lengths:
                                motif_lengths = [int(getattr(lib, "motif_length", 3) or 3)]
                            for L in sorted({int(x) for x in motif_lengths if x is not None and int(x) > 0}):
                                # Need L+1 voiced notes to get L intervals.
                                if len(voiced) < int(L) + 1:
                                    continue
                                window = list(voiced[-(int(L) + 1) :])
                                degs = [int(d) for d, _dur in window]
                                durs = [float(dur) for _d, dur in window]
                                intervals = [int(degs[i + 1]) - int(degs[i]) for i in range(int(L))]
                                rhythms = [float(durs[i]) for i in range(int(L))]
                                try:
                                    lib.add_motif(
                                        intervals=list(intervals),
                                        rhythms=list(rhythms),
                                        source_emotion=str(emo_name),
                                        chord_context=None,
                                        chord_degrees=None,
                                        is_rhythm_only=False,
                                    )
                                except Exception:
                                    pass
                        try:
                            setattr(gen, "_runtime_motif_feedback_used", int(used) + 1)
                        except Exception:
                            pass
                    except Exception:
                        pass

            melody.extend(phrase_melody)
            current_degree = phrase_melody[-1][0]
            current_beat += sum(d for _, d in phrase_melody)
            if phrase_intervals:
                all_intervals.extend(phrase_intervals)
            if phrase_rhythms:
                all_rhythms.extend(phrase_rhythms)
            phrase_history.append(list(phrase_melody))
        else:
            logger.warning(f"Phrase returned empty for {n_notes} notes!")

        # Stop if we've exceeded total beats after this phrase
        if total_beats is not None and current_beat >= total_beats:
            truncated = True
            break

    if melody and repair_stack_on:
        repaired_melody = _repair_static_phrase_motion(melody, plan=None, emotion=emotion)
        repaired_melody = _pride_broad_arc_smoothing(repaired_melody, plan=None, emotion=emotion)
        repaired_melody = _smooth_unwanted_large_leaps(repaired_melody, emotion=emotion)
        repaired_melody = _tilt_rising_motion_for_emotion(repaired_melody, emotion=emotion)
        repaired_melody = _tilt_falling_motion_for_emotion(repaired_melody, emotion=emotion)
        if repaired_melody != melody:
            melody = repaired_melody
            beat_positions = recompute_beat_positions(melody, 0.0)
            rebuilt_history: List[List[Tuple[int, float]]] = []
            idx0 = 0
            for n in list(notes_per_phrase or []):
                n_i = max(0, int(n))
                if n_i <= 0:
                    continue
                rebuilt_history.append(list(melody[idx0: idx0 + n_i]))
                idx0 += n_i
                if idx0 >= len(melody):
                    break
            if rebuilt_history:
                phrase_history = rebuilt_history

    # Truncate melody if it exceeds total beats (just in case)
    if total_beats is not None and current_beat > total_beats:
        cumulative = 0.0
        trunc_idx = 0
        for i, (_, dur) in enumerate(melody):
            if cumulative + dur > total_beats + 1e-6:
                break
            cumulative += dur
            trunc_idx = i + 1
        melody = melody[:trunc_idx]
        beat_positions = beat_positions[:trunc_idx]
        truncated = True

    # Optional: export live training row (pre post-processing stages that add rests/gaps).
    try:
        from audiogen_core.config import CONFIG

        enabled = bool(getattr(CONFIG.composition, "export_live_melody_training_enabled", False))
        out_path = str(getattr(CONFIG.composition, "export_live_melody_training_path", ".cache/live_melody_training.jsonl") or "")
    except Exception:
        enabled = False
        out_path = ""
    if enabled and out_path:
        try:
            # Final cadence lock for the export row: ensure the last voiced degree
            # matches the last phrase plan's cadence target when present.
            try:
                if plans and melody:
                    cad = getattr(plans[-1], "cadence_degree", None)
                    if cad is not None:
                        tgt = int(cad) % 7
                        last_idx = None
                        for i in range(len(melody) - 1, -1, -1):
                            d, _dur = melody[i]
                            if isinstance(d, int) and int(d) >= 0:
                                last_idx = i
                                break
                        if last_idx is not None:
                            d0, dur0 = melody[last_idx]
                            if int(d0) % 7 != int(tgt):
                                melody[last_idx] = (int(tgt), float(dur0))
            except Exception:
                pass

            roles = [str(getattr(p, "phrase_role", "") or "") for p in plans]
            contours = [str(getattr(p, "contour", "") or "") for p in plans]
            reg_centers = [getattr(p, "register_center_midi", None) for p in plans]
            reg_half = [getattr(p, "register_half_width_midi", None) for p in plans]
            cadence_targets = []
            for p0 in list(plans or []):
                try:
                    cadence_targets.append(
                        {
                            "entry_degree": None if getattr(p0, "entry_degree", None) is None else int(getattr(p0, "entry_degree")) % 7,
                            "target_climax": None if getattr(p0, "target_climax", None) is None else int(getattr(p0, "target_climax")) % 7,
                            "pre_cadence_degree": None if getattr(p0, "pre_cadence_degree", None) is None else int(getattr(p0, "pre_cadence_degree")) % 7,
                            "cadence_degree": None if getattr(p0, "cadence_degree", None) is None else int(getattr(p0, "cadence_degree")) % 7,
                            "position": None if getattr(p0, "position", None) is None else float(getattr(p0, "position")),
                            "phrase_role": str(getattr(p0, "phrase_role", "") or ""),
                            "contour": str(getattr(p0, "contour", "") or ""),
                        }
                    )
                except Exception:
                    cadence_targets.append({})

            # Export chords in two forms:
            # - chord_sequence: per-event alignment (len == len(melody)) so chord-conditioned melody
            #   training can use it directly.
            # - chord_sequence_bars: original bar-level chord progression for chord Markov retraining.
            chord_sequence_bars = [str(c or "") for c in (chords or [])] if chords else None
            chord_sequence = None
            if chord_sequence_bars and melody:
                try:
                    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
                except Exception:
                    bpb = 4.0
                bpb = max(0.25, float(bpb))
                aligned: List[str] = []
                # Prefer beat_positions if it matches (more robust when durations were repaired/merged).
                use_beats = isinstance(beat_positions, list) and len(beat_positions) == len(melody)
                beat = 0.0
                for i, (_deg, dur) in enumerate(list(melody or [])):
                    try:
                        beat_i = float(beat_positions[i]) if use_beats else float(beat)
                    except Exception:
                        beat_i = float(beat)
                    try:
                        bar = int(max(0.0, float(beat_i)) // float(bpb))
                    except Exception:
                        bar = 0
                    bar = min(max(0, int(bar)), int(len(chord_sequence_bars) - 1))
                    aligned.append(str(chord_sequence_bars[bar]))
                    try:
                        beat += abs(float(dur))
                    except Exception:
                        beat += 0.5
                chord_sequence = aligned if len(aligned) == len(melody) else None
            roots_out = [int(r) for r in (roots or [])] if roots else None
            chord_markov_tokens = None
            if chord_sequence_bars:
                try:
                    from data.tokens import ChordToken

                    toks = []
                    for ch in chord_sequence_bars:
                        try:
                            # Infer a stable function bucket for roman-numeral-ish symbols.
                            # Using the old simplify helper on bare roman roots (e.g. "I") collapses
                            # everything to "dom", which breaks chord Markov retraining.
                            s = str(ch or "").strip()
                            rlc = s.lower()
                            if "dim" in rlc or "°" in s or "ø" in s:
                                bucket = "dim"
                            elif "aug" in rlc or "+" in s:
                                bucket = "aug"
                            elif "sus" in rlc:
                                bucket = "sus"
                            elif "min" in rlc or (s and s[0].islower()):
                                bucket = "min"
                            elif "maj" in rlc or (s and s[0].isupper() and not rlc.startswith("v")):
                                bucket = "maj"
                            elif rlc.startswith("v") or "7" in s:
                                bucket = "dom"
                            else:
                                bucket = "dom"
                        except Exception:
                            bucket = "dom"
                        toks.append(ChordToken.from_symbol(str(ch), bucket=bucket).serialize(use_degree=True))
                    chord_markov_tokens = toks
                except Exception:
                    chord_markov_tokens = None

            # Lightweight harmony summaries (avoid heavy VL search in export path).
            voice_leading_cost_summary = None
            if roots_out and len(roots_out) >= 2:
                try:
                    leaps = [abs(int(roots_out[i]) - int(roots_out[i - 1])) for i in range(1, len(roots_out))]
                    voice_leading_cost_summary = {
                        "root_leap_mean": float(sum(leaps)) / float(len(leaps)) if leaps else 0.0,
                        "root_leap_max": float(max(leaps)) if leaps else 0.0,
                    }
                except Exception:
                    voice_leading_cost_summary = None
            if chord_sequence and voice_leading_cost_summary is not None:
                try:
                    repeats = sum(1 for i in range(1, len(chord_sequence)) if str(chord_sequence[i]) == str(chord_sequence[i - 1]))
                    voice_leading_cost_summary["chord_repeat_rate"] = float(repeats) / float(max(1, len(chord_sequence) - 1))
                except Exception:
                    pass

            row = {
                "ts": float(time.time()),
                "emotion": str(getattr(emotion, "name", "") or ""),
                "section_role": str(section_role or ""),
                "phrase_contours": contours,
                "phrase_roles": roles,
                "phrase_register_center_midi": [int(v) for v in reg_centers if v is not None] if any(v is not None for v in reg_centers) else None,
                "phrase_register_half_width_midi": [int(v) for v in reg_half if v is not None] if any(v is not None for v in reg_half) else None,
                "phrases": [[[int(d), float(dur)] for (d, dur) in ph] for ph in (phrase_history or [])],
                "melody": [[int(d), float(dur)] for (d, dur) in (melody or [])],
                "chord_sequence": chord_sequence,
                "chord_sequence_bars": chord_sequence_bars,
                "chord_markov_tokens": chord_markov_tokens,
                "harmonic_rhythm_bars": [1.0 for _ in chord_sequence_bars] if chord_sequence_bars else None,
                "cadence_targets": cadence_targets or None,
                "voice_leading_cost_summary": voice_leading_cost_summary,
                "roots": roots_out,
                "scale_intervals": [int(iv) for iv in (getattr(emotion, "scale_intervals", None) or [])] if emotion is not None else None,
                "beats_per_bar": float(beats_per_bar),
                "accept_score": float(melody_accept_heuristic(melody or [])),
            }
            try:
                from ai.markov.melody.beauty import score_lyrical_melody

                beauty, components = score_lyrical_melody(melody or [])
                row["lyrical_score"] = float(beauty)
                row["lyrical_components"] = {
                    str(k): float(v) for k, v in dict(components or {}).items()
                }
            except Exception:
                pass
            p = Path(out_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        except Exception:
            logger.debug("Live melody training export failed", exc_info=True)

    # Insert phrase gaps (if enabled)
    if gen.phrase_gap_prob > 0:
        melody = gen.post.insert_phrase_gaps(
            melody, notes_per_phrase,
            gap_duration=gen.phrase_gap_duration,
            prob=gen.phrase_gap_prob
        )
        beat_positions = recompute_beat_positions(melody, 0.0)
        length_may_change = True
        # We also need to update notes_per_phrase to include the rests for post-processing that depends on phrase structure.
        # Since we added rests, the notes_per_phrase list is no longer accurate for phrase-level operations.
        # We'll disable phrase-level post-processing when gaps are inserted (or simply skip them).
        # For safety, we'll set truncated = True to skip phrase-level ops that rely on notes_per_phrase.
        truncated = True  # skip enforce_phrase_structure and enforce_phrase_contours

    # Post‑processing
    chord_tones_per_bar_set = [set(cw.keys()) for cw in chord_weights_per_bar]

    if not truncated and gen.enforce_phrase_structure_prob > 0 and emotion and chords and roots:
        melody = gen.post.enforce_phrase_structure(
            melody, phrase_contours, notes_per_phrase, chord_tones_per_bar_set,
            beats_per_bar, beat_positions, probability=gen.enforce_phrase_structure_prob
        )

    # Markov upgrade A: optional position-aware rest scaling (very lightweight).
    rest_prob_eff = float(gen.rest_prob)
    from audiogen_core.composition_runtime_flags import melody_position_conditioning

    pos_on, pos_strength = melody_position_conditioning()
    if pos_on and pos_strength > 1e-6:
        try:
            # Cadence-like roles: slightly more space.
            if any(str(getattr(p, "phrase_role", "") or "").lower() == "cadence" for p in (plans or [])):
                rest_prob_eff *= (1.0 + 0.35 * pos_strength)
            # Intro/outro: slightly more space by default.
            sr = str(section_role or "").lower()
            if sr in {"intro", "outro"}:
                rest_prob_eff *= (1.0 + 0.45 * pos_strength)
        except Exception:
            pass
    rest_prob_eff = max(0.0, min(0.85, float(rest_prob_eff)))

    if rest_prob_eff > 1e-9:
        insert_kw = {}
        min_voiced_per_bar = 0
        try:
            from audiogen_core.config import CONFIG

            br_on = bool(getattr(CONFIG.composition, "melody_breath_rest_bias_enabled", False))
            br_st = float(getattr(CONFIG.composition, "melody_breath_rest_bias_strength", 0.65) or 0.65)
            br_st = max(0.0, min(1.0, float(br_st)))
            if br_on and br_st > 1e-9 and breath_window_by_bar:
                insert_kw = {
                    "breath_window_by_bar": list(breath_window_by_bar),
                    "breath_bias_strength": br_st,
                }
            guard_on = bool(getattr(CONFIG.composition, "melody_rest_min_voiced_bar_enabled", True))
            guard_ratio = float(getattr(CONFIG.composition, "melody_rest_min_voiced_bar_ratio", 0.58) or 0.58)
            guard_floor = int(getattr(CONFIG.composition, "melody_rest_min_voiced_bar_floor", 2) or 2)
            guard_cap = int(getattr(CONFIG.composition, "melody_rest_min_voiced_bar_ceiling", 6) or 6)
            if guard_on:
                bars_count = max(1, int(len(chords or [])) or int(round(float(total_beats or 0) / float(beats_per_bar or 4.0))))
                planned_npb = float(expected_total) / float(max(1, bars_count))
                guard_ratio = max(0.0, min(1.0, float(guard_ratio)))
                target_min = int(round(planned_npb * guard_ratio))
                min_voiced_per_bar = max(1, min(int(max(1, guard_cap)), max(int(max(1, guard_floor)), int(target_min))))
        except Exception:
            insert_kw = {}
            min_voiced_per_bar = 0
        melody = gen.post.insert_rests(
            melody,
            beat_positions,
            beats_per_bar,
            prob=float(rest_prob_eff),
            min_voiced_per_bar=int(min_voiced_per_bar),
            **insert_kw,
        )
        beat_positions = recompute_beat_positions(melody, 0.0)
        length_may_change = True

    if gen.embellishment_prob > 0 and chords and roots and emotion:
        # Grace notes (2026-07-03, docs/AUDIOGEN_COMPOSITION_PLAN.md item 16): scale by
        # how energetic the emotion is rather than adding a new per-emotion data table --
        # `tempo_multiplier` is already the codebase's existing energy proxy (used the same
        # way elsewhere, e.g. rhythm/style-profile biasing). Emotions at or below the
        # tempo_multiplier=1.0 baseline (grief, sadness, neutral, ...) get none; only
        # faster-than-baseline emotions (excitement, amusement, joy, ...) get any.
        energy = max(0.0, min(1.5, float(getattr(emotion, "tempo_multiplier", 1.0) or 1.0) - 1.0))
        prob_grace_note = gen.embellishment_prob * 0.4 * energy
        # Turns/mordents/slides (2026-07-04, docs/AUDIOGEN_COMPOSITION_PLAN.md item 16
        # follow-up): same energy-gating as grace notes -- decorative flourishes suit
        # energetic/ornamental emotions (amusement, excitement, curiosity) and are absent
        # at/below the tempo baseline. Kept individually rarer than grace notes since they
        # replace more of a note; each note takes at most one ornament (apply loop guards).
        prob_mordent = gen.embellishment_prob * 0.28 * energy
        prob_turn = gen.embellishment_prob * 0.18 * energy
        prob_slide = gen.embellishment_prob * 0.22 * energy
        melody = apply_embellishments(
            melody, beat_positions, chord_tones_per_bar_set, beats_per_bar,
            prob_passing=gen.embellishment_prob,
            prob_neighbor=gen.embellishment_prob * 0.5,
            prob_appoggiatura=gen.embellishment_prob * 0.3,
            prob_grace_note=prob_grace_note,
            prob_mordent=prob_mordent,
            prob_turn=prob_turn,
            prob_slide=prob_slide,
            rng=gen.rng
        )
        beat_positions = recompute_beat_positions(melody, 0.0)
        length_may_change = True

    if gen.enforce_chord_tones_prob > 0:
        melody = gen.post.enforce_chord_tones(
            melody, chord_tones_per_bar_set, beats_per_bar, beat_positions,
            probability=gen.enforce_chord_tones_prob,
            chord_weights_per_bar=chord_weights_per_bar,
        )

    if gen.enforce_climax:
        melody = gen._enforce_climax(melody)

    if not truncated and emotion:
        melody = gen.post.enforce_phrase_contours(melody, phrase_contours, notes_per_phrase)

    try:
        from audiogen_core.config import CONFIG

        max_repeat = int(getattr(CONFIG.composition, "melody_break_repeat_max", 3) or 3)
    except Exception:
        max_repeat = 3
    melody = gen.post.break_repetitions(melody, max_repeat=max(2, min(6, int(max_repeat))))
    melody = gen.post.remove_dissonant_leaps(melody)
    melody = gen.post.quantize_melody_strict(melody)

    # Optional post-processing stages such as rest insertion, embellishments,
    # and phrase gaps legitimately change the note count, so only warn when
    # the pipeline was expected to preserve the original target length.
    if len(melody) != expected_total:
        if length_may_change:
            logger.debug(
                "Melody length changed during post-processing: expected %s, got %s",
                expected_total,
                len(melody),
            )
        else:
            logger.warning(f"Melody length mismatch: expected {expected_total}, got {len(melody)}")
    return melody
