# ai/markov/chord/models.py
from ai.markov.core.base import BaseMarkov


class ChordMarkov(BaseMarkov):
    """Markov model for chord progressions."""


class GlobalChordMarkov(ChordMarkov):
    """Global chord Markov model trained on all emotions."""
