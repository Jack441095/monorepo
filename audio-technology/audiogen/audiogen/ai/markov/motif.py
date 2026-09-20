# ai/markov/motif.py
# Project module `motif` (ai).

# motif.py
import random
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from audiogen_core.composition_runtime_flags import motif_rhythm_only_enabled


class Motif:
    """
    Represents a melodic motif with intervals, rhythms, and metadata.
    """
    def __init__(
        self,
        intervals: List[int],
        rhythms: List[float],
                 contour: str = 'static',
                 avg_interval: float = 0.0,
                 rhythmic_density: float = 1.0,
                 source_emotion: str = 'neutral',
                 chord_progression_context: Optional[List[str]] = None,
                 chord_degrees: Optional[List[Set[int]]] = None,
                 is_rhythm_only: bool = False,
    ):
        self.intervals = tuple(intervals or [])
        self.rhythms = tuple(rhythms)
        self.contour = contour
        self.avg_interval = avg_interval
        self.rhythmic_density = rhythmic_density
        self.source_emotion = source_emotion
        self.chord_progression_context = chord_progression_context or []
        self.chord_degrees = chord_degrees or []
        self.is_rhythm_only = bool(is_rhythm_only)
        self.length = len(self.rhythms) if self.is_rhythm_only else len(self.intervals)

    def to_tuple(self) -> Tuple[Tuple[int, ...], Tuple[float, ...]]:
        return (self.intervals, self.rhythms)

    def is_chord_tone_at_position(self, position: int, chord_tones: Set[int]) -> bool:
        if position < len(self.chord_degrees):
            return any(deg in chord_tones for deg in self.chord_degrees[position])
        return False

    def __repr__(self):
        return (
            f"Motif(intervals={self.intervals}, rhythms={self.rhythms}, "
            f"contour={self.contour})"
        )


class MotifLibrary:
    """
    Stores and retrieves melodic motifs with metadata.
    Supports filtering by contour, emotion, and harmonic context.
    """

    def __init__(
        self,
        motif_length: int = 3,
        motif_lengths: Optional[List[int]] = None,
        filter_repeated: bool = True,
                 similarity_threshold: float = 1.5,
                 min_occurrences: int = 2):
        # FIX 1: The original default similarity_threshold was 0.1.
        # Because melodic intervals are integers, the minimum possible non-zero
        # RMS difference between two distinct motifs is 1.0 (one interval differs
        # by exactly 1 semitone).  A threshold of 0.1 therefore only matched
        # *perfectly identical* motifs, making near-duplicate filtering
        # completely ineffective.  1.5 means motifs where the average per-step
        # difference is under 1.5 semitones are treated as too similar to keep.
        # Adjust upward (e.g. 2.0–3.0) for more aggressive deduplication.
        self.motif_length = motif_length
        # Optional: support multiple motif lengths (e.g. 3–5) for richer vocabulary.
        self.motif_lengths = sorted({int(motif_length)} | {int(x) for x in (motif_lengths or []) if x is not None})
        self.filter_repeated = filter_repeated
        self.similarity_threshold = similarity_threshold
        self.min_occurrences = min_occurrences
        self.motifs: List[Motif] = []
        self.rhythm_motifs: List[Motif] = []
        self.by_contour: Dict[str, List[Motif]] = defaultdict(list)
        self.by_emotion: Dict[str, List[Motif]] = defaultdict(list)
        self.by_start_interval: Dict[int, List[Motif]] = defaultdict(list)
        self.by_start_rhythm: Dict[float, List[Motif]] = defaultdict(list)

    def _compute_contour(self, intervals: List[int]) -> str:
        if not intervals:
            return 'static'
        first = intervals[0]
        last = intervals[-1]
        if last > first + 1:
            return 'asc'
        elif last < first - 1:
            return 'desc'
        elif any(i > 1 for i in intervals) and any(i < -1 for i in intervals):
            return 'arch'
        else:
            return 'static'

    def _avg_interval_abs(self, intervals: List[int]) -> float:
        return sum(abs(i) for i in intervals) / len(intervals) if intervals else 0.0

    def _rhythmic_density(self, rhythms: List[float]) -> float:
        if not rhythms:
            return 1.0
        short_count = sum(1 for d in rhythms if d < 1.0)
        return short_count / len(rhythms)

    def _is_similar(self, m1: Motif, m2: Motif) -> bool:
        # Rhythm-only motifs: compare rhythms; otherwise compare intervals.
        if bool(getattr(m1, "is_rhythm_only", False)) or bool(getattr(m2, "is_rhythm_only", False)):
            if bool(getattr(m1, "is_rhythm_only", False)) != bool(getattr(m2, "is_rhythm_only", False)):
                return False
            if len(m1.rhythms) != len(m2.rhythms):
                return False
            diff = np.sqrt(np.mean([(a - b) ** 2 for a, b in zip(m1.rhythms, m2.rhythms)]))
            return diff < (self.similarity_threshold * 0.75)

        if len(m1.intervals) != len(m2.intervals):
            return False
        diff = np.sqrt(np.mean([(a - b) ** 2 for a, b in zip(m1.intervals, m2.intervals)]))
        return diff < self.similarity_threshold

    def add_motif(
        self,
        intervals: List[int],
        rhythms: List[float],
                  source_emotion: str = 'neutral',
                  chord_context: Optional[List[str]] = None,
        chord_degrees: Optional[List[Set[int]]] = None,
        *,
        is_rhythm_only: bool = False,
    ) -> bool:
        L = len(rhythms)
        if int(L) not in set(self.motif_lengths):
            return False
        if (not is_rhythm_only) and len(intervals) != L:
            return False
        if self.filter_repeated and (not is_rhythm_only) and all(i == 0 for i in intervals):
            return False
        if (not is_rhythm_only) and sum(abs(i) for i in intervals) <= 1:
            return False
        if len(set(rhythms)) == 1 and rhythms[0] >= 2.0:
            return False

        contour = "static" if is_rhythm_only else self._compute_contour(intervals)
        avg_int = 0.0 if is_rhythm_only else self._avg_interval_abs(intervals)
        density = self._rhythmic_density(rhythms)

        new_motif = Motif(
            intervals,
            rhythms,
            contour,
            avg_int,
            density,
            source_emotion,
            chord_context,
            chord_degrees,
            is_rhythm_only=bool(is_rhythm_only),
        )

        existing_pool = self.rhythm_motifs if is_rhythm_only else self.motifs
        for existing in existing_pool:
            if self._is_similar(new_motif, existing):
                return False

        if is_rhythm_only:
            self.rhythm_motifs.append(new_motif)
            self.by_emotion[source_emotion].append(new_motif)
            self.by_start_rhythm[rhythms[0]].append(new_motif)
        else:
            self.motifs.append(new_motif)
            self.by_contour[contour].append(new_motif)
            self.by_emotion[source_emotion].append(new_motif)
            self.by_start_interval[intervals[0]].append(new_motif)
            self.by_start_rhythm[rhythms[0]].append(new_motif)
        return True

    def extract_from_melody(self, melody: List[Tuple[int, float]],
                            source_emotion: str = 'neutral',
                            chord_sequence: Optional[List[str]] = None):

        max_len = max(self.motif_lengths) if self.motif_lengths else int(self.motif_length)
        if len(melody) < int(max_len) + 1:
            return
        intervals = [melody[i + 1][0] - melody[i][0] for i in range(len(melody) - 1)]
        rhythms = [d for _, d in melody]

        # Count motifs for each supported length.
        temp_counts: Dict[Tuple[Tuple[int, ...], Tuple[float, ...], int], int] = {}
        for L in list(self.motif_lengths or [int(self.motif_length)]):
            if L <= 0 or len(intervals) < L:
                continue
            for i in range(len(intervals) - L + 1):
                seg_intervals = tuple(intervals[i:i + L])
                seg_rhythms = tuple(rhythms[i:i + L])
                key = (seg_intervals, seg_rhythms, int(L))
                temp_counts[key] = temp_counts.get(key, 0) + 1

        def _roman_root_degree(sym: str) -> Optional[int]:
            s = (sym or "").strip()
            if not s:
                return None
            # Strip leading accidentals.
            i = 0
            while i < len(s) and s[i] in {"b", "#"}:
                i += 1
            start = i
            while i < len(s) and s[i] in {"i", "v", "I", "V"}:
                i += 1
            roman = s[start:i]
            if not roman:
                return None
            r = roman.upper()
            mapping = {"I": 0, "II": 1, "III": 2, "IV": 3, "V": 4, "VI": 5, "VII": 6}
            return mapping.get(r)

        def _approx_chord_degrees(sym: str) -> Set[int]:
            """
            Coarse diatonic chord-tone degrees (0..6) derived from roman numeral + quality.
            This is intentionally lightweight (RT-safe) and is only used as a *motif fit hint*.
            """
            s = (sym or "").strip()
            root = _roman_root_degree(s)
            if root is None:
                return {0, 2, 4}
            lowered = s.lower()
            is_sus = "sus" in lowered
            is_dim = ("dim" in lowered) or ("ø" in s) or ("°" in s)
            is_aug = ("aug" in lowered) or ("+" in s)
            is_min = ("min" in lowered) or (len(s) > 0 and s[0].islower())
            is_dom = ("7" in lowered) and "maj" not in lowered

            third = (root + (3 if is_sus else 2)) % 7
            fifth = (root + 4) % 7
            out = {int(root), int(third), int(fifth)}
            if is_dom:
                out.add(int((root + 6) % 7))
            if is_dim:
                out.add(int((root + 6) % 7))
            if is_aug:
                out.add(int((root + 5) % 7))
            if is_min:
                # keep same degrees; quality is not represented in diatonic degree space
                pass
            return out

        for (seg_intervals, seg_rhythms, L), count in temp_counts.items():
            if count >= self.min_occurrences:
                chord_context = None
                chord_degrees = None
                if chord_sequence:
                    start_idx = next(
                        (
                            idx for idx in range(len(intervals) - int(L) + 1)
                            if tuple(intervals[idx:idx + int(L)]) == seg_intervals
                            and tuple(rhythms[idx:idx + int(L)]) == seg_rhythms
                        ),
                        0,
                    )
                    chord_context = list(chord_sequence[start_idx:start_idx + int(L) + 1])
                    try:
                        # Per-step chord-degree sets aligned to motif steps.
                        # Step i corresponds to the note *after* applying interval i.
                        cd: List[Set[int]] = []
                        for j in range(int(L)):
                            sym = ""
                            k = int(start_idx) + int(j) + 1
                            if 0 <= k < len(chord_sequence):
                                sym = str(chord_sequence[k] or "")
                            cd.append(set(_approx_chord_degrees(sym)))
                        chord_degrees = cd
                    except Exception:
                        chord_degrees = None
                self.add_motif(
                    list(seg_intervals),
                    list(seg_rhythms),
                    source_emotion=source_emotion,
                    chord_context=chord_context,
                    chord_degrees=chord_degrees,
                )

        # Optional: extract rhythm-only motifs (durations only).
        rhythm_only = motif_rhythm_only_enabled()
        if rhythm_only:
            try:
                for L in list(self.motif_lengths or [int(self.motif_length)]):
                    if L <= 0 or len(rhythms) < L:
                        continue
                    for i in range(len(rhythms) - L + 1):
                        seg_rh = list(rhythms[i:i + L])
                        # Skip ultra-uniform long holds.
                        if len(set(seg_rh)) == 1 and float(seg_rh[0]) >= 2.0:
                            continue
                        self.add_motif(
                            [],
                            seg_rh,
                            source_emotion=source_emotion,
                            chord_context=None,
                            chord_degrees=None,
                            is_rhythm_only=True,
                        )
            except Exception:
                pass

    def random_motif(self, contour: Optional[str] = None,
                     emotion: Optional[str] = None,
                     max_interval: Optional[float] = None,
                     min_density: Optional[float] = None) -> Optional['Motif']:
        # FIX 2: Use the pre-built index dicts (by_contour, by_emotion) for
        # the first filter step instead of always starting from self.motifs.
        # The original code used by_contour but never used by_emotion —
        # the emotion filter was always a slow linear scan over whatever
        # candidates were left.  Now both indexes are used up front so the
        # common case of filtering by both contour and emotion is fast.
        if contour and emotion:
            # Intersect the two index sets for maximum efficiency.
            contour_set = set(id(m) for m in self.by_contour.get(contour, []))
            candidates = [
                m for m in self.by_emotion.get(emotion, [])
                if id(m) in contour_set
            ]
        elif contour:
            candidates = list(self.by_contour.get(contour, []))
        elif emotion:
            candidates = list(self.by_emotion.get(emotion, []))
        else:
            candidates = list(self.motifs)

        if max_interval is not None:
            candidates = [m for m in candidates if m.avg_interval <= max_interval]
        if min_density is not None:
            candidates = [m for m in candidates if m.rhythmic_density >= min_density]

        return random.choice(candidates) if candidates else None

    def motifs_starting_with(self, interval: int, rhythm: float,
                              contour: Optional[str] = None,
                              emotion: Optional[str] = None) -> List['Motif']:
        candidates = [motif for motif in self.by_start_interval.get(interval, []) if motif.rhythms and motif.rhythms[0] == rhythm]
        if contour:
            candidates = [m for m in candidates if m.contour == contour]
        if emotion:
            candidates = [m for m in candidates if m.source_emotion == emotion]
        return candidates

    def rhythm_motifs_starting_with(self, rhythm: float, *, emotion: Optional[str] = None) -> List['Motif']:
        candidates = [motif for motif in self.by_start_rhythm.get(rhythm, []) if getattr(motif, "is_rhythm_only", False)]
        if emotion:
            candidates = [m for m in candidates if m.source_emotion == emotion]
        return candidates

    def best_motif_for_context(self, last_interval: int, last_rhythm: float,
                               target_contour: str,
                               current_emotion: str,
                               chord: Optional[str] = None) -> Optional['Motif']:
        candidates = self.motifs_starting_with(
            last_interval, last_rhythm,
            contour=target_contour,
            emotion=current_emotion,
        )
        if not candidates:
            candidates = self.motifs_starting_with(last_interval, last_rhythm)
        if not candidates:
            return None

        def score(m: Motif) -> float:
            s = 1.0
            # Placeholder for chord-tone scoring — extend here when
            # chord_degrees are populated during extraction.
            return s

        return max(candidates, key=score)
