from __future__ import annotations

from typing import Dict

from data.emotion_aliases import canonical_emotion_name


EMOTION_HARMONY_PROFILES: Dict[str, Dict[str, float]] = {
    "admiration": {
        "opening_maj": 3.0,
        "opening_dom": 0.7,
        "cadence_strength": 1.08,
        "deceptive_strength": 0.82,
    },
    "amusement": {
        "opening_maj": 2.9,
        "opening_dom": 1.18,
        "cadence_major": 1.18,
        "cadence_strength": 1.04,
        "deceptive_strength": 0.92,
    },
    "anger": {
        "opening_min": 2.8,
        "opening_dom": 1.35,
        "opening_dim": 0.72,
        "cadence_minor": 1.42,
        "cadence_dom": 1.24,
        "cadence_strength": 0.96,
        "deceptive_strength": 1.04,
    },
    "annoyance": {
        "opening_min": 2.4,
        "opening_dom": 1.08,
        "opening_dim": 0.62,
        "cadence_minor": 1.24,
        "cadence_strength": 0.84,
        "deceptive_strength": 1.22,
    },
    "approval": {
        "opening_maj": 2.5,
        "cadence_strength": 1.08,
        "deceptive_strength": 0.78,
    },
    "calm": {
        "opening_maj": 2.2,
        "cadence_strength": 0.92,
        "deceptive_strength": 0.82,
    },
    "caring": {
        "opening_maj": 2.4,
        "opening_min": 1.4,
        "cadence_strength": 1.02,
        "deceptive_strength": 0.78,
    },
    "confusion": {
        "opening_dom": 0.95,
        "opening_dim": 0.7,
        "cadence_strength": 0.82,
        "deceptive_strength": 1.22,
    },
    "curiosity": {
        "opening_maj": 2.2,
        "opening_dom": 0.9,
        "cadence_strength": 0.9,
        "deceptive_strength": 1.2,
    },
    "desire": {
        "opening_min": 1.9,
        "cadence_strength": 0.96,
        "deceptive_strength": 1.1,
    },
    "disappointment": {
        "opening_min": 2.8,
        "cadence_minor": 1.72,
        "cadence_major": 0.72,
        "cadence_strength": 0.95,
        "deceptive_strength": 1.08,
    },
    "disapproval": {
        "opening_min": 2.2,
        "opening_dom": 0.98,
        "opening_dim": 0.58,
        "cadence_minor": 1.16,
        "cadence_strength": 0.88,
        "deceptive_strength": 1.16,
    },
    "disgust": {
        "opening_min": 2.6,
        "opening_dom": 1.12,
        "opening_dim": 0.88,
        "cadence_minor": 1.34,
        "cadence_strength": 0.82,
        "deceptive_strength": 1.24,
    },
    "embarrassment": {
        "opening_min": 1.9,
        "cadence_strength": 0.88,
        "deceptive_strength": 1.15,
    },
    "excitement": {
        "opening_maj": 3.0,
        "opening_dom": 1.55,
        "cadence_strength": 1.12,
        "deceptive_strength": 0.85,
    },
    "fear": {
        "opening_min": 2.9,
        "opening_dom": 1.0,
        "opening_dim": 0.9,
        "cadence_major": 0.72,
        "cadence_minor": 1.5,
        "cadence_dom": 1.28,
        "cadence_strength": 0.8,
        "deceptive_strength": 1.28,
    },
    "gratitude": {
        "opening_maj": 2.9,
        "cadence_strength": 1.12,
        "deceptive_strength": 0.72,
    },
    "grief": {
        "opening_min": 3.0,
        "cadence_major": 0.7,
        "cadence_minor": 1.8,
        "cadence_strength": 0.92,
        "deceptive_strength": 1.18,
    },
    "joy": {
        "opening_maj": 3.1,
        "opening_dom": 0.82,
        "cadence_strength": 1.16,
        "deceptive_strength": 0.74,
    },
    "love": {
        "opening_maj": 2.4,
        "opening_min": 1.5,
        "cadence_strength": 1.05,
        "deceptive_strength": 0.84,
    },
    "neutral": {
        "opening_maj": 1.7,
        "opening_min": 1.0,
        "opening_dom": 0.52,
        "cadence_major": 1.22,
        "cadence_dom": 0.94,
        "cadence_strength": 0.78,
        "deceptive_strength": 1.0,
    },
    "nervousness": {
        "opening_min": 2.6,
        "opening_dom": 1.1,
        "opening_dim": 0.82,
        "cadence_strength": 0.86,
        "deceptive_strength": 1.3,
    },
    "optimism": {
        "opening_maj": 3.0,
        "opening_dom": 0.78,
        "cadence_strength": 1.1,
        "deceptive_strength": 0.82,
    },
    "peaceful": {
        "opening_maj": 2.2,
        "cadence_strength": 0.92,
        "deceptive_strength": 0.82,
    },
    "pride": {
        "opening_maj": 2.8,
        "opening_dom": 0.74,
        "cadence_strength": 1.08,
        "deceptive_strength": 0.8,
    },
    "realization": {
        "opening_dom": 1.15,
        "cadence_major": 1.55,
        "cadence_strength": 0.94,
        "deceptive_strength": 1.12,
    },
    "relief": {
        "opening_maj": 3.1,
        "opening_dom": 0.58,
        "cadence_major": 2.05,
        "cadence_dom": 1.0,
        "cadence_strength": 1.2,
        "deceptive_strength": 0.62,
    },
    "remorse": {
        "opening_min": 3.0,
        "cadence_major": 0.68,
        "cadence_minor": 1.78,
        "cadence_strength": 0.92,
        "deceptive_strength": 1.2,
    },
    "sadness": {
        "opening_min": 2.9,
        "cadence_major": 0.7,
        "cadence_minor": 1.72,
        "cadence_strength": 0.95,
        "deceptive_strength": 1.14,
    },
    "serenity": {
        "opening_maj": 2.2,
        "cadence_strength": 0.9,
        "deceptive_strength": 0.8,
    },
    "surprise": {
        "opening_dom": 1.6,
        "cadence_major": 1.4,
        "cadence_dom": 1.48,
        "cadence_strength": 1.02,
        "deceptive_strength": 1.08,
    },
}


def harmony_profile_for_emotion(emotion_name: str) -> Dict[str, float]:
    key = canonical_emotion_name(emotion_name or "")
    return dict(EMOTION_HARMONY_PROFILES.get(key, {}))
