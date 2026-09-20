# composition/mixins/caching.py
# Project module `caching` (composition).

# caching.py
from collections import OrderedDict
from typing import List

from data.music_data import EmotionProfile

class _LRUDict(OrderedDict):
    """
    Tiny LRU dict with a hard max size.

    Used to prevent unbounded growth of shared caches during long realtime sessions.
    """

    def __init__(self, maxsize: int):
        super().__init__()
        self.maxsize = int(max(16, maxsize))

    def __getitem__(self, key):
        v = super().__getitem__(key)
        try:
            self.move_to_end(key, last=True)
        except Exception:
            pass
        return v

    def get(self, key, default=None):
        if key in self:
            try:
                self.move_to_end(key, last=True)
            except Exception:
                pass
        return super().get(key, default)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        try:
            self.move_to_end(key, last=True)
        except Exception:
            pass
        try:
            while len(self) > int(self.maxsize):
                self.popitem(last=False)
        except Exception:
            pass


_SHARED_EMOTION_TRAINING_CACHE = _LRUDict(maxsize=1024)
_SHARED_ARTIFICIAL_MELODY_CACHE = _LRUDict(maxsize=2048)
_SHARED_PROGRESSION_EXPANSION_CACHE = _LRUDict(maxsize=2048)
_SHARED_PREPARED_TRAINING_DATA_CACHE = _LRUDict(maxsize=512)


class CachingMixin:
    """Caching utilities for scales, chord tones, and training data."""

    def __init__(self, *args, **kwargs):
        # No super() call
        # Local (per-generator) caches: cap size to avoid long-session growth.
        self._emotion_scale_cache = _LRUDict(maxsize=128)
        self._chord_tone_cache = _LRUDict(maxsize=2048)
        self._emotion_training_cache = _SHARED_EMOTION_TRAINING_CACHE
        self._artificial_melody_cache = _SHARED_ARTIFICIAL_MELODY_CACHE
        self._progression_expansion_cache = _SHARED_PROGRESSION_EXPANSION_CACHE
        self._prepared_training_data_cache = _SHARED_PREPARED_TRAINING_DATA_CACHE

    def _get_cached_chord_tones(self, chord: str, degree: int) -> List[int]:
        """Cache chord tone patterns"""
        key = (chord, degree)
        if key not in self._chord_tone_cache:
            tones = [degree, degree+2, degree+4]
            if '7' in chord or 'maj7' in chord:
                tones.append(degree+6)
            self._chord_tone_cache[key] = tones
        return self._chord_tone_cache[key]

    def _get_scale_intervals(self, emotion: EmotionProfile) -> List[int]:
        """Cache scale intervals per emotion"""
        if emotion.name not in self._emotion_scale_cache:
            self._emotion_scale_cache[emotion.name] = emotion.scale_intervals
        return self._emotion_scale_cache[emotion.name]
