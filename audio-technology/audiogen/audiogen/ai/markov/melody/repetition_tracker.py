from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


_RHYTHM_BINS: Tuple[float, ...] = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0)


def _snap_rhythm(d: float) -> float:
    try:
        x = float(d)
    except Exception:
        return 1.0
    return float(min(_RHYTHM_BINS, key=lambda a: abs(float(a) - x)))


@dataclass
class RepetitionTracker:
    """
    RT-cheap dynamic repetition penalty for melodic tokens.

    Keeps a rolling window of recent tokens and maintains n-gram counts so
    selection-time penalty is O(ngram_orders) per candidate.
    """

    window_tokens: int = 36
    decay: float = 0.92
    strength: float = 0.35
    n_min: int = 3
    n_max: int = 5

    def __post_init__(self) -> None:
        self.window_tokens = int(max(8, min(256, int(self.window_tokens))))
        self.decay = float(max(0.5, min(0.995, float(self.decay))))
        self.strength = float(max(0.0, min(1.0, float(self.strength))))
        self.n_min = int(max(2, min(6, int(self.n_min))))
        self.n_max = int(max(self.n_min, min(7, int(self.n_max))))

        self._degrees: List[int] = []
        self._intervals: List[int] = []
        self._rhythms: List[float] = []

        # Counts per n for quick lookup.
        self._deg_counts: Dict[int, Dict[Tuple[int, ...], float]] = {}
        self._int_counts: Dict[int, Dict[Tuple[int, ...], float]] = {}
        self._rhy_counts: Dict[int, Dict[Tuple[float, ...], float]] = {}

    def start(self, start_degree: int) -> None:
        self._degrees = [int(start_degree) % 7]
        self._intervals = []
        self._rhythms = []
        self._rebuild()

    def observe_interval(self, interval: int, next_degree: int) -> None:
        self._intervals.append(int(interval))
        self._degrees.append(int(next_degree) % 7)
        self._trim()
        self._rebuild()

    def observe_rhythm(self, dur: float) -> None:
        self._rhythms.append(_snap_rhythm(abs(float(dur))))
        self._trim()
        self._rebuild()

    def penalty_for_next_interval(self, *, current_degree: int, candidate_interval: int) -> float:
        if self.strength <= 1e-9:
            return 1.0
        next_deg = (int(current_degree) + int(candidate_interval)) % 7
        deg_pen = self._penalty_from_counts(self._deg_counts, (*self._tail(self._degrees, self.n_max - 1), next_deg))
        int_pen = self._penalty_from_counts(self._int_counts, (*self._tail(self._intervals, self.n_max - 1), int(candidate_interval)))
        # Combine mildly; avoid collapsing to ~0 too easily.
        return float(max(0.05, min(1.0, (deg_pen * 0.55 + int_pen * 0.45))))

    def penalty_for_next_rhythm(self, *, candidate_dur: float) -> float:
        if self.strength <= 1e-9:
            return 1.0
        dur = _snap_rhythm(abs(float(candidate_dur)))
        return float(self._penalty_from_counts(self._rhy_counts, (*self._tail(self._rhythms, self.n_max - 1), dur)))

    def _trim(self) -> None:
        # Keep degrees length ~= intervals length + 1.
        w = int(self.window_tokens)
        if len(self._intervals) > w:
            drop = len(self._intervals) - w
            if drop > 0:
                self._intervals = self._intervals[drop:]
                # drop degrees accordingly, keeping +1
                self._degrees = self._degrees[drop:]
        if len(self._rhythms) > w:
            drop = len(self._rhythms) - w
            if drop > 0:
                self._rhythms = self._rhythms[drop:]

    @staticmethod
    def _tail(seq: List, k: int) -> Tuple:
        if k <= 0 or not seq:
            return tuple()
        return tuple(seq[-k:])

    def _rebuild(self) -> None:
        self._deg_counts = {n: {} for n in range(self.n_min, self.n_max + 1)}
        self._int_counts = {n: {} for n in range(self.n_min, self.n_max + 1)}
        self._rhy_counts = {n: {} for n in range(self.n_min, self.n_max + 1)}

        self._fill_counts(self._deg_counts, self._degrees)
        self._fill_counts(self._int_counts, self._intervals)
        self._fill_counts(self._rhy_counts, self._rhythms)

    def _fill_counts(self, target: Dict[int, Dict[Tuple, float]], seq: List) -> None:
        if not seq:
            return
        # Newer occurrences matter more (decay back in time).
        for n in range(self.n_min, self.n_max + 1):
            if len(seq) < n:
                continue
            counts = target[n]
            # walk forward; weight by how recent the n-gram ends.
            for end in range(n - 1, len(seq)):
                start = end - (n - 1)
                key = tuple(seq[start : end + 1])
                age = (len(seq) - 1) - end  # 0 = newest
                w = float(self.decay) ** float(age)
                counts[key] = float(counts.get(key, 0.0)) + w

    def _penalty_from_counts(self, counts_by_n: Dict[int, Dict[Tuple, float]], tail_plus: Tuple) -> float:
        if not counts_by_n:
            return 1.0
        # Evaluate all n-grams that end in this candidate.
        score = 0.0
        weight_sum = 0.0
        for n in range(self.n_min, self.n_max + 1):
            if len(tail_plus) < n:
                continue
            key = tuple(tail_plus[-n:])
            c = float(counts_by_n.get(n, {}).get(key, 0.0))
            if c <= 1e-9:
                continue
            # Higher-order repeats are more objectionable.
            w = float(n - self.n_min + 1)
            score += w * c
            weight_sum += w
        if weight_sum <= 1e-9:
            return 1.0
        avg = score / weight_sum
        # Map avg repeat score -> multiplicative penalty in (0,1].
        # 0 -> 1.0, ~1 -> (1-strength), larger -> stronger penalty.
        return float(max(0.05, 1.0 - float(self.strength) * (avg / (1.0 + avg))))

