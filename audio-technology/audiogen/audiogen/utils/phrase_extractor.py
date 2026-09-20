# utils/phrase_extractor.py
# Project module `phrase_extractor` (utils).

#phrase_extractor.py
#//////////////////////////////////////////////////////////////////
# This module provides functions to analyze monophonic melodies and extract musical phrases based on rests and 
# fixed bar lengths. It includes functionality to determine the contour of each phrase (ascending, descending, arch,
# static) and can be used to label phrases for training AI models on melodic structure and expression.

from typing import List, Tuple


def detect_phrase_boundaries(melody: List[Tuple[int, float]],
                             min_rest_duration: float = 0.5,
                             max_phrase_len: int = 16) -> List[int]:
    if not melody:
        return [0]
    boundaries = [0]
    for i, (degree, duration) in enumerate(melody):
        # gap since last note end? Not directly available, we need start times.
        # We'll reconstruct approximate start times.
        pass
    if len(melody) > max_phrase_len:
        for i in range(max_phrase_len, len(melody), max_phrase_len):
            boundaries.append(i)
    return boundaries

def compute_contour(phrase: List[Tuple[int, float]]) -> str:
    if len(phrase) < 2:
        return 'static'
    degrees = [d for d, _ in phrase]
    first = degrees[0]
    last = degrees[-1]
    max_deg = max(degrees)
    min_deg = min(degrees)
    if last > first + 1:
        return 'asc'
    elif last < first - 1:
        return 'desc'
    elif max_deg > first + 1 and max_deg > last + 1:
        # peak is interior and higher than both ends
        return 'arch'
    elif min_deg < first - 1 and min_deg < last - 1:
        return 'valley'   # optional
    else:
        return 'static'

def split_into_phrases(melody: List[Tuple[int, float]],
                       time_signature: Tuple[int, int] = (4, 4),
                       beats_per_bar: float = 4.0,
                       phrase_bars: int = 4) -> Tuple[List[List[Tuple[int, float]]], List[str]]:
    """
    Split melody into fixed-length phrases (by bars) and label each with contour.
    This is simpler and works well if your melodies are metered.
    """
    # Estimate total beats from cumulative durations
    total_beats = sum(dur for _, dur in melody)
    total_beats / beats_per_bar
    # Split into phrases of `phrase_bars` bars
    beats_per_phrase = phrase_bars * beats_per_bar
    phrases = []
    current_phrase = []
    current_beats = 0.0
    for note in melody:
        current_phrase.append(note)
        current_beats += note[1]
        if current_beats >= beats_per_phrase - 1e-6:
            phrases.append(current_phrase)
            current_phrase = []
            current_beats = 0.0
    if current_phrase:
        phrases.append(current_phrase)

    contours = [compute_contour(p) for p in phrases]
    return phrases, contours


def process_midi_file(midi_path: str,
                      scale_intervals: List[int],
                      root_midi: int = 60,
                      phrase_bars: int = 4,
                      beats_per_bar: float = 4.0) -> Tuple[List[List[Tuple[int, float]]], List[str]]:

    from .midi_to_melody_data import midi_to_degree_duration  # relative import
    melody = midi_to_degree_duration(midi_path, scale_intervals, root_midi=root_midi)
    if not melody:
        return [], []
    return split_into_phrases(melody, phrase_bars=phrase_bars, beats_per_bar=beats_per_bar)


# Example usage (if run as script):
if __name__ == "__main__":
    # Test with a simple melody
    test_melody = [(0,1.0), (2,1.0), (4,1.0), (5,1.0), (4,1.0), (2,1.0), (0,2.0)]
    phrases, contours = split_into_phrases(test_melody, phrase_bars=2)  # 2-bar phrases (8 beats)
    print("Phrases:", phrases)
    print("Contours:", contours)