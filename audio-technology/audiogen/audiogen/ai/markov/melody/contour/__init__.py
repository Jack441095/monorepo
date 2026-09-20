# ai/markov/melody/contour/__init__.py
from .contour import (
    compute_contour,
    get_phrase_intervals_by_contour,
    infer_contour_sequence,
    recompute_beat_positions,
)

__all__ = [
    "compute_contour",
    "infer_contour_sequence",
    "get_phrase_intervals_by_contour",
    "recompute_beat_positions",
]
