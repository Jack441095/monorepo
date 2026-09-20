from __future__ import annotations

from typing import Dict, List

from data.emotion_aliases import canonical_emotion_name


# Small symbolic song-theme vocabulary.
#
# These are intentionally not raw MIDI phrases. Each profile is a compact
# emotional contour: pitch offsets from a local anchor plus note durations.
# The composition engine still chooses register, harmony, scale snapping, and
# section-specific development.
SONG_THEME_PROFILES: Dict[str, Dict[str, object]] = {
    "bright_lift": {
        "intervals": [0, 2, 4, 7, 5, 7],
        "rhythms": [0.5, 0.5, 1.0, 0.5, 1.0, 1.5],
        "contour": "rise_answer",
        "cadence_offset": 7,
        "hook_density": 0.78,
        "answer_offset": 4,
    },
    "tender_sigh": {
        "intervals": [0, 3, 2, 0, -2, 0],
        "rhythms": [0.75, 0.5, 0.75, 1.0, 0.5, 1.5],
        "contour": "arch_sigh",
        "cadence_offset": 0,
        "hook_density": 0.42,
        "answer_offset": -2,
    },
    "dark_fall": {
        "intervals": [0, 2, 0, -2, -5, -7],
        "rhythms": [1.0, 0.5, 0.5, 1.0, 1.0, 1.5],
        "contour": "falling",
        "cadence_offset": 0,
        "hook_density": 0.30,
        "answer_offset": -5,
    },
    "tense_pulse": {
        "intervals": [0, 1, 3, 1, 4, 2],
        "rhythms": [0.5, 0.5, 0.5, 0.5, 1.0, 1.0],
        "contour": "jagged",
        "cadence_offset": 2,
        "hook_density": 0.74,
        "answer_offset": 1,
    },
    "curious_question": {
        "intervals": [0, 2, 5, 4, 7, 5],
        "rhythms": [0.5, 1.0, 0.5, 1.0, 0.5, 1.0],
        "contour": "question",
        "cadence_offset": 5,
        "hook_density": 0.62,
        "answer_offset": 7,
    },
    "aversion_drop": {
        "intervals": [0, -1, 2, -2, -5, -3],
        "rhythms": [0.5, 0.5, 1.0, 0.5, 1.0, 1.0],
        "contour": "drop",
        "cadence_offset": -3,
        "hook_density": 0.55,
        "answer_offset": -5,
    },
    "neutral_arc": {
        "intervals": [0, 2, 4, 2, 0],
        "rhythms": [0.75, 0.75, 1.0, 0.75, 1.25],
        "contour": "balanced_arc",
        "cadence_offset": 0,
        "hook_density": 0.48,
        "answer_offset": 2,
    },
}


EMOTION_THEME_FAMILIES: Dict[str, str] = {
    "admiration": "bright_lift",
    "amusement": "bright_lift",
    "approval": "bright_lift",
    "excitement": "bright_lift",
    "joy": "bright_lift",
    "optimism": "bright_lift",
    "pride": "bright_lift",
    "caring": "tender_sigh",
    "desire": "tender_sigh",
    "gratitude": "tender_sigh",
    "love": "tender_sigh",
    "relief": "tender_sigh",
    "disappointment": "dark_fall",
    "grief": "dark_fall",
    "remorse": "dark_fall",
    "sadness": "dark_fall",
    "anger": "tense_pulse",
    "annoyance": "tense_pulse",
    "fear": "tense_pulse",
    "nervousness": "tense_pulse",
    "confusion": "curious_question",
    "curiosity": "curious_question",
    "realization": "curious_question",
    "surprise": "curious_question",
    "disapproval": "aversion_drop",
    "disgust": "aversion_drop",
    "embarrassment": "aversion_drop",
    "neutral": "neutral_arc",
}


def theme_family_for_emotion(emotion_name: str) -> str:
    key = canonical_emotion_name(str(emotion_name or ""))
    return str(EMOTION_THEME_FAMILIES.get(key, "neutral_arc"))


def song_theme_profile_for_emotion(emotion_name: str) -> Dict[str, object]:
    family = theme_family_for_emotion(str(emotion_name or ""))
    profile = dict(SONG_THEME_PROFILES.get(family, SONG_THEME_PROFILES["neutral_arc"]))
    profile["family"] = str(family)
    profile["emotion"] = canonical_emotion_name(str(emotion_name or ""))
    profile["intervals"] = [int(v) for v in list(profile.get("intervals", []) or [])]
    profile["rhythms"] = [float(v) for v in list(profile.get("rhythms", []) or [])]
    return profile


def all_song_theme_families() -> List[str]:
    return sorted(str(k) for k in SONG_THEME_PROFILES.keys())
