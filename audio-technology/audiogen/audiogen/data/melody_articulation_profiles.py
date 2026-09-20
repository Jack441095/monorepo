from __future__ import annotations

from typing import Dict

from data.emotion_aliases import canonical_emotion_name


EMOTION_MELODY_ARTICULATION_PROFILES: Dict[str, Dict[str, float]] = {
    "admiration": {"gate_mult": 0.96, "velocity_mult": 1.02},
    "amusement": {"gate_mult": 0.84, "velocity_mult": 1.06},
    "anger": {"gate_mult": 0.82, "velocity_mult": 1.10},
    "annoyance": {"gate_mult": 0.84, "velocity_mult": 1.08},
    "approval": {"gate_mult": 0.94, "velocity_mult": 1.02},
    "calm": {"gate_mult": 1.08, "velocity_mult": 0.96},
    "caring": {"gate_mult": 1.1, "velocity_mult": 0.95},
    "confusion": {"gate_mult": 0.9, "velocity_mult": 1.0},
    "curiosity": {"gate_mult": 0.88, "velocity_mult": 1.02},
    "desire": {"gate_mult": 1.02, "velocity_mult": 0.98},
    "disappointment": {"gate_mult": 1.06, "velocity_mult": 0.94},
    "disapproval": {"gate_mult": 0.86, "velocity_mult": 1.08},
    "disgust": {"gate_mult": 0.74, "velocity_mult": 1.12},
    "embarrassment": {"gate_mult": 0.94, "velocity_mult": 0.96},
    "excitement": {"gate_mult": 0.76, "velocity_mult": 1.10},
    "fear": {"gate_mult": 0.82, "velocity_mult": 1.04},
    "gratitude": {"gate_mult": 1.02, "velocity_mult": 0.98},
    "grief": {"gate_mult": 1.14, "velocity_mult": 0.92},
    "joy": {"gate_mult": 0.8, "velocity_mult": 1.08},
    "love": {"gate_mult": 1.08, "velocity_mult": 0.98},
    "neutral": {"gate_mult": 0.96, "velocity_mult": 1.0},
    "nervousness": {"gate_mult": 0.8, "velocity_mult": 1.04},
    "optimism": {"gate_mult": 0.84, "velocity_mult": 1.06},
    "peaceful": {"gate_mult": 1.12, "velocity_mult": 0.95},
    "pride": {"gate_mult": 0.9, "velocity_mult": 1.05},
    "realization": {"gate_mult": 0.98, "velocity_mult": 0.98},
    "relief": {"gate_mult": 1.12, "velocity_mult": 0.96},
    "remorse": {"gate_mult": 1.12, "velocity_mult": 0.92},
    "sadness": {"gate_mult": 1.08, "velocity_mult": 0.94},
    "serenity": {"gate_mult": 1.14, "velocity_mult": 0.94},
    "surprise": {"gate_mult": 0.82, "velocity_mult": 1.10},
}


def melody_articulation_profile_for_emotion(emotion_name: str) -> Dict[str, float]:
    key = canonical_emotion_name(emotion_name or "")
    return dict(EMOTION_MELODY_ARTICULATION_PROFILES.get(key, {}))
