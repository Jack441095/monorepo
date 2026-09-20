from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from data.emotion_aliases import canonical_emotion_name
from data.melody_phrase_profiles import melody_phrase_profile_for_emotion
from data.melody_rhythm_profiles import melody_rhythm_profile_for_emotion


@dataclass(frozen=True)
class EmotionMelodyPrior:
    """Sampler-facing melody intent for an emotion.

    The lower-level Markov model still supplies learned probabilities. These
    priors gently steer that distribution so each adjective has a distinct
    melodic contour and rhythmic feel even when the corpus is sparse.
    """

    name: str
    interval_step_mult: float = 1.0
    interval_small_leap_mult: float = 1.0
    interval_large_leap_mult: float = 1.0
    ascending_mult: float = 1.0
    descending_mult: float = 1.0
    repeat_mult: float = 1.0
    short_rhythm_mult: float = 1.0
    medium_rhythm_mult: float = 1.0
    long_rhythm_mult: float = 1.0
    cadence_closure_mult: float = 1.0
    description: str = ""


_BASE_PRIORS: Dict[str, EmotionMelodyPrior] = {
    # v012b+: admiration still trends short-heavy in diagnostics; give it a bit more long-breath pull.
    "admiration": EmotionMelodyPrior("admiration", 1.12, 0.96, 0.82, 1.04, 1.00, 1.02, 0.92, 1.04, 1.22, 1.10, "warm, lifted, mostly stepwise"),
    "amusement": EmotionMelodyPrior("amusement", 0.98, 1.14, 0.96, 1.12, 0.92, 0.88, 1.18, 1.04, 0.88, 0.92, "playful upward turns"),
    "anger": EmotionMelodyPrior("anger", 0.88, 1.18, 1.16, 1.03, 1.06, 0.74, 1.14, 0.98, 0.88, 0.78, "jagged, terse, unstable"),
    "annoyance": EmotionMelodyPrior("annoyance", 0.96, 1.08, 0.92, 0.98, 1.04, 0.76, 1.04, 1.00, 0.96, 0.84, "short irritated nudges"),
    "approval": EmotionMelodyPrior("approval", 1.08, 0.98, 0.84, 1.05, 0.98, 1.00, 1.05, 1.04, 0.98, 1.12, "clear stable affirmation"),
    "caring": EmotionMelodyPrior("caring", 1.28, 0.86, 0.62, 0.96, 1.10, 1.08, 0.82, 1.10, 1.20, 1.18, "gentle downward stepwise line"),
    "confusion": EmotionMelodyPrior("confusion", 0.96, 1.12, 1.06, 1.04, 1.02, 0.62, 1.10, 1.00, 0.94, 0.78, "questioning unsettled motion"),
    "curiosity": EmotionMelodyPrior("curiosity", 1.00, 1.12, 0.98, 1.14, 0.90, 0.88, 1.12, 1.06, 0.90, 0.88, "rising question shapes"),
    "desire": EmotionMelodyPrior("desire", 1.16, 0.98, 0.78, 1.02, 1.06, 1.04, 0.86, 1.10, 1.14, 1.05, "yearning, leaning stepwise"),
    "disappointment": EmotionMelodyPrior("disappointment", 1.22, 0.88, 0.64, 0.86, 1.22, 1.08, 0.82, 1.08, 1.18, 1.12, "sinking, resigned phrases"),
    "disapproval": EmotionMelodyPrior("disapproval", 1.00, 1.08, 0.88, 0.94, 1.10, 0.78, 1.00, 1.02, 0.98, 0.88, "firm downward refusal"),
    "disgust": EmotionMelodyPrior("disgust", 0.88, 1.12, 1.10, 0.92, 1.08, 0.72, 1.16, 0.92, 0.86, 0.72, "sour angular gestures"),
    "embarrassment": EmotionMelodyPrior("embarrassment", 1.18, 0.86, 0.58, 0.90, 1.16, 1.12, 0.84, 1.08, 1.14, 1.00, "small shy falling motions"),
    "excitement": EmotionMelodyPrior("excitement", 0.90, 1.22, 1.18, 1.20, 0.86, 0.78, 1.34, 1.02, 0.72, 0.84, "fast rising bursts"),
    "fear": EmotionMelodyPrior("fear", 0.86, 1.18, 1.26, 1.08, 1.02, 0.62, 1.14, 0.92, 0.82, 0.68, "fragmented, unresolved alarm"),
    "gratitude": EmotionMelodyPrior("gratitude", 1.16, 0.94, 0.72, 1.02, 1.04, 1.06, 0.90, 1.08, 1.10, 1.18, "settled heartfelt rise"),
    "grief": EmotionMelodyPrior("grief", 1.36, 0.74, 0.46, 0.72, 1.36, 1.16, 0.70, 1.08, 1.34, 1.22, "slow descending lament"),
    "joy": EmotionMelodyPrior("joy", 0.96, 1.18, 1.02, 1.18, 0.88, 0.84, 1.24, 1.04, 0.78, 0.96, "bright buoyant lift"),
    "love": EmotionMelodyPrior("love", 1.24, 0.90, 0.64, 0.98, 1.10, 1.10, 0.88, 1.10, 1.14, 1.20, "lyrical tender stepwise line"),
    "nervousness": EmotionMelodyPrior("nervousness", 1.02, 1.08, 1.00, 1.05, 1.02, 0.68, 1.24, 0.94, 0.78, 0.70, "restless short fragments"),
    "neutral": EmotionMelodyPrior("neutral", 1.04, 0.98, 0.82, 1.00, 1.00, 0.96, 0.92, 1.04, 1.04, 1.00, "balanced singable default"),
    "optimism": EmotionMelodyPrior("optimism", 0.98, 1.12, 0.94, 1.16, 0.90, 0.88, 1.18, 1.06, 0.84, 1.02, "hopeful rising motion"),
    "pride": EmotionMelodyPrior("pride", 0.98, 1.12, 1.04, 1.10, 0.94, 0.86, 1.00, 1.04, 0.98, 1.14, "broad confident arcs"),
    "realization": EmotionMelodyPrior("realization", 1.14, 0.96, 0.74, 1.03, 1.03, 1.02, 0.84, 1.08, 1.12, 1.16, "clarifying, settling line"),
    "relief": EmotionMelodyPrior("relief", 1.26, 0.84, 0.58, 0.90, 1.22, 1.12, 0.80, 1.10, 1.22, 1.28, "exhale and resolve"),
    "remorse": EmotionMelodyPrior("remorse", 1.30, 0.80, 0.54, 0.78, 1.30, 1.14, 0.74, 1.08, 1.28, 1.18, "penitent descending line"),
    "sadness": EmotionMelodyPrior("sadness", 1.28, 0.82, 0.58, 0.80, 1.26, 1.12, 0.78, 1.08, 1.24, 1.16, "slow stepwise descent"),
    "surprise": EmotionMelodyPrior("surprise", 0.86, 1.18, 1.20, 1.14, 0.92, 0.70, 1.18, 1.00, 0.84, 0.76, "sudden upward swerves"),
    "calm": EmotionMelodyPrior("calm", 1.24, 0.84, 0.56, 0.96, 1.10, 1.12, 0.76, 1.10, 1.24, 1.24, "quiet spacious stepwise motion"),
    "peaceful": EmotionMelodyPrior("peaceful", 1.26, 0.82, 0.54, 0.98, 1.08, 1.12, 0.74, 1.10, 1.26, 1.24, "serene long-breathed motion"),
    "serenity": EmotionMelodyPrior("serenity", 1.28, 0.80, 0.52, 0.98, 1.08, 1.14, 0.72, 1.08, 1.28, 1.24, "still, slowly resolving line"),
}


def _clamp(value: float, low: float = 0.35, high: float = 2.40) -> float:
    try:
        return max(float(low), min(float(high), float(value)))
    except Exception:
        return 1.0


def emotion_melody_prior_for(emotion_name: str) -> EmotionMelodyPrior:
    """Return a merged melody prior for a canonical or aliased emotion name."""

    key = canonical_emotion_name(emotion_name or "") or "neutral"
    base = _BASE_PRIORS.get(key, _BASE_PRIORS["neutral"])
    rhythm = melody_rhythm_profile_for_emotion(key)
    phrase = melody_phrase_profile_for_emotion(key)
    leap_bias = float(phrase.get("leap_bias", 1.0) or 1.0)
    return EmotionMelodyPrior(
        name=base.name,
        interval_step_mult=_clamp(base.interval_step_mult * max(0.75, 2.0 - leap_bias), 0.45, 2.0),
        interval_small_leap_mult=_clamp(base.interval_small_leap_mult * leap_bias, 0.35, 2.1),
        interval_large_leap_mult=_clamp(base.interval_large_leap_mult * leap_bias, 0.30, 2.2),
        ascending_mult=_clamp(base.ascending_mult, 0.45, 1.8),
        descending_mult=_clamp(base.descending_mult, 0.45, 1.8),
        repeat_mult=_clamp(base.repeat_mult, 0.35, 1.6),
        short_rhythm_mult=_clamp(base.short_rhythm_mult * float(rhythm.get("short_bias", 1.0) or 1.0), 0.35, 2.0),
        medium_rhythm_mult=_clamp(base.medium_rhythm_mult, 0.45, 1.8),
        long_rhythm_mult=_clamp(base.long_rhythm_mult * float(rhythm.get("long_bias", 1.0) or 1.0), 0.35, 2.2),
        cadence_closure_mult=_clamp(base.cadence_closure_mult, 0.35, 1.8),
        description=base.description,
    )


EMOTION_MELODY_PRIORS: Dict[str, EmotionMelodyPrior] = {
    name: emotion_melody_prior_for(name) for name in sorted(_BASE_PRIORS)
}
