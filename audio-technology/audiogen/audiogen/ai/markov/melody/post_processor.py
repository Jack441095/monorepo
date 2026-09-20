# ai/markov/melody/post_processor.py
# Project module `post_processor` (ai).

# ai/markov/melody/post_processor.py
import random
import logging
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class PostProcessor:
    """Handles post‑generation modifications: quantization, smoothing, repetition breaking."""

    def __init__(self, grid: float = 0.25, rng=random):
        self.grid = grid
        self.rng = rng

    def quantize_melody_strict(self, melody: List[Tuple[int, float]]) -> List[Tuple[int, float]]:
        """Quantise note start times and durations to the grid, ensuring no gaps or overlaps."""
        if not melody:
            return melody
        quantized = []
        current_beat = 0.0
        for degree, dur in melody:
            start = round(current_beat / self.grid) * self.grid
            dur_quant = round(dur / self.grid) * self.grid
            if dur_quant < self.grid / 2:
                dur_quant = self.grid
            quantized.append((degree, dur_quant))
            current_beat = start + dur_quant
        return quantized

    def remove_dissonant_leaps(self, melody: List[Tuple[int, float]]) -> List[Tuple[int, float]]:
        """Cap melodic leaps larger than a scale-degree third (i.e. > 3 scale steps).

        NOTE: this operates on scale degrees, not MIDI semitones, so "a third"
        here means a distance of 3 diatonic steps — which is a musical fourth
        or fifth depending on the scale.  If you need semitone-accurate leap
        smoothing, convert to MIDI first.
        """
        if len(melody) < 2:
            return melody
        smoothed = [melody[0]]
        for i in range(1, len(melody)):
            prev_deg = smoothed[-1][0]
            curr_deg, dur = melody[i]
            leap = abs(curr_deg - prev_deg)
            if leap > 3:
                if curr_deg > prev_deg:
                    curr_deg = prev_deg + 1
                else:
                    curr_deg = prev_deg - 1
                curr_deg = curr_deg % 7
            smoothed.append((curr_deg, dur))
        return smoothed

    def smooth_leaps(self, melody: List[Tuple[int, float]]) -> List[Tuple[int, float]]:
        """Alias for remove_dissonant_leaps."""
        return self.remove_dissonant_leaps(melody)

    def break_repetitions(self, melody: List[Tuple[int, float]], max_repeat: int = 2) -> List[Tuple[int, float]]:
        """Replace repeated notes with rests after max_repeat."""
        new_melody = []
        repeat_count = 0
        prev_deg = None
        for deg, dur in melody:
            if deg == prev_deg and deg != -1:
                repeat_count += 1
            else:
                repeat_count = 0
            if repeat_count >= max_repeat:
                new_melody.append((-1, dur))
                repeat_count = 0
            else:
                new_melody.append((deg, dur))
            prev_deg = deg
        return new_melody

    def insert_rests(self, melody: List[Tuple[int, float]],
                     beat_positions: List[float],
                     beats_per_bar: float,
                     prob: float = 0.15,
                     *,
                     breath_window_by_bar: Optional[List[float]] = None,
                     breath_bias_strength: float = 0.0,
                     min_voiced_per_bar: int = 0) -> List[Tuple[int, float]]:
        """Insert rests randomly.

        When ``breath_window_by_bar`` is provided and ``breath_bias_strength`` > 0,
        rest probability scales up on bars with higher breath weights (0..1).
        """
        new_melody = []
        bpb = float(beats_per_bar) if beats_per_bar else 4.0
        for i, (deg, dur) in enumerate(melody):
            p = float(prob)
            if breath_window_by_bar and breath_bias_strength > 1e-9:
                try:
                    bi = int(float(beat_positions[i]) // bpb) if i < len(beat_positions) else 0
                except Exception:
                    bi = 0
                if 0 <= bi < len(breath_window_by_bar):
                    bw = float(breath_window_by_bar[bi] or 0.0)
                    bw = max(0.0, min(1.0, bw))
                    p = min(0.85, p * (1.0 + float(breath_bias_strength) * bw))
            if self.rng.random() < p:
                new_melody.append((-1, dur))
            else:
                new_melody.append((deg, dur))
        if int(min_voiced_per_bar) > 0 and beat_positions:
            by_bar = {}
            for i in range(min(len(new_melody), len(beat_positions))):
                try:
                    bi = int(float(beat_positions[i]) // bpb)
                except Exception:
                    bi = 0
                by_bar.setdefault(int(bi), []).append(i)

            min_voiced = max(1, int(min_voiced_per_bar))
            for _bar, idxs in by_bar.items():
                voiced = sum(
                    1 for i in idxs
                    if i < len(new_melody) and isinstance(new_melody[i][0], int) and int(new_melody[i][0]) >= 0
                )
                need = int(min_voiced - voiced)
                if need <= 0:
                    continue

                candidates = []
                for i in idxs:
                    if i >= len(new_melody) or i >= len(melody):
                        continue
                    if int(new_melody[i][0]) >= 0:
                        continue
                    src_deg, _src_dur = melody[i]
                    if not isinstance(src_deg, int) or int(src_deg) < 0:
                        continue
                    local_beat = float(beat_positions[i]) % bpb
                    # Strongest restore priority:
                    # 1) bar downbeat, 2) quarter-note positions, 3) any other slot.
                    quarter_dist = abs(local_beat - round(local_beat))
                    strong_rank = 2
                    if abs(local_beat) <= 1e-9:
                        strong_rank = 0
                    elif quarter_dist <= 1e-9:
                        strong_rank = 1
                    candidates.append((strong_rank, quarter_dist, i))

                candidates.sort(key=lambda t: (t[0], t[1], t[2]))
                for _rank, _dist, i in candidates[:need]:
                    new_melody[i] = melody[i]
        return new_melody

    def insert_phrase_gaps(self, melody: List[Tuple[int, float]], notes_per_phrase: List[int],
                           gap_duration: float = 1.0, prob: float = 0.3) -> List[Tuple[int, float]]:
        """Insert rests between phrases."""
        new_melody = []
        idx = 0
        for i, n in enumerate(notes_per_phrase):
            phrase = melody[idx:idx+n]
            new_melody.extend(phrase)
            if i < len(notes_per_phrase) - 1 and self.rng.random() < prob:
                new_melody.append((-1, gap_duration))   # rest
            idx += n
        return new_melody

    @staticmethod
    def _is_strong_beat(local_beat: float, beats_per_bar: float, eps: float = 0.08) -> bool:
        bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
        x = float(local_beat)
        e = max(1e-9, float(eps))
        d0 = min(abs(x - 0.0), abs(x - bpb))
        dmid = abs(x - (bpb / 2.0))
        return (d0 <= e) or (dmid <= e)

    @staticmethod
    def _nearest_degree(target: int, candidates: Set[int]) -> int:
        return min(candidates, key=lambda d: min(abs(int(d) - int(target)), 7 - abs(int(d) - int(target))))

    def enforce_phrase_structure(self,
                                 melody: List[Tuple[int, float]],
                                 phrase_contours: List[str],
                                 notes_per_phrase: List[int],
                                 chord_tones_per_bar: List[Set[int]],
                                 beats_per_bar: float,
                                 beat_positions: List[float],
                                 probability: float = 0.9) -> List[Tuple[int, float]]:
        """Ensure phrase start/end notes are chord tones."""
        new_melody = []
        idx = 0
        for phrase_idx, n in enumerate(notes_per_phrase):
            phrase = melody[idx:idx+n]
            if not phrase:
                new_melody.extend(phrase)
                idx += n
                continue
            if self.rng.random() < probability:
                first_deg, first_dur = phrase[0]
                bar = int(beat_positions[idx] // beats_per_bar) if idx < len(beat_positions) else 0
                if bar >= len(chord_tones_per_bar):
                    bar = len(chord_tones_per_bar) - 1
                if bar >= 0 and bar < len(chord_tones_per_bar) and chord_tones_per_bar[bar]:
                    if first_deg not in chord_tones_per_bar[bar]:
                        closest = min(chord_tones_per_bar[bar], key=lambda d: abs(d - first_deg))
                        phrase[0] = (closest, first_dur)
            if self.rng.random() < probability and len(phrase) > 1:
                last_deg, last_dur = phrase[-1]
                last_beat_idx = idx + n - 1
                bar = int(beat_positions[last_beat_idx] // beats_per_bar) if last_beat_idx < len(beat_positions) else 0
                if bar >= len(chord_tones_per_bar):
                    bar = len(chord_tones_per_bar) - 1
                if bar >= 0 and bar < len(chord_tones_per_bar) and chord_tones_per_bar[bar]:
                    if last_deg not in chord_tones_per_bar[bar]:
                        closest = min(chord_tones_per_bar[bar], key=lambda d: abs(d - last_deg))
                        phrase[-1] = (closest, last_dur)
            new_melody.extend(phrase)
            idx += n
        return new_melody

    def enforce_chord_tones(self,
                            melody: List[Tuple[int, float]],
                            chord_tones_per_bar: List[Set[int]],
                            beats_per_bar: float,
                            beat_positions: List[float],
                            probability: float = 0.9,
                            *,
                            chord_weights_per_bar: Optional[List[Dict[int, float]]] = None,
                            strong_beat_probability: float = 1.0,
                            strong_beat_window: float = 0.08) -> List[Tuple[int, float]]:
        """Ensure notes land on stable harmony tones.

        Offbeats keep the legacy behaviour: if a degree is outside the bar's
        chord-tone set, it may be snapped to the nearest available tone.

        Strong beats are treated more strictly: we prefer the chord's stable
        members (root/3rd/5th-like weights >= 0.8 when available) so downbeats
        and mid-bar accents read as intentionally harmonised rather than merely
        "inside the scale".
        """
        new_melody = []
        for i, (deg, dur) in enumerate(melody):
            if not isinstance(deg, int) or int(deg) < 0:
                new_melody.append((deg, dur))
                continue
            if i < len(beat_positions):
                bar = int(beat_positions[i] // beats_per_bar)
                if bar >= len(chord_tones_per_bar):
                    bar = len(chord_tones_per_bar) - 1
                local_beat = float(beat_positions[i]) - float(max(0, bar)) * float(beats_per_bar)
            else:
                bar = 0
                local_beat = 0.0
            if bar >= 0 and bar < len(chord_tones_per_bar) and chord_tones_per_bar[bar]:
                chord_tones = {int(d) % 7 for d in chord_tones_per_bar[bar]}
                chord_weights = (
                    chord_weights_per_bar[bar]
                    if chord_weights_per_bar is not None and 0 <= bar < len(chord_weights_per_bar)
                    else {}
                ) or {}
                stable = {
                    int(d) % 7
                    for d, w in chord_weights.items()
                    if float(w) >= 0.8
                }
                if not stable:
                    stable = set(chord_tones)
                is_strong = self._is_strong_beat(local_beat, beats_per_bar, eps=float(strong_beat_window))
                prob_eff = float(strong_beat_probability) if is_strong else float(probability)
                prob_eff = max(0.0, min(1.0, prob_eff))
                current = int(deg) % 7
                target_pool = stable if is_strong else chord_tones
                needs_snap = current not in target_pool
                if needs_snap and self.rng.random() < prob_eff:
                    deg = self._nearest_degree(current, set(target_pool))
            new_melody.append((deg, dur))
        return new_melody

    def enforce_phrase_contours(self,
                                melody: List[Tuple[int, float]],
                                phrase_contours: List[str],
                                notes_per_phrase: List[int]) -> List[Tuple[int, float]]:
        """Adjust phrase contours if they deviate (ascending/descending)."""
        idx = 0
        new_melody = []
        for contour, n in zip(phrase_contours, notes_per_phrase):
            phrase = melody[idx:idx+n]
            if not phrase:
                continue
            first_deg = phrase[0][0]
            last_deg = phrase[-1][0]
            if contour == 'asc' and last_deg <= first_deg:
                diff = first_deg - last_deg + 1
                phrase = [(min((d + diff) % 7, 6), dur) for d, dur in phrase]
            elif contour == 'desc' and last_deg >= first_deg:
                diff = last_deg - first_deg + 1
                phrase = [(max((d - diff) % 7, 0), dur) for d, dur in phrase]
            new_melody.extend(phrase)
            idx += n
        return new_melody
