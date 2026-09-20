# composition/song_postprocess/form_polish/_constants.py
# Shared emotion/family sets used by the motif-development and hook-identity
# postprocess passes. Leaf module — no dependency on any sibling here.

from __future__ import annotations

_MOTIF_DEVELOPMENT_EMOTIONS = frozenset(
    {
        "admiration",
        "amusement",
        "approval",
        "confusion",
        "curiosity",
        "embarrassment",
        "excitement",
        "joy",
        "nervousness",
        "neutral",
        "optimism",
        "pride",
        "realization",
        "surprise",
    }
)
_MOTIF_DEVELOPMENT_FAMILIES = frozenset(
    {
        "bright_lift",
        "curious_question",
        "neutral_arc",
        "tense_pulse",
    }
)
# Phase-C audit: weak hook_identity on these primaries (chorus restatement).
_HOOK_IDENTITY_EMOTIONS = frozenset(
    {"surprise", "disapproval", "realization", "neutral", "love"}
)
