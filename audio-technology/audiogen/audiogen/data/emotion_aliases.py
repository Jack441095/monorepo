from __future__ import annotations

from typing import Dict


# Canonical emotion names used internally (must match `data/music_data.py`).
# This exists to keep CLI/user labels and exported filenames flexible.
#
# Examples: your reference renders include misspellings like `greif.wav` and
# `nutural.wav`. Without aliasing, those names won't hit the tuned tables.
EMOTION_ALIASES: Dict[str, str] = {
    # Common morphology
    "optimistic": "optimism",
    "nervous": "nervousness",
    "curious": "curiosity",
    "surprised": "surprise",
    "grateful": "gratitude",
    "embarrassed": "embarrassment",
    "sad": "sadness",
    "angry": "anger",

    # Misspellings from dataset / exports
    "nutural": "neutral",
    "excitment": "excitement",
    "amusment": "amusement",
    "greif": "grief",
    "disapointed": "disappointment",
    "disproval": "disapproval",
    "embaressed": "embarrassment",
}


def canonical_emotion_name(name: str) -> str:
    key = (name or "").strip().lower()
    if not key:
        return ""
    return EMOTION_ALIASES.get(key, key)
