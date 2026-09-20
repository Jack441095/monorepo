from __future__ import annotations

from typing import Dict

from data.emotion_aliases import canonical_emotion_name


EMOTION_MELODY_NOTE_PROFILES: Dict[str, Dict[str, float]] = {
    "admiration": {"note_target_mult": 0.84, "min_notes_per_bar": 2.7},
    "amusement": {"note_target_mult": 1.16, "min_notes_per_bar": 5.8},
    "anger": {"note_target_mult": 1.08, "min_notes_per_bar": 5.2},
    "annoyance": {"note_target_mult": 1.00, "min_notes_per_bar": 4.8},
    "approval": {"note_target_mult": 0.88, "min_notes_per_bar": 2.9},
    "calm": {"note_target_mult": 0.88, "min_notes_per_bar": 3.1},
    "caring": {"note_target_mult": 0.90, "min_notes_per_bar": 3.2},
    "confusion": {"note_target_mult": 0.98, "min_notes_per_bar": 4.2},
    "curiosity": {"note_target_mult": 1.12, "min_notes_per_bar": 5.4},
    "desire": {"note_target_mult": 0.90, "min_notes_per_bar": 3.8},
    "disappointment": {"note_target_mult": 0.92, "min_notes_per_bar": 3.4},
    "disapproval": {"note_target_mult": 0.96, "min_notes_per_bar": 4.0},
    "disgust": {"note_target_mult": 0.86, "min_notes_per_bar": 2.8},
    "embarrassment": {"note_target_mult": 0.86, "min_notes_per_bar": 3.0},
    "excitement": {"note_target_mult": 1.34, "min_notes_per_bar": 7.0},
    "fear": {"note_target_mult": 0.96, "min_notes_per_bar": 4.0},
    "gratitude": {"note_target_mult": 0.92, "min_notes_per_bar": 3.6},
    "grief": {"note_target_mult": 0.74, "min_notes_per_bar": 3.0},
    "joy": {"note_target_mult": 1.24, "min_notes_per_bar": 6.2},
    "love": {"note_target_mult": 0.78, "min_notes_per_bar": 2.5},
    "neutral": {"note_target_mult": 0.92, "min_notes_per_bar": 3.8},
    "nervousness": {"note_target_mult": 1.12, "min_notes_per_bar": 5.6},
    "optimism": {"note_target_mult": 1.12, "min_notes_per_bar": 5.6},
    "peaceful": {"note_target_mult": 0.86, "min_notes_per_bar": 3.0},
    "pride": {"note_target_mult": 1.00, "min_notes_per_bar": 4.6},
    "realization": {"note_target_mult": 0.88, "min_notes_per_bar": 3.4},
    "relief": {"note_target_mult": 0.74, "min_notes_per_bar": 3.0},
    "remorse": {"note_target_mult": 0.86, "min_notes_per_bar": 3.0},
    "sadness": {"note_target_mult": 0.68, "min_notes_per_bar": 3.8},
    "serenity": {"note_target_mult": 0.84, "min_notes_per_bar": 3.0},
    "surprise": {"note_target_mult": 1.18, "min_notes_per_bar": 5.8},
}


def melody_note_profile_for_emotion(emotion_name: str) -> Dict[str, float]:
    key = canonical_emotion_name(emotion_name or "")
    return dict(EMOTION_MELODY_NOTE_PROFILES.get(key, {}))
