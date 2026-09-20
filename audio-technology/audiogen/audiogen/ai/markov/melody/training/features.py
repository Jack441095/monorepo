# ai/markov/melody/training/features.py
from typing import Dict, List, Tuple

from ai.markov.melody.ensemble.bucketing import (
    GESTURE_KEYS,
    NUM_PREV_DURATION_BUCKETS,
    phrase_gesture_from_position,
    prev_note_duration_bucket,
)


def build_recency_weights(count: int, start: float = 0.7, end: float = 1.3) -> List[float]:
    if count <= 0:
        return []
    if count == 1:
        return [1.0]
    return [start + (end - start) * (i / (count - 1)) for i in range(count)]


def melody_interval_steps(melody: List[Tuple[int, float]], rest_safe: bool) -> List[int]:
    """Consecutive scale-degree intervals for training IntervalMarkov."""
    if len(melody) < 2:
        return []
    if not rest_safe:
        return [int(melody[i + 1][0]) - int(melody[i][0]) for i in range(len(melody) - 1)]
    voiced: List[int] = []
    for d, _ in melody:
        try:
            if isinstance(d, int) and int(d) >= 0:
                voiced.append(int(d))
        except Exception:
            continue
    if len(voiced) < 2:
        return []
    return [voiced[j + 1] - voiced[j] for j in range(len(voiced) - 1)]


def rhythm_token_for_event(degree: int, dur: float, signed_rest: bool) -> float:
    """Phase 2b: positive = voiced IOI, negative = rest of abs(IOI)."""
    if not signed_rest:
        return float(dur)
    try:
        if isinstance(degree, int) and int(degree) < 0:
            return -float(dur)
    except Exception:
        pass
    return float(dur)


def interval_sequences_by_prev_duration_bucket(
    melody: List[Tuple[int, float]],
    rest_safe: bool,
) -> Dict[int, List[int]]:
    """Intervals grouped by duration bucket of the preceding voiced note (Phase 2a training)."""
    out: Dict[int, List[int]] = {i: [] for i in range(NUM_PREV_DURATION_BUCKETS)}
    if len(melody) < 2:
        return out
    if rest_safe:
        vidx = [i for i, (d, _) in enumerate(melody) if isinstance(d, int) and int(d) >= 0]
        for j in range(len(vidx) - 1):
            i0, i1 = vidx[j], vidx[j + 1]
            try:
                pd = float(melody[i0][1])
            except Exception:
                continue
            b = prev_note_duration_bucket(pd)
            iv = int(melody[i1][0]) - int(melody[i0][0])
            out[b].append(iv)
    else:
        for i in range(len(melody) - 1):
            deg0, dur0 = melody[i]
            deg1, _ = melody[i + 1]
            try:
                if int(deg0) < 0 or int(deg1) < 0:
                    continue
            except Exception:
                continue
            b = prev_note_duration_bucket(float(dur0))
            out[b].append(int(deg1) - int(deg0))
    return out


def interval_sequences_by_phrase_gesture(
    melody: List[Tuple[int, float]],
    rest_safe: bool,
) -> Dict[str, List[int]]:
    """Collect interval tokens per phrase-gesture bucket (Phase 2c training)."""
    acc: Dict[str, List[int]] = {g: [] for g in GESTURE_KEYS}
    if len(melody) < 2:
        return acc
    if rest_safe:
        vidx = [i for i, (d, _) in enumerate(melody) if isinstance(d, int) and int(d) >= 0]
        n = len(vidx)
        if n < 2:
            return acc
        for j in range(n - 1):
            i0, i1 = vidx[j], vidx[j + 1]
            try:
                iv = int(melody[i1][0]) - int(melody[i0][0])
            except Exception:
                continue
            pos = float(j) / float(max(1, n - 1))
            g = phrase_gesture_from_position(pos)
            acc[g].append(iv)
    else:
        for i in range(len(melody) - 1):
            pos = float(i) / float(max(1, len(melody) - 1))
            g = phrase_gesture_from_position(pos)
            try:
                acc[g].append(int(melody[i + 1][0]) - int(melody[i][0]))
            except Exception:
                continue
    return acc
