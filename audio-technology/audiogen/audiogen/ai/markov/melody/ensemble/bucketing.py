# ai/markov/melody/ensemble/bucketing.py
from typing import Tuple

# Buckets for P(next_interval | duration of preceding voiced note).
NUM_PREV_DURATION_BUCKETS = 5

# Phase 2c: phrase gesture buckets (position along voiced line, not phrase-role labels).
GESTURE_KEYS: Tuple[str, ...] = ("opening", "middle", "cadence")


def phrase_gesture_from_position(pos: float) -> str:
    """Map normalized phrase position 0..1 to opening | middle | cadence (thirds)."""
    try:
        p = max(0.0, min(1.0, float(pos)))
    except Exception:
        p = 0.0
    if p < 1.0 / 3.0:
        return "opening"
    if p < 2.0 / 3.0:
        return "middle"
    return "cadence"


def prev_note_duration_bucket(dur: float) -> int:
    """Quantize preceding note duration into 0..NUM_PREV_DURATION_BUCKETS-1."""
    try:
        d = float(dur)
    except Exception:
        return 2
    if d <= 0.25 + 1e-9:
        return 0
    if d <= 0.5 + 1e-9:
        return 1
    if d <= 1.0 + 1e-9:
        return 2
    if d <= 2.0 + 1e-9:
        return 3
    return 4
