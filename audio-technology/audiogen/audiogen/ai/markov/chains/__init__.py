# ai/markov/chains/__init__.py
# Deprecated: use ai.markov.core instead.

from ai.markov.core import (
    BaseMarkov,
    DURATIONS,
    IntervalMarkov,
    PhraseMarkov,
    RhythmMarkov,
)

__all__ = [
    "BaseMarkov",
    "DURATIONS",
    "IntervalMarkov",
    "RhythmMarkov",
    "PhraseMarkov",
]
