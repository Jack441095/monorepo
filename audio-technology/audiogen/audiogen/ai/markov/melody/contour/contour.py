# ai/markov/melody/contour/contour.py
from typing import Dict, List, Tuple


def compute_contour(phrase: List[Tuple[int, float]]) -> str:
    """Return the melodic contour label for a phrase of (degree, duration) pairs."""
    if len(phrase) < 2:
        return "static"
    first = phrase[0][0]
    last = phrase[-1][0]
    mid_idx = len(phrase) // 2
    mid = phrase[mid_idx][0]
    if last > first + 1:
        return "asc"
    elif last < first - 1:
        return "desc"
    elif mid > first + 1 and mid > last + 1:
        return "arch"
    else:
        return "static"


def infer_contour_sequence(
    melody: List[Tuple[int, float]], beats_per_phrase: float = 16.0
) -> List[str]:
    """Split melody into phrases and return a list of contours."""
    if not melody:
        return []
    phrase_start_idx = 0
    phrase_contours = []
    phrase_beats = 0.0
    for i, (_, dur) in enumerate(melody):
        phrase_beats += dur
        if phrase_beats >= beats_per_phrase - 1e-6:
            phrase = melody[phrase_start_idx : i + 1]
            contour = compute_contour(phrase)
            phrase_contours.append(contour)
            phrase_start_idx = i + 1
            phrase_beats = 0.0
    if phrase_start_idx < len(melody):
        phrase = melody[phrase_start_idx:]
        contour = compute_contour(phrase)
        phrase_contours.append(contour)
    return phrase_contours


def get_phrase_intervals_by_contour(
    melody: List[Tuple[int, float]],
    beats_per_phrase: float = 16.0,
    *,
    rest_safe_intervals: bool = False,
) -> Dict[str, List[List[int]]]:
    """Split a melody into phrases and bucket their interval sequences by contour."""
    buckets: Dict[str, List[List[int]]] = {c: [] for c in ("asc", "desc", "arch", "static")}
    if len(melody) < 2:
        return buckets

    phrase_slices = []
    phrase_start = 0
    accumulated = 0.0
    for i, (_, dur) in enumerate(melody):
        accumulated += dur
        if accumulated >= beats_per_phrase - 1e-6:
            phrase_slices.append((phrase_start, i + 1))
            phrase_start = i + 1
            accumulated = 0.0
    if phrase_start < len(melody):
        phrase_slices.append((phrase_start, len(melody)))

    for start, end in phrase_slices:
        phrase = melody[start:end]
        if len(phrase) < 2:
            continue
        if rest_safe_intervals:
            voiced_pts = [(d, dur) for d, dur in phrase if isinstance(d, int) and int(d) >= 0]
            if len(voiced_pts) < 2:
                continue
            contour = compute_contour(voiced_pts)
            intervals = [voiced_pts[j + 1][0] - voiced_pts[j][0] for j in range(len(voiced_pts) - 1)]
        else:
            contour = compute_contour(phrase)
            intervals = [phrase[j + 1][0] - phrase[j][0] for j in range(len(phrase) - 1)]
        if contour in buckets:
            buckets[contour].append(intervals)
    return buckets


def recompute_beat_positions(
    phrase_melody: List[Tuple[int, float]], start_beat: float
) -> List[float]:
    """Return a beat-position list for phrase_melody starting at start_beat."""
    positions = []
    beat = start_beat
    for _, dur in phrase_melody:
        positions.append(beat)
        beat += dur
    return positions
