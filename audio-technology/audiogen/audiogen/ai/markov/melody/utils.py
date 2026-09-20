# ai/markov/melody/utils.py
# Project module `utils` (ai).

# utils.py
from typing import Dict, List, Optional, Set

from data.music_theory import CHORD_VOICINGS


def chord_symbol_to_scale_degrees(chord_symbol: str, root: int, scale_intervals: List[int]) -> Set[int]:
    matched_quality = None
    for quality in sorted(CHORD_VOICINGS.keys(), key=len, reverse=True):
        if quality in chord_symbol:
            matched_quality = quality
            break

    if matched_quality is None:
        intervals = [0, 4, 7]
    else:
        intervals = CHORD_VOICINGS[matched_quality][0]

    chord_midi_notes = [root + i for i in intervals]
    degrees = set()
    for midi in chord_midi_notes:
        pc = midi % 12
        for deg, interval in enumerate(scale_intervals):
            if (root + interval) % 12 == pc:
                degrees.add(deg)
                break
    return degrees

def chord_symbol_to_scale_degrees_weighted(chord_symbol: str, root: int, scale_intervals: List[int]) -> Dict[int, float]:
    matched_quality = None
    for quality in sorted(CHORD_VOICINGS.keys(), key=len, reverse=True):
        if quality in chord_symbol:
            matched_quality = quality
            break

    if matched_quality is None:
        intervals = [0, 4, 7]
        weights = [1.0, 0.9, 0.8]
    else:
        intervals = CHORD_VOICINGS[matched_quality][0]
        weights = []
        for i in intervals:
            pc = i % 12
            if pc == 0:
                weights.append(1.0)
            elif pc == 4 or pc == 3:
                weights.append(0.9)
            elif pc == 7:
                weights.append(0.8)
            elif pc == 10 or pc == 11:
                weights.append(0.7)
            else:
                weights.append(0.6)

    chord_midi_notes = [root + i for i in intervals]
    degree_weight = {}
    for midi, w in zip(chord_midi_notes, weights):
        pc = midi % 12
        for deg, interval in enumerate(scale_intervals):
            if (root + interval) % 12 == pc:
                degree_weight[deg] = max(w, degree_weight.get(deg, 0))
                break
    return degree_weight


def _weight_for_interval_pc(pc: int) -> float:
    pc = int(pc) % 12
    if pc == 0:
        return 1.0
    if pc in (3, 4):
        return 0.9
    if pc == 7:
        return 0.8
    if pc in (10, 11):
        return 0.7
    return 0.6


def chord_weights_for_bar_from_voiced_midi(
    root: int,
    scale_intervals: List[int],
    midi_notes: List[int],
) -> Dict[int, float]:
    """Map absolute MIDI chord tones to scale degrees; merge with max weight."""
    if not scale_intervals or not midi_notes:
        return {}
    root = int(root)
    degree_weight: Dict[int, float] = {}
    for midi in midi_notes:
        if not isinstance(midi, int):
            continue
        m_pc = int(midi) % 12
        rel = (m_pc - (root % 12)) % 12
        w = _weight_for_interval_pc(rel)
        for deg, interval in enumerate(scale_intervals):
            if (root + int(interval)) % 12 == m_pc:
                degree_weight[int(deg)] = max(float(w), float(degree_weight.get(int(deg), 0.0)))
                break
    return degree_weight


def build_chord_weights_per_bar(
    chords: Optional[List[str]],
    roots: Optional[List[int]],
    scale_intervals: Optional[List[int]],
    voiced_chords_per_bar: Optional[List[List[int]]] = None,
) -> List[Dict[int, float]]:
    """
    One dict per bar: scale-degree -> weight for interval / motif conditioning.

    When ``voiced_chords_per_bar`` has non-empty MIDI lists for a bar, weights
    follow the actual voicing; otherwise falls back to Roman-symbol analysis.
    """
    if not chords or not roots:
        n_bars = len(chords) if chords else 64
        return [{} for _ in range(max(1, int(n_bars)))]
    if not scale_intervals:
        n_bars = len(chords)
        return [{} for _ in range(max(1, int(n_bars)))]

    out: List[Dict[int, float]] = []
    n = len(chords)
    for i in range(n):
        use_voiced = (
            voiced_chords_per_bar is not None
            and i < len(voiced_chords_per_bar)
            and voiced_chords_per_bar[i]
        )
        if use_voiced:
            cw = chord_weights_for_bar_from_voiced_midi(
                int(roots[i]),
                list(scale_intervals),
                list(voiced_chords_per_bar[i]),
            )
            if cw:
                out.append(cw)
                continue
        out.append(
            chord_symbol_to_scale_degrees_weighted(str(chords[i] or ""), int(roots[i]), list(scale_intervals))
        )
    return out