# ai/markov/core/__init__.py
"""Core Markov primitives (base model + typed melody subclasses + constants)."""

from .base import BaseMarkov
from .constants import DURATIONS
from .models import IntervalMarkov, PhraseMarkov, RhythmMarkov

__all__ = [
    "BaseMarkov",
    "DURATIONS",
    "IntervalMarkov",
    "RhythmMarkov",
    "PhraseMarkov",
]
