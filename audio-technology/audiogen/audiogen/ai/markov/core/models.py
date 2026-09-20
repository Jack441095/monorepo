# ai/markov/core/models.py
from .base import BaseMarkov


class IntervalMarkov(BaseMarkov):
    """Markov model for pitch intervals."""


class RhythmMarkov(BaseMarkov):
    """Markov model for note durations."""


class PhraseMarkov(BaseMarkov):
    """Markov model for phrase contours."""
