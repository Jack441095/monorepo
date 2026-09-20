# ai/markov/melody/motif_variations.py
# Project module `motif_variations` (ai).

# motif_variations.py
from typing import List, Tuple


def augment_motif(intervals: List[int], rhythms: List[float], factor: float = 2.0) -> Tuple[List[int], List[float]]:
    """Double (or multiply by factor) the durations of a motif."""
    return intervals, [d * factor for d in rhythms]

def diminish_motif(intervals: List[int], rhythms: List[float], factor: float = 0.5) -> Tuple[List[int], List[float]]:
    """Halve (or multiply by factor) the durations of a motif."""
    return intervals, [d * factor for d in rhythms]

def invert_motif(intervals: List[int], rhythms: List[float]) -> Tuple[List[int], List[float]]:
    """Invert the intervals (positive becomes negative, etc.)."""
    return [-i for i in intervals], rhythms

def retrograde_motif(intervals: List[int], rhythms: List[float]) -> Tuple[List[int], List[float]]:
    """Reverse the order of both intervals and rhythms."""
    return intervals[::-1], rhythms[::-1]

def fragment_motif(intervals: List[int], rhythms: List[float], length: int) -> Tuple[List[int], List[float]]:
    """Take only the first `length` notes of the motif."""
    return intervals[:length], rhythms[:length]

def sequence_motif(intervals: List[int], rhythms: List[float], step: int = 1) -> Tuple[List[int], List[float]]:

    return [i + step for i in intervals], rhythms