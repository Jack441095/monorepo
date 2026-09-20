# composition/markov_style_profiles.py
# Heuristic Markov style profiles (dataclasses) — distinct from data/sample_style_profiles.py.

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MarkovStyleProfile:
    """
    Small heuristic style profile used to bias Markov decisions.

    All fields are bounded, deterministic, and intended to be blended with strength knobs
    (defaults should preserve behavior when strength=0).
    """

    profile_id: str
    # 0..1: higher => allow more melodic leaps; lower => prefer stepwise motion.
    leap_allowance: float = 0.5
    # 0..1: higher => allow more harmonic rhythm motion; lower => steadier holds.
    harmony_motion_allowance: float = 0.5
    # 0..1: higher => allow more harmonic color ops (extensions/interchange/sec dom).
    harmony_color_allowance: float = 0.5
    # 0..1: higher => allow more short durations (busier rhythm); lower => longer notes.
    melody_rhythm_activity: float = 0.5


def _bucket_emotion(name: str) -> str:
    # 2026-07-02: 6/28 emotions were silently falling through to "neutral" (a generic
    # harmony-color allowance of 0.50), or worse — "disapproval" matched the "approval"
    # substring in the warm branch below and got bucketed as warm, backwards for a
    # negative-judgment emotion. Fixed by adding explicit keywords, ordered so
    # "disapproval"/"annoy"/"disgust"/"embarrass" are caught by an earlier (negative)
    # branch before they could ever reach the "approval" substring check. See
    # docs/AUDIOGEN_COMPOSITION_PLAN.md item 10/11.
    n = (name or "").strip().lower()
    if not n:
        return "neutral"
    if any(k in n for k in ("grief", "sad", "remorse", "disappointment", "melanch")):
        return "sad"
    if any(k in n for k in ("calm", "relax", "peace", "serene")):
        return "calm"
    if any(k in n for k in ("fear", "nervous", "anxiety", "tense", "confus", "embarrass")):
        return "tense"
    if any(k in n for k in ("anger", "rage", "furious", "annoy", "disgust", "disapproval")):
        return "angry"
    if any(k in n for k in ("joy", "excite", "optim", "amuse", "pride")):
        return "energetic"
    if any(k in n for k in ("love", "caring", "gratitude", "relief", "approval", "admir", "desir")):
        return "warm"
    if any(k in n for k in ("surprise", "realization", "curiosity")):
        return "curious"
    return "neutral"


def style_profile_for_emotion_and_role(
    emotion_name: str,
    section_role: Optional[str] = None,
) -> MarkovStyleProfile:
    """
    Deterministic heuristic profile.

    Intended semantics:
    - verses/pre sections: slightly steadier harmony + fewer colors
    - choruses/tags: more motion + a bit more color
    - intros/outros: steadier and less busy
    """

    bucket = _bucket_emotion(emotion_name)
    r = (section_role or "").strip().lower()

    # Base per-emotion defaults.
    base = {
        "sad": MarkovStyleProfile("sad", leap_allowance=0.25, harmony_motion_allowance=0.35, harmony_color_allowance=0.30, melody_rhythm_activity=0.35),
        "calm": MarkovStyleProfile("calm", leap_allowance=0.20, harmony_motion_allowance=0.30, harmony_color_allowance=0.25, melody_rhythm_activity=0.25),
        "tense": MarkovStyleProfile("tense", leap_allowance=0.45, harmony_motion_allowance=0.60, harmony_color_allowance=0.55, melody_rhythm_activity=0.55),
        "angry": MarkovStyleProfile("angry", leap_allowance=0.55, harmony_motion_allowance=0.70, harmony_color_allowance=0.60, melody_rhythm_activity=0.60),
        "energetic": MarkovStyleProfile("energetic", leap_allowance=0.55, harmony_motion_allowance=0.70, harmony_color_allowance=0.55, melody_rhythm_activity=0.65),
        "warm": MarkovStyleProfile("warm", leap_allowance=0.35, harmony_motion_allowance=0.45, harmony_color_allowance=0.45, melody_rhythm_activity=0.45),
        "curious": MarkovStyleProfile("curious", leap_allowance=0.45, harmony_motion_allowance=0.55, harmony_color_allowance=0.60, melody_rhythm_activity=0.50),
        "neutral": MarkovStyleProfile("neutral", leap_allowance=0.40, harmony_motion_allowance=0.50, harmony_color_allowance=0.50, melody_rhythm_activity=0.50),
    }.get(bucket, MarkovStyleProfile("neutral"))

    # Role nudge (bounded).
    la = float(base.leap_allowance)
    hm = float(base.harmony_motion_allowance)
    hc = float(base.harmony_color_allowance)
    ra = float(base.melody_rhythm_activity)

    if r in {"intro", "outro"}:
        # Stronger setup/release identity: steadier harmony and less rhythmic
        # lead activity so these roles read as form markers, not mini-choruses.
        la *= 0.88
        hm *= 0.72
        hc *= 0.74
        ra *= 0.62
    elif r in {"a", "verse"}:
        la *= 0.94
        hm *= 0.90
        hc *= 0.86
        ra *= 0.92
    elif r in {"pre_chorus"}:
        hm *= 1.06
        hc *= 0.95
        ra *= 1.03
    elif r in {"b", "chorus", "tag", "a_prime"}:
        hm *= 1.14
        hc *= 1.12
        ra *= 1.14

    def _cl01(x: float) -> float:
        return max(0.0, min(1.0, float(x)))

    return MarkovStyleProfile(
        profile_id=f"{base.profile_id}:{r or 'none'}",
        leap_allowance=_cl01(la),
        harmony_motion_allowance=_cl01(hm),
        harmony_color_allowance=_cl01(hc),
        melody_rhythm_activity=_cl01(ra),
    )
