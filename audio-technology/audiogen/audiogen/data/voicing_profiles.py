from __future__ import annotations

from typing import Dict, List, TypedDict

from data.emotion_aliases import canonical_emotion_name


class VoicingProfile(TypedDict, total=False):
    """
    Emotion-scoped harmonic voicing intent.

    This is intentionally small: it steers *how* chords are voiced (spread/shape),
    while channel register is primarily handled by `midi/midi_range_limiter.py`.
    """

    chord_styles: List[str]
    # If True, bias toward stable/close voicings to keep the harmonic bed calm.
    prefer_stable: bool


DEFAULT_VOICING_PROFILE: VoicingProfile = {
    # Piano/pop baseline: prefer standard comping shapes, avoid cluster-y stacks.
    "chord_styles": ["drop2", "shell", "tenth", "open", "closed"],
    "prefer_stable": False,
}


# Notes:
# - Styles must be supported by `composition/chord_utils.py` -> apply_voicing_style().
# - Order matters: the voice-leading engine explores earlier options first.
EMOTION_VOICING_PROFILES: Dict[str, VoicingProfile] = {
    # Bright/open, "played" harmony
    "joy": {"chord_styles": ["open", "tenth", "drop2", "closed"], "prefer_stable": False},
    "amusement": {"chord_styles": ["open", "drop2", "tenth", "closed"], "prefer_stable": False},
    "optimism": {"chord_styles": ["open", "tenth", "drop2", "closed"], "prefer_stable": False},
    "surprise": {"chord_styles": ["tenth", "open", "drop2", "closed"], "prefer_stable": False},
    "pride": {"chord_styles": ["tenth", "drop2", "open", "closed"], "prefer_stable": False},

    # Warm/soft, less busy
    "love": {"chord_styles": ["drop2", "open", "shell", "closed"], "prefer_stable": True},
    "admiration": {"chord_styles": ["drop2", "shell", "closed", "open"], "prefer_stable": True},
    "gratitude": {"chord_styles": ["drop2", "shell", "closed", "open"], "prefer_stable": True},
    "caring": {"chord_styles": ["shell", "drop2", "closed"], "prefer_stable": True},
    "calm": {"chord_styles": ["shell", "closed", "drop2"], "prefer_stable": True},
    "neutral": {"chord_styles": ["drop2", "closed", "shell", "open"], "prefer_stable": True},
    "relief": {"chord_styles": ["shell", "drop2", "closed"], "prefer_stable": True},

    # Darker/tense: tighter or more abrasive shells
    "sadness": {"chord_styles": ["closed", "drop2", "shell"], "prefer_stable": True},
    "grief": {"chord_styles": ["shell", "closed", "drop2"], "prefer_stable": True},
    "remorse": {"chord_styles": ["closed", "shell", "drop2"], "prefer_stable": True},
    "disappointment": {"chord_styles": ["closed", "shell", "drop2"], "prefer_stable": True},

    # Aggressive/edge: keep it punchy but still playable/clear (avoid quartal stacks by default).
    "anger": {"chord_styles": ["barre", "tenth", "drop2", "closed", "open"], "prefer_stable": False},
    "disapproval": {"chord_styles": ["barre", "drop2", "closed", "tenth"], "prefer_stable": False},
    "disgust": {"chord_styles": ["barre", "drop2", "closed", "tenth"], "prefer_stable": False},
    "annoyance": {"chord_styles": ["barre", "drop2", "closed"], "prefer_stable": False},

    # Uncertain/anxious: ambiguous shells but keep voicings clean (no quartal stacks by default).
    "fear": {"chord_styles": ["shell", "drop2", "closed", "open"], "prefer_stable": False},
    "nervousness": {"chord_styles": ["shell", "drop2", "closed", "open"], "prefer_stable": False},
    "confusion": {"chord_styles": ["shell", "drop2", "closed", "open"], "prefer_stable": False},
    "curiosity": {"chord_styles": ["open", "drop2", "shell", "closed"], "prefer_stable": False},
    "realization": {"chord_styles": ["drop2", "shell", "open", "closed"], "prefer_stable": True},
    "desire": {"chord_styles": ["drop2", "open", "shell", "closed"], "prefer_stable": True},
    "embarrassment": {"chord_styles": ["closed", "drop2", "shell"], "prefer_stable": True},
}


def voicing_profile_for_emotion(emotion_name: str) -> VoicingProfile:
    key = canonical_emotion_name(emotion_name)
    prof = EMOTION_VOICING_PROFILES.get(key)
    if not prof:
        return dict(DEFAULT_VOICING_PROFILE)
    # Merge with defaults so missing keys are filled.
    out: VoicingProfile = dict(DEFAULT_VOICING_PROFILE)
    out.update(dict(prof))
    return out

