"""Per-emotion auto-mix bias (docs/AUDIOGEN_COMPOSITION_PLAN.md, auto-mixer work 2026-07-04).

data/delay_profiles.py deliberately keeps delay feedback GLOBAL across emotions ("global
sonic identity"). Per user direction, the auto-mixer takes the opposite approach for reverb
space and master EQ tilt: subtle, emotion-derived variation so emotions feel distinct while
the system still sounds like itself -- the same spirit as a mastering engineer letting songs
breathe differently within one consistent album sound.

Biases are derived from the SAME knobs generation already uses (EmotionAnchors.brightness,
EmotionProfile.tempo_multiplier/density) rather than a separate hand-tuned table, so this
can't drift out of sync with what an emotion actually sounds like (same design principle as
composition/emotion_fidelity.py).
"""
from __future__ import annotations

from dataclasses import dataclass

from data.emotion_anchors import anchors_for_emotion

# Deltas are intentionally small -- this nudges the existing global mix, it doesn't replace it.
_MAX_REVERB_WET_DELTA = 0.08
_MAX_EQ_SHELF_DELTA_DB = 1.2


@dataclass(frozen=True)
class AutoMixBias:
    reverb_wet_delta: float = 0.0
    eq_low_shelf_delta_db: float = 0.0
    eq_high_shelf_delta_db: float = 0.0


def auto_mix_bias_for_emotion(emotion) -> AutoMixBias:
    name = str(getattr(emotion, "name", "") or "")
    anchors = anchors_for_emotion(name)
    tempo_m = max(0.3, min(2.0, float(getattr(emotion, "tempo_multiplier", 1.0) or 1.0)))
    density = max(0.0, min(1.0, float(getattr(emotion, "density", 0.5) or 0.5)))
    brightness = float(getattr(anchors, "brightness", 0.0) or 0.0)

    # Slower / sparser / drone-preferring emotions get a touch more space (wetter reverb);
    # fast/dense emotions get a touch drier so they stay clear.
    tempo_term = (1.0 - tempo_m) * 0.05
    density_term = (0.5 - density) * 0.05
    drone_term = 0.03 if bool(getattr(anchors, "drone_preferred", False)) else 0.0
    reverb_wet_delta = max(
        -_MAX_REVERB_WET_DELTA, min(_MAX_REVERB_WET_DELTA, tempo_term + density_term + drone_term)
    )

    # Brightness anchor -> gentle tilt: bright emotions get a touch more high-shelf lift and
    # a touch less low-shelf lift (and vice versa for dark emotions).
    eq_high_shelf_delta_db = max(-_MAX_EQ_SHELF_DELTA_DB, min(_MAX_EQ_SHELF_DELTA_DB, brightness * 1.2))
    eq_low_shelf_delta_db = max(-_MAX_EQ_SHELF_DELTA_DB, min(_MAX_EQ_SHELF_DELTA_DB, -brightness * 0.8))

    return AutoMixBias(
        reverb_wet_delta=reverb_wet_delta,
        eq_low_shelf_delta_db=eq_low_shelf_delta_db,
        eq_high_shelf_delta_db=eq_high_shelf_delta_db,
    )
