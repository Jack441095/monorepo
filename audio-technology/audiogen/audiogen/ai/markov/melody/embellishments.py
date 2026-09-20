# ai/markov/melody/embellishments.py
# Project module `embellishments` (ai).

#embellls

import random
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def is_chord_tone(degree: int, bar: int, chord_tones_per_bar: List[set]) -> bool:
    if bar < len(chord_tones_per_bar):
        return degree in chord_tones_per_bar[bar]
    return False


def find_passing_tone_opportunity(melody: List[Tuple[int, float]],
                                  idx: int,
                                  chord_tones_per_bar: List[set],
                                  beat_positions: List[float],
                                  beats_per_bar: float) -> Optional[List[Tuple[int, float]]]:
    if idx + 1 >= len(melody):
        return None
    if idx >= len(beat_positions) or idx + 1 >= len(beat_positions):
        return None
    deg1, dur1 = melody[idx]
    deg2, dur2 = melody[idx + 1]

    if abs(deg2 - deg1) == 2 and dur1 >= 0.5 and dur2 >= 0.5:
        mid_deg = (deg1 + deg2) // 2
        mid_dur = min(dur1, dur2) / 2
        new_dur1 = dur1 / 2
        new_dur2 = dur2
        return [(deg1, new_dur1), (mid_deg, mid_dur), (deg2, new_dur2)]
    return None


def find_neighbor_tone_opportunity(melody: List[Tuple[int, float]],
                                   idx: int,
                                   chord_tones_per_bar: List[set],
                                   beat_positions: List[float],
                                   beats_per_bar: float,
                                   rng=random) -> Optional[List[Tuple[int, float]]]:
    if idx + 1 >= len(melody):
        return None
    if idx >= len(beat_positions) or idx + 1 >= len(beat_positions):
        return None
    deg1, dur1 = melody[idx]
    deg2, dur2 = melody[idx + 1]
    bar1 = int(beat_positions[idx] // beats_per_bar)
    bar2 = int(beat_positions[idx + 1] // beats_per_bar)
    if bar1 >= len(chord_tones_per_bar) or bar2 >= len(chord_tones_per_bar):
        return None
    if not (deg1 in chord_tones_per_bar[bar1] and deg2 in chord_tones_per_bar[bar2] and deg1 == deg2 and dur1 >= 0.5):
        return None

    upper = (deg1 + 1) % 7
    lower = (deg1 - 1) % 7
    neighbor_deg = None
    if upper not in chord_tones_per_bar[bar1]:
        neighbor_deg = upper
    elif lower not in chord_tones_per_bar[bar1]:
        neighbor_deg = lower
    else:
        neighbor_deg = upper if rng.random() < 0.5 else lower

    new_dur1 = dur1 / 2.0
    new_dur2 = dur1 / 2.0
    return [(deg1, new_dur1), (neighbor_deg, new_dur2), (deg2, dur2)]


def find_appoggiatura_opportunity(melody: List[Tuple[int, float]],
                                  idx: int,
                                  chord_tones_per_bar: List[set],
                                  beat_positions: List[float],
                                  beats_per_bar: float) -> Optional[List[Tuple[int, float]]]:
    if idx == 0:
        return None
    if idx >= len(beat_positions):
        return None
    deg_target, dur_target = melody[idx]
    deg_prev, dur_prev = melody[idx - 1]
    bar_target = int(beat_positions[idx] // beats_per_bar)
    if bar_target >= len(chord_tones_per_bar):
        return None
    is_strong = (abs(beat_positions[idx] % beats_per_bar) < 1e-6 or
                 abs((beat_positions[idx] % beats_per_bar) - 2.0) < 1e-6)
    if not (deg_target in chord_tones_per_bar[bar_target] and is_strong):
        return None

    upper = (deg_target + 1) % 7
    lower = (deg_target - 1) % 7
    app_deg = None
    if upper not in chord_tones_per_bar[bar_target]:
        app_deg = upper
    elif lower not in chord_tones_per_bar[bar_target]:
        app_deg = lower
    else:
        return None

    app_dur = min(dur_target / 2.0, 0.5)
    new_dur_target = dur_target - app_dur
    if new_dur_target <= 0:
        return None
    return [(deg_prev, dur_prev), (app_deg, app_dur), (deg_target, new_dur_target)]


def find_grace_note_opportunity(melody: List[Tuple[int, float]],
                                idx: int,
                                beat_positions: List[float],
                                rng=random) -> Optional[List[Tuple[int, float]]]:
    """A short, unaccented step-wise auxiliary note crushed just before the main note,
    stealing a small sliver of the main note's own duration (distinct from
    `find_appoggiatura_opportunity`, which is longer, accented, and only targets
    chord tones on strong beats)."""
    if idx >= len(melody) or idx >= len(beat_positions):
        return None
    deg_target, dur_target = melody[idx]
    # The engine's canonical smallest note value is 0.25 beats (`core/constants.py::
    # DURATIONS`); anything shorter gets swallowed by downstream quantization before it
    # reaches the final event list (confirmed empirically -- a 0.0625 grace note never
    # survived to `song.events`). 0.5 beats of headroom leaves a valid 0.25-beat remainder
    # on the main note after carving out the grace note.
    if dur_target < 0.5:
        return None
    grace_dur = 0.25
    new_dur_target = dur_target - grace_dur
    if new_dur_target <= 0:
        return None
    upper = (deg_target + 1) % 7
    lower = (deg_target - 1) % 7
    grace_deg = upper if rng.random() < 0.5 else lower
    return [(grace_deg, grace_dur), (deg_target, new_dur_target)]


def find_mordent_opportunity(melody: List[Tuple[int, float]],
                             idx: int,
                             rng=random) -> Optional[List[Tuple[int, float]]]:
    """Mordent: a quick main -> neighbor -> main flourish on a single note, total duration
    preserved. A note of duration D becomes three notes ([main .25][neighbor .25][main
    D-.5]); needs D >= 0.75 so the sustained main note keeps a valid >=0.25 remainder.
    Idiomatic decorative flourish, most at home in energetic/playful lines."""
    if idx >= len(melody):
        return None
    deg, dur = melody[idx]
    if dur < 0.75:
        return None
    neighbor = (deg + 1) % 7 if rng.random() < 0.5 else (deg - 1) % 7
    return [(deg, 0.25), (neighbor, 0.25), (deg, dur - 0.5)]


def find_turn_opportunity(melody: List[Tuple[int, float]],
                          idx: int,
                          rng=random) -> Optional[List[Tuple[int, float]]]:
    """Turn: a four-note decorative figure circling the note (upper, principal, lower,
    principal), total duration preserved. A note of duration D becomes
    ([upper .25][main .25][lower .25][main D-.75]); needs D >= 1.0. Elegant/lyrical."""
    if idx >= len(melody):
        return None
    deg, dur = melody[idx]
    if dur < 1.0:
        return None
    upper = (deg + 1) % 7
    lower = (deg - 1) % 7
    return [(upper, 0.25), (deg, 0.25), (lower, 0.25), (deg, dur - 0.75)]


def find_slide_opportunity(melody: List[Tuple[int, float]],
                           idx: int,
                           rng=random) -> Optional[List[Tuple[int, float]]]:
    """Slide (scalar scoop): approach the note from two scale degrees below via a quick
    step-run, total duration preserved. A note of duration D becomes
    ([deg-2 .25][deg-1 .25][main D-.5]); needs D >= 0.75. Adds smooth flourish/lead-in."""
    if idx >= len(melody):
        return None
    deg, dur = melody[idx]
    if dur < 0.75:
        return None
    return [((deg - 2) % 7, 0.25), ((deg - 1) % 7, 0.25), (deg, dur - 0.5)]


def apply_embellishments(melody: List[Tuple[int, float]],
                         beat_positions: List[float],
                         chord_tones_per_bar: List[set],
                         beats_per_bar: float,
                         prob_passing: float = 0.1,
                         prob_neighbor: float = 0.1,
                         prob_appoggiatura: float = 0.05,
                         prob_grace_note: float = 0.0,
                         prob_mordent: float = 0.0,
                         prob_turn: float = 0.0,
                         prob_slide: float = 0.0,
                         rng=random) -> List[Tuple[int, float]]:
    if len(melody) < 2:
        return melody
    # Make sure beat_positions has same length as melody (pad if needed)
    if len(beat_positions) < len(melody):
        # Should not happen, but fallback
        logger.warning("beat_positions shorter than melody, skipping embellishments")
        return melody
    new_melody = []
    i = 0
    while i < len(melody):
        applied = False
        if i < len(melody) - 1 and rng.random() < prob_neighbor:
            seg = find_neighbor_tone_opportunity(melody, i, chord_tones_per_bar, beat_positions, beats_per_bar, rng=rng)
            if seg:
                new_melody.extend(seg)
                i += 2
                applied = True
        if not applied and i < len(melody) - 1 and rng.random() < prob_passing:
            seg = find_passing_tone_opportunity(melody, i, chord_tones_per_bar, beat_positions, beats_per_bar)
            if seg:
                new_melody.extend(seg)
                i += 2
                applied = True
        if not applied and i > 0 and i < len(melody) and rng.random() < prob_appoggiatura:
            seg = find_appoggiatura_opportunity(melody, i, chord_tones_per_bar, beat_positions, beats_per_bar)
            if seg:
                if new_melody:
                    new_melody.pop()
                new_melody.extend(seg)
                i += 1
                applied = True
        if not applied and prob_grace_note > 0 and rng.random() < prob_grace_note:
            seg = find_grace_note_opportunity(melody, i, beat_positions, rng=rng)
            if seg:
                new_melody.extend(seg)
                i += 1
                applied = True
        if not applied and prob_mordent > 0 and rng.random() < prob_mordent:
            seg = find_mordent_opportunity(melody, i, rng=rng)
            if seg:
                new_melody.extend(seg)
                i += 1
                applied = True
        if not applied and prob_turn > 0 and rng.random() < prob_turn:
            seg = find_turn_opportunity(melody, i, rng=rng)
            if seg:
                new_melody.extend(seg)
                i += 1
                applied = True
        if not applied and prob_slide > 0 and rng.random() < prob_slide:
            seg = find_slide_opportunity(melody, i, rng=rng)
            if seg:
                new_melody.extend(seg)
                i += 1
                applied = True
        if not applied:
            new_melody.append(melody[i])
            i += 1
    return new_melody