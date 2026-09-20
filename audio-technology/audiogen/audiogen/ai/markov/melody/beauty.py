"""Lyrical-minimalist melody scoring.

The scorer is intentionally lightweight and deterministic. It rewards broad
musical traits that suit intimate emotional generative writing: stepwise motion,
recoveries after leaps, small recurring motifs, breathable pacing, and stable
cadences.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Tuple

MelodyEvent = Tuple[int, float]


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _wrapped_step(a: int, b: int) -> int:
    d = abs(int(a) - int(b)) % 7
    return int(min(d, 7 - d))


def _duration_bucket(dur: float) -> float:
    d = abs(float(dur))
    if d <= 0.25 + 1e-9:
        return 0.25
    if d <= 0.5 + 1e-9:
        return 0.5
    if d <= 1.0 + 1e-9:
        return 1.0
    if d <= 2.0 + 1e-9:
        return 2.0
    return 4.0


def _sweet_spot(value: float, target: float, half_width: float) -> float:
    if half_width <= 1e-9:
        return 1.0 if abs(float(value) - float(target)) <= 1e-9 else 0.0
    return _clamp01(1.0 - abs(float(value) - float(target)) / float(half_width))


def _motif_recurrence(degs: List[int], rhythms: List[float]) -> float:
    if len(degs) < 5:
        return 0.45
    scores: List[float] = []
    for n in (2, 3, 4):
        if len(degs) < n * 2:
            continue
        pitch_cells = Counter(tuple(degs[i : i + n]) for i in range(0, len(degs) - n + 1))
        rhythm_cells = Counter(tuple(rhythms[i : i + n]) for i in range(0, len(rhythms) - n + 1))
        pitch_hits = sum(c - 1 for c in pitch_cells.values() if c > 1)
        rhythm_hits = sum(c - 1 for c in rhythm_cells.values() if c > 1)
        denom = max(1, len(degs) - n)
        scores.append(_clamp01((0.75 * pitch_hits + 0.25 * rhythm_hits) / float(denom)))
    if not scores:
        return 0.45
    raw = max(scores)
    return _sweet_spot(raw, 0.28, 0.32)


def score_lyrical_melody(events: List[MelodyEvent], *, cadence_degree: int = 0) -> Tuple[float, Dict[str, float]]:
    """Return ``(score, components)`` where score is 0..1."""

    tokens: List[MelodyEvent] = []
    for d, dur in list(events or []):
        try:
            tokens.append((int(d), float(dur)))
        except Exception:
            continue
    if not tokens:
        return 0.0, {"empty": 1.0}

    voiced = [(int(d) % 7, abs(float(dur))) for d, dur in tokens if int(d) >= 0]
    rests = [(int(d), abs(float(dur))) for d, dur in tokens if int(d) < 0]
    if len(voiced) < 3:
        return 0.20, {"too_short": 1.0}

    degs = [d for d, _ in voiced]
    durs = [max(0.0, float(dur)) for _, dur in voiced]
    rhythm_buckets = [_duration_bucket(d) for d in durs]
    intervals = [_wrapped_step(degs[i], degs[i - 1]) for i in range(1, len(degs))]

    stepwise_ratio = sum(1 for iv in intervals if iv <= 1) / float(max(1, len(intervals)))
    leap_ratio = sum(1 for iv in intervals if iv >= 3) / float(max(1, len(intervals)))
    stepwise = _clamp01(0.72 * stepwise_ratio + 0.28 * (1.0 - leap_ratio))

    recoveries = 0
    leap_count = 0
    for i, iv in enumerate(intervals[:-1]):
        if iv < 3:
            continue
        leap_count += 1
        if intervals[i + 1] <= 1:
            recoveries += 1
    leap_recovery = 0.75 if leap_count == 0 else _clamp01(recoveries / float(leap_count))

    signed = []
    for i in range(1, len(degs)):
        raw = int(degs[i]) - int(degs[i - 1])
        if raw > 3:
            raw -= 7
        elif raw < -3:
            raw += 7
        signed.append(raw)
    direction_changes = 0
    prev_sign = 0
    for v in signed:
        sign = 1 if v > 0 else (-1 if v < 0 else 0)
        if sign and prev_sign and sign != prev_sign:
            direction_changes += 1
        if sign:
            prev_sign = sign
    contour_smooth = _sweet_spot(direction_changes / float(max(1, len(signed))), 0.22, 0.30)

    motif = _motif_recurrence(degs, rhythm_buckets)

    unique_rhythms = len(set(rhythm_buckets))
    rhythm_vocab = 1.0 - _clamp01(max(0, unique_rhythms - 4) / 5.0)
    tiny_ratio = sum(1 for d in durs if d <= 0.25 + 1e-9) / float(len(durs))
    long_ratio = sum(1 for d in durs if d >= 1.0 - 1e-9) / float(len(durs))
    rhythm_space = _clamp01(0.45 * rhythm_vocab + 0.35 * (1.0 - tiny_ratio) + 0.20 * _sweet_spot(long_ratio, 0.34, 0.34))

    rest_rate = len(rests) / float(max(1, len(tokens)))
    rest_balance = _sweet_spot(rest_rate, 0.14, 0.18)

    cad = int(cadence_degree) % 7
    last = int(degs[-1]) % 7
    cadence_dist = _wrapped_step(last, cad)
    cadence = _clamp01(1.0 - 0.34 * float(cadence_dist))
    if last in {0, 2, 4}:
        cadence = max(cadence, 0.78)

    span = max(degs) - min(degs)
    range_focus = _sweet_spot(span, 4.0, 3.0)

    components = {
        "stepwise": float(stepwise),
        "leap_recovery": float(leap_recovery),
        "contour_smooth": float(contour_smooth),
        "motif_recurrence": float(motif),
        "rhythm_space": float(rhythm_space),
        "rest_balance": float(rest_balance),
        "cadence": float(cadence),
        "range_focus": float(range_focus),
    }
    weights = {
        "stepwise": 0.19,
        "leap_recovery": 0.13,
        "contour_smooth": 0.12,
        "motif_recurrence": 0.15,
        "rhythm_space": 0.14,
        "rest_balance": 0.08,
        "cadence": 0.13,
        "range_focus": 0.06,
    }
    score = sum(float(components[k]) * float(weights[k]) for k in weights)
    return _clamp01(score), components


def lyrical_accept_score(events: List[MelodyEvent]) -> float:
    """Accept-score helper for JSONL export."""

    score, _components = score_lyrical_melody(events)
    if not events:
        return 0.0
    voiced = [int(d) for d, _ in events if isinstance(d, int) and int(d) >= 0]
    if len(voiced) < 2:
        return float(score)
    reps = 0
    for i in range(2, len(voiced)):
        if voiced[i] == voiced[i - 1] == voiced[i - 2]:
            reps += 1
    leaps = 0
    for i in range(1, len(voiced)):
        if _wrapped_step(voiced[i], voiced[i - 1]) >= 4:
            leaps += 1
    n = max(1, len(voiced))
    safety = max(0.0, 1.0 - 0.35 * (reps / n) - 0.25 * (leaps / n))
    return float(_clamp01(0.62 * score + 0.38 * safety))
