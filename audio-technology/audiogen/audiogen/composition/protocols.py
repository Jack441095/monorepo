# composition/protocols.py
"""Structural types for Markov backends used by the composition layer.

Implementations live in `ai.markov` (`BaseMarkov`, `ChordMarkov`, `MarkovModelSet`, …).
These protocols document the contract so callers can swap models without importing
concrete classes everywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Dict, List, Optional, Protocol, TypeAlias

__all__ = [
    "ChordProgressionMarkov",
    "MarkovChain",
    "MelodyMarkovBackend",
    "MelodyMarkovModelSet",
]


class MarkovChain(Protocol):
    """Discrete n-gram Markov model (chords, scale-degree deltas, rhythm tokens, …)."""

    order: int

    def train(
        self,
        sequences: List[List[Any]],
        sequence_weights: Optional[Sequence[float]] = None,
    ) -> None:
        ...

    def generate(
        self,
        seed: List[Any],
        length: int,
        temperature: float = 1.0,
        top_k: Optional[int] = None,
    ) -> List[Any]:
        ...

    def get_probabilities(
        self,
        context: List[Any],
        temperature: float = 1.0,
        top_k: Optional[int] = None,
    ) -> Dict[Any, float]:
        ...


# Same surface as `ChordMarkov` / `GlobalChordMarkov` (harmony token sequences).
ChordProgressionMarkov: TypeAlias = MarkovChain


class MelodyMarkovModelSet(Protocol):
    """Bundle of interval, rhythm, and phrase chains used by `MelodyGenerator`."""

    interval: MarkovChain
    rhythm: MarkovChain
    phrase: MarkovChain


MelodyMarkovBackend: TypeAlias = MelodyMarkovModelSet
