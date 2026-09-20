from __future__ import annotations

from typing import Dict

# Emotion-driven chord-change parameters used by ArrangementPolicy.chord_change_params().
# Values are multipliers/limits applied to chord planner anti-stuck logic.
CHORD_CHANGE_PARAMS: Dict[str, Dict[str, float]] = {
    "joy": {"max_repeats": 1, "force_prob": 0.62, "repeat_penalty": 0.10},
    "excitement": {"max_repeats": 1, "force_prob": 0.72, "repeat_penalty": 0.08},
    "amusement": {"max_repeats": 1, "force_prob": 0.6, "repeat_penalty": 0.08},
    "anger": {"max_repeats": 1, "force_prob": 0.58, "repeat_penalty": 0.12},
    "surprise": {"max_repeats": 1, "force_prob": 0.68, "repeat_penalty": 0.08},
    "pride": {"max_repeats": 1, "force_prob": 0.48, "repeat_penalty": 0.12},
    "optimism": {"max_repeats": 1, "force_prob": 0.52, "repeat_penalty": 0.12},
    "admiration": {"max_repeats": 1, "force_prob": 0.34, "repeat_penalty": 0.18},
    "approval": {"max_repeats": 2, "force_prob": 0.32, "repeat_penalty": 0.18},
    "curiosity": {"max_repeats": 1, "force_prob": 0.44, "repeat_penalty": 0.12},
    "gratitude": {"max_repeats": 2, "force_prob": 0.24, "repeat_penalty": 0.22},
    "fear": {"max_repeats": 1, "force_prob": 0.40, "repeat_penalty": 0.22},
    "nervousness": {"max_repeats": 1, "force_prob": 0.46, "repeat_penalty": 0.20},
    "annoyance": {"max_repeats": 1, "force_prob": 0.46, "repeat_penalty": 0.16},
    "disapproval": {"max_repeats": 1, "force_prob": 0.42, "repeat_penalty": 0.18},
    # Was sticky (high repeat_penalty); lift motion for restless / shifting harmony.
    "disgust": {"max_repeats": 1, "force_prob": 0.66, "repeat_penalty": 0.09},
    "desire": {"max_repeats": 2, "force_prob": 0.26, "repeat_penalty": 0.22},
    "realization": {"max_repeats": 2, "force_prob": 0.26, "repeat_penalty": 0.20},
    "embarrassment": {"max_repeats": 2, "force_prob": 0.34, "repeat_penalty": 0.18},
    "love": {"max_repeats": 2, "force_prob": 0.20, "repeat_penalty": 0.26},
    "disappointment": {"max_repeats": 2, "force_prob": 0.22, "repeat_penalty": 0.24},
    "remorse": {"max_repeats": 3, "force_prob": 0.16, "repeat_penalty": 0.30},
    "sadness": {"max_repeats": 3, "force_prob": 0.16, "repeat_penalty": 0.30},
    "relief": {"max_repeats": 2, "force_prob": 0.18, "repeat_penalty": 0.28},
    "caring": {"max_repeats": 3, "force_prob": 0.16, "repeat_penalty": 0.30},
    "grief": {"max_repeats": 3, "force_prob": 0.12, "repeat_penalty": 0.36},
    # Default “bed” emotion: push harder chord motion so progressions don’t sit on one function.
    "neutral": {"max_repeats": 2, "force_prob": 0.38, "repeat_penalty": 0.18},
}
