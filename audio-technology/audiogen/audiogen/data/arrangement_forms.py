from __future__ import annotations

from typing import Dict, Optional, Tuple

# Named section roles used by arrangement curves and section planners.
FORM_SEQUENCES: Dict[str, Tuple[str, ...]] = {
    # Default: simple radio-like arc.
    # intro → verse → pre-chorus → chorus → verse → chorus → outro
    "default": ("intro", "a", "pre_chorus", "b", "a", "b", "outro"),
    # Pop: intro, verse, chorus, verse, chorus, bridge, final chorus, outro
    "pop": ("intro", "a", "b", "a", "b", "b", "a_prime", "outro"),
    # Pop + pre-chorus before each chorus + hook tag before outro (11 sections).
    "pop_ext": (
        "intro",
        "a",
        "pre_chorus",
        "b",
        "a",
        "pre_chorus",
        "b",
        "b",
        "a_prime",
        "tag",
        "outro",
    ),
    # Rondo: intro, A, B, A', C, A', outro (contrasting episodes share the "b" curve)
    "rondo": ("intro", "a", "b", "a_prime", "b", "a_prime", "outro"),
    # Ballad: long intro, verse, lift, second verse, developed return, outro (6 sections).
    "ballad": ("intro", "a", "b", "a", "a_prime", "outro"),
    # Wave / build–drop: intro, riser, drop, breathe, final hit, outro (6 sections).
    "wave": ("intro", "pre_chorus", "b", "a", "b", "outro"),
    # Snowfall-like ambient arc (~2:00 @ ~95 BPM with 8-bar sections):
    # intro (pads) → A (bed) → B (hook) → A' (breathe) → B (hook return) → outro (fade)
    "snowfall": ("intro", "a", "b", "a_prime", "b", "outro"),
    # Anthem / cinematic-pop longform:
    # intro, verse, pre, chorus, post-hook, verse2, pre2, chorus2, bridge, build, final chorus, tag, outro
    "anthem": (
        "intro",
        "a",
        "pre_chorus",
        "b",
        "tag",
        "a",
        "pre_chorus",
        "b",
        "a_prime",
        "pre_chorus",
        "b",
        "tag",
        "outro",
    ),
}

# Shown in CLI (`arranged`) so users pick the right mode for verse–chorus motion.
ARRANGED_MODE_GUIDE: Dict[str, str] = {
    "ambient": (
        "5 timed sections with “default” curves (intro → A → B → A' → outro). "
        "B is a short contrast block, not a radio “chorus” with a second verse after."
    ),
    "default": (
        "7 sections: intro → verse → pre-chorus → chorus → verse → chorus → outro. "
        "Simple motion without the extra bridge/tag complexity of `pop_ext`."
    ),
    "pop": (
        "8 sections: intro → verse → chorus → verse → chorus → bridge → final chorus → outro. "
        "Best match when you want clear motion out of the first chorus into another verse."
    ),
    "rondo": (
        "7 sections: intro → A → B → A' → C → A' → outro (refrains vs episodes)."
    ),
    "pop_ext": (
        "11 sections: pop arc with pre-chorus before each chorus, hook tag, then outro. "
        "Stronger section boundaries + return-motif recall vs plain `pop`."
    ),
    "ballad": (
        "6 sections: intro → verse → chorus → verse → A' → outro. "
        "Longer edges, sparser verses, curves tuned for space and harmonic restraint vs `default`."
    ),
    "wave": (
        "6 sections: intro → build (pre-chorus curve) → drop → breakdown (verse) → drop → outro. "
        "Energy arc for electronic / hype-friendly motion without the full `pop_ext` section count."
    ),
    "snowfall": (
        "6 sections: intro → A (bed) → B (hook) → A' (breathe) → B (return) → outro. "
        "Loop-forward ambient arc with steady arp bed, slow chords, and memorable motif recall."
    ),
    "anthem": (
        "13 sections: intro → verse → pre → chorus → hook-tag → verse2 → pre2 → chorus2 "
        "→ bridge(A') → build(pre) → final chorus → tag → outro. "
        "Best for stronger narrative development and a bigger final payoff."
    ),
}


# ---------------------------------------------------------------------------
# Per-song form variety (2026-07-04, docs/AUDIOGEN_COMPOSITION_PLAN.md item 2)
# ---------------------------------------------------------------------------
# The generative path reads a single `arranged_song_mode` config value once and reuses it
# for every song in a session, so every generated song has the SAME section arc -- no
# structural variety across the continuous stream. `select_arranged_form` picks a form per
# song via a seeded, emotion-weighted choice so structure varies (one excitement song is a
# punchy pop arc, the next an anthem build) while staying musically appropriate to the
# emotion. Weighting is by energy (tempo_multiplier) and valence (anchor brightness), with a
# floor weight so any form *can* appear (real variety) but fitting ones dominate.

# The distinct structural forms available for auto-selection (each has its own builder in
# SongGenerator). Excludes `ambient`/`snowfall` (different builder signature / a dedicated
# ambient mode) -- those stay explicit opt-ins.
_AUTO_FORM_POOL = ("default", "ballad", "pop", "pop_ext", "rondo", "wave", "anthem")

# Per-form ideal (energy 0..1, brightness -1..1). Energy is where the form's build/motion
# sits; brightness is its tonal lean. Used as centers for a soft compatibility weight.
_FORM_CHARACTER = {
    "ballad":  (0.18, -0.10),   # slow, spacious, emotional
    "default": (0.42,  0.00),   # simple radio arc; the broad mid-energy fallback
    "rondo":   (0.58,  0.15),   # contrasting episodes; playful/curious
    "pop":     (0.62,  0.30),   # clear verse-chorus motion, positive
    "pop_ext": (0.75,  0.40),   # hooky, pre-chorus lifts, bright
    "wave":    (0.80,  0.00),   # build-drop energy, works dark or bright
    "anthem":  (0.86,  0.30),   # big cinematic longform payoff
}

_TEMPO_MIN, _TEMPO_MAX = 0.35, 1.90  # observed EmotionProfile.tempo_multiplier range


def _emotion_energy_brightness(emotion_name: str):
    """(energy 0..1 from tempo_multiplier, brightness -1..1 from anchor). Local imports to
    avoid a data-layer import cycle."""
    try:
        from data.music_data import EMOTION_BY_NAME
        from data.emotion_anchors import anchors_for_emotion

        emo = EMOTION_BY_NAME.get(str(emotion_name))
        tempo = float(getattr(emo, "tempo_multiplier", 1.0) or 1.0) if emo else 1.0
        brightness = float(getattr(anchors_for_emotion(str(emotion_name)), "brightness", 0.0) or 0.0)
    except Exception:
        tempo, brightness = 1.0, 0.0
    energy = (tempo - _TEMPO_MIN) / (_TEMPO_MAX - _TEMPO_MIN)
    return max(0.0, min(1.0, energy)), max(-1.0, min(1.0, brightness))


def arranged_form_weights(emotion_name: str, *, floor: float = 0.06) -> Dict[str, float]:
    """Weight over `_AUTO_FORM_POOL` for how well each form suits the emotion. Normalized to
    sum to 1.0. `floor` keeps every form reachable so structure still surprises."""
    import math

    e_energy, e_bright = _emotion_energy_brightness(emotion_name)
    raw: Dict[str, float] = {}
    for form in _AUTO_FORM_POOL:
        f_energy, f_bright = _FORM_CHARACTER[form]
        energy_fit = math.exp(-((e_energy - f_energy) / 0.30) ** 2)
        bright_fit = 1.0 - 0.5 * min(2.0, abs(e_bright - f_bright))  # 0.0..1.0-ish
        raw[form] = max(floor, energy_fit * (0.5 + 0.5 * bright_fit))
    total = sum(raw.values()) or 1.0
    return {k: v / total for k, v in raw.items()}


def select_arranged_form(
    emotion_name: str,
    *,
    seed: Optional[int] = None,
    avoid: str = "",
) -> str:
    """Pick one form for a song via seeded emotion-weighted choice. `avoid` (e.g. the
    previous song's form) is down-weighted so consecutive songs rarely repeat structure."""
    import random as _random

    weights = arranged_form_weights(emotion_name)
    if avoid and avoid in weights:
        weights = dict(weights)
        weights[avoid] *= 0.25  # discourage immediate repeats without forbidding them
        total = sum(weights.values()) or 1.0
        weights = {k: v / total for k, v in weights.items()}
    rng = _random.Random(seed) if seed is not None else _random
    forms = list(weights.keys())
    return rng.choices(forms, weights=[weights[f] for f in forms])[0]
