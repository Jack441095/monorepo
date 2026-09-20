from __future__ import annotations

from typing import Dict

from data.emotion_aliases import canonical_emotion_name


EMOTION_MELODY_RHYTHM_PROFILES: Dict[str, Dict[str, float]] = {
    "admiration": {"short_bias": 0.92, "long_bias": 1.08},
    "amusement": {"short_bias": 1.18, "syncopation_bias": 1.14, "long_bias": 0.88},
    "anger": {"short_bias": 1.12, "syncopation_bias": 1.08, "long_bias": 0.92},
    "annoyance": {"short_bias": 1.02, "syncopation_bias": 1.04, "long_bias": 0.96},
    "approval": {"short_bias": 0.94, "long_bias": 1.04},
    "calm": {"short_bias": 0.76, "syncopation_bias": 0.86, "long_bias": 1.22},
    "caring": {"short_bias": 0.82, "syncopation_bias": 0.90, "long_bias": 1.18},
    "confusion": {"short_bias": 1.04, "syncopation_bias": 1.10, "long_bias": 0.98},
    "curiosity": {"short_bias": 1.12, "syncopation_bias": 1.12, "long_bias": 0.9},
    "desire": {"short_bias": 0.84, "syncopation_bias": 0.94, "long_bias": 1.12},
    "disappointment": {"short_bias": 0.82, "syncopation_bias": 0.88, "long_bias": 1.18},
    "disapproval": {"short_bias": 1.0, "syncopation_bias": 1.02, "long_bias": 0.96},
    "disgust": {"short_bias": 1.18, "syncopation_bias": 1.16, "long_bias": 0.86},
    "embarrassment": {"short_bias": 0.82, "syncopation_bias": 0.9, "long_bias": 1.14},
    "excitement": {"short_bias": 1.34, "syncopation_bias": 1.22, "long_bias": 0.72},
    "fear": {"short_bias": 1.08, "syncopation_bias": 1.12, "long_bias": 0.94},
    "gratitude": {"short_bias": 0.90, "long_bias": 1.08},
    "grief": {"short_bias": 0.72, "syncopation_bias": 0.82, "long_bias": 1.30},
    "joy": {"short_bias": 1.24, "syncopation_bias": 1.18, "long_bias": 0.78},
    "love": {"short_bias": 0.88, "syncopation_bias": 0.94, "long_bias": 1.12},
    "neutral": {"short_bias": 0.92, "syncopation_bias": 0.96, "long_bias": 1.04},
    "nervousness": {"short_bias": 1.22, "syncopation_bias": 1.16, "long_bias": 0.82},
    "optimism": {"short_bias": 1.18, "syncopation_bias": 1.1, "long_bias": 0.84},
    "peaceful": {"short_bias": 0.74, "syncopation_bias": 0.84, "long_bias": 1.24},
    "pride": {"short_bias": 1.0, "syncopation_bias": 0.98, "long_bias": 0.98},
    "realization": {"short_bias": 0.84, "syncopation_bias": 0.92, "long_bias": 1.12},
    "relief": {"short_bias": 0.80, "syncopation_bias": 0.88, "long_bias": 1.20},
    "remorse": {"short_bias": 0.74, "syncopation_bias": 0.84, "long_bias": 1.28},
    "sadness": {"short_bias": 0.80, "syncopation_bias": 0.86, "long_bias": 1.22},
    "serenity": {"short_bias": 0.72, "syncopation_bias": 0.82, "long_bias": 1.26},
    "surprise": {"short_bias": 1.18, "syncopation_bias": 1.22, "long_bias": 0.84},
}


def melody_rhythm_profile_for_emotion(emotion_name: str) -> Dict[str, float]:
    key = canonical_emotion_name(emotion_name or "")
    return dict(EMOTION_MELODY_RHYTHM_PROFILES.get(key, {}))
