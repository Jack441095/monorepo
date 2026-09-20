# ai/markov/melody/ensemble/__init__.py
import sys
import types

from .bucketing import (
    GESTURE_KEYS,
    NUM_PREV_DURATION_BUCKETS,
    phrase_gesture_from_position,
    prev_note_duration_bucket,
)
from .model_set import MarkovModelSet

_MM = "ai.markov.melody.markov_models"
if _MM not in sys.modules:
    _stub = types.ModuleType(_MM)
    _stub.MarkovModelSet = MarkovModelSet
    sys.modules[_MM] = _stub

__all__ = [
    "MarkovModelSet",
    "NUM_PREV_DURATION_BUCKETS",
    "GESTURE_KEYS",
    "phrase_gesture_from_position",
    "prev_note_duration_bucket",
]
