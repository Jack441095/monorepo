from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class EmotionAnchors:
    """
    Small, explicit "semantic anchors" for an emotion.

    These are not full presets; they are stable intent knobs that bias arrangement +
    generation toward perceptual emotion clarity (texture, cadence feel, rhythmic feel,
    tension arc).
    """

    # Texture / instrumentation intent.
    arp_allowed: bool = True
    drone_preferred: bool = False

    # Cadence archetype: affects harmonic-color/motion and restiness.
    # Values: "authentic" | "plagal" | "avoid" | "suspended"
    cadence: str = "authentic"

    # Rhythm feel intent: 0..1 swing amount (mapped to arp swing),
    # and a 0..1 "syncopation bias" used as a light multiplier.
    swing: float = 0.0
    syncopation: float = 0.5

    # Tension arc template: "rise" | "fall" | "flat" | "spike"
    tension_arc: str = "rise"

    # Global brightness: -1..+1 (drives harmonic color + restiness bias).
    brightness: float = 0.0


# Explicit anchors for all emotion presets.
# These should be stable, human-editable, and represent "perceptual intent" rather than
# micro-tuning. (Fine-grain tuning still lives in the other override tables.)
EMOTION_ANCHORS: Dict[str, EmotionAnchors] = {
    # Gold standards / references
    "optimism": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="authentic",
        swing=0.02,
        syncopation=0.70,
        tension_arc="rise",
        brightness=0.55,
    ),
    "neutral": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="authentic",
        swing=0.0,
        syncopation=0.48,
        tension_arc="flat",
        brightness=0.0,
    ),
    "admiration": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=True,
        cadence="plagal",
        swing=0.0,
        syncopation=0.30,
        tension_arc="fall",
        brightness=0.25,
    ),

    # Bright / playful
    "joy": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="authentic",
        swing=0.03,
        syncopation=0.75,
        tension_arc="rise",
        brightness=0.70,
    ),
    "amusement": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="authentic",
        swing=0.06,
        syncopation=0.82,
        tension_arc="spike",
        brightness=0.65,
    ),
    "excitement": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="authentic",
        swing=0.01,
        syncopation=0.88,
        tension_arc="spike",
        brightness=0.80,
    ),
    "pride": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="authentic",
        swing=0.01,
        syncopation=0.62,
        tension_arc="rise",
        brightness=0.45,
    ),
    "approval": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="authentic",
        swing=0.0,
        syncopation=0.44,
        tension_arc="flat",
        brightness=0.25,
    ),
    "gratitude": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=True,
        cadence="plagal",
        swing=0.0,
        syncopation=0.30,
        tension_arc="fall",
        brightness=0.15,
    ),
    "love": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=True,
        cadence="plagal",
        swing=0.0,
        syncopation=0.26,
        tension_arc="fall",
        brightness=0.10,
    ),
    "caring": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=True,
        cadence="plagal",
        swing=0.0,
        syncopation=0.24,
        tension_arc="fall",
        brightness=0.05,
    ),

    # Tense / aggressive
    "anger": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="authentic",
        swing=0.0,
        syncopation=0.72,
        tension_arc="spike",
        brightness=0.35,
    ),
    "annoyance": EmotionAnchors(
        # Annoyance reads "bubbly" if the arp bed is present; keep it tighter/emptier.
        arp_allowed=False,
        drone_preferred=False,
        cadence="avoid",
        swing=0.0,
        # Slightly more choppy/off-kilter to feel irritated.
        syncopation=0.66,
        tension_arc="spike",
        brightness=-0.15,
    ),
    "disapproval": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="avoid",
        swing=0.0,
        syncopation=0.52,
        tension_arc="flat",
        brightness=-0.05,
    ),
    "disgust": EmotionAnchors(
        # The constant arp bed tends to "beautify" the affect; keep it more sparse/stabby.
        arp_allowed=False,
        drone_preferred=False,
        cadence="avoid",
        swing=0.0,
        syncopation=0.62,
        tension_arc="spike",
        brightness=-0.20,
    ),
    "nervousness": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="avoid",
        swing=0.0,
        syncopation=0.78,
        tension_arc="spike",
        brightness=0.10,
    ),
    "surprise": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="suspended",
        swing=0.0,
        syncopation=0.80,
        tension_arc="spike",
        brightness=0.35,
    ),
    "confusion": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="avoid",
        swing=0.0,
        syncopation=0.60,
        tension_arc="flat",
        brightness=-0.05,
    ),

    # Explicit request: fear should not have an arp bed.
    "fear": EmotionAnchors(
        arp_allowed=False,
        drone_preferred=False,
        cadence="avoid",
        swing=0.0,
        syncopation=0.35,
        tension_arc="spike",
        brightness=-0.25,
    ),

    # Curious / yearning
    "curiosity": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="suspended",
        swing=0.0,
        syncopation=0.70,
        tension_arc="rise",
        brightness=0.25,
    ),
    "realization": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="authentic",
        swing=0.0,
        syncopation=0.40,
        tension_arc="rise",
        brightness=0.20,
    ),
    "desire": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=True,
        cadence="suspended",
        swing=0.0,
        syncopation=0.42,
        tension_arc="rise",
        brightness=0.05,
    ),

    # Low-energy / negative valence
    "sadness": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=True,
        cadence="plagal",
        swing=0.0,
        syncopation=0.22,
        tension_arc="fall",
        brightness=-0.35,
    ),
    "grief": EmotionAnchors(
        # Allow arp, but keep it extremely subtle via curve overrides below.
        arp_allowed=True,
        drone_preferred=True,
        cadence="avoid",
        swing=0.0,
        syncopation=0.10,
        tension_arc="fall",
        brightness=-0.55,
    ),
    "remorse": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=True,
        cadence="avoid",
        swing=0.0,
        syncopation=0.18,
        tension_arc="fall",
        brightness=-0.45,
    ),
    "disappointment": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=True,
        cadence="avoid",
        swing=0.0,
        syncopation=0.18,
        tension_arc="fall",
        brightness=-0.40,
    ),
    "embarrassment": EmotionAnchors(
        arp_allowed=True,
        drone_preferred=False,
        cadence="avoid",
        swing=0.0,
        syncopation=0.36,
        tension_arc="flat",
        brightness=-0.10,
    ),
    "relief": EmotionAnchors(
        # Allow arp, but keep it extremely subtle via curve overrides below.
        arp_allowed=True,
        drone_preferred=False,
        cadence="authentic",
        swing=0.0,
        syncopation=0.18,
        tension_arc="fall",
        brightness=0.05,
    ),
}


def anchors_for_emotion(emotion: Any) -> EmotionAnchors:
    """
    Return anchors for an EmotionProfile-like object (or name string).
    Unknown emotions fall back to a small derived anchor from scalar energy.
    """
    name = ""
    try:
        name = str(getattr(emotion, "name", emotion) or "").strip().lower()
    except Exception:
        name = str(emotion or "").strip().lower()

    explicit = EMOTION_ANCHORS.get(name)
    if explicit is not None:
        return explicit

    # Derived fallback: use tempo/velocity/density to set a sensible feel.
    try:
        tempo = float(getattr(emotion, "tempo_multiplier", 1.0) or 1.0)
        vel = float(getattr(emotion, "velocity_multiplier", 1.0) or 1.0)
        dens = float(getattr(emotion, "density", 0.5) or 0.5)
    except Exception:
        tempo, vel, dens = 1.0, 1.0, 0.5

    energy = (tempo + vel + dens) / 3.0
    bright = (energy - 0.95) / 0.35  # roughly -1..+1 around typical mid-point
    bright = max(-1.0, min(1.0, float(bright)))

    # Lower-energy emotions tend to want drones and less syncopation.
    drone = energy <= 0.55
    sync = max(0.25, min(0.80, 0.45 + 0.35 * max(0.0, min(1.0, (energy - 0.7) / 0.5))))

    # Very tense/low energy: avoid strong authentic cadences.
    cadence = "authentic"
    if energy <= 0.55:
        cadence = "plagal"
    if name in {"grief", "remorse", "sadness", "disappointment"}:
        cadence = "avoid"

    # Swing is generally subtle; leave at 0 unless explicitly authored.
    return EmotionAnchors(
        arp_allowed=(name not in {"grief", "relief"}),  # legacy intent compatibility
        drone_preferred=bool(drone),
        cadence=str(cadence),
        swing=0.0,
        syncopation=float(sync),
        tension_arc="rise" if energy >= 0.75 else "flat",
        brightness=float(bright),
    )


def anchor_curve_overrides(
    emotion: Any,
    *,
    section_role: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Map anchors into ArrangementPolicy curve keys (pure overrides).
    """
    a = anchors_for_emotion(emotion)
    role = (section_role or "").lower()

    out: Dict[str, Any] = {}

    # Texture: if arp isn't allowed, force it off.
    if not bool(a.arp_allowed):
        out["arp_enabled"] = 0.0
        out["arp_density_mult"] = 0.0
        out["arp_target_notes_per_bar"] = 0.0
        out["arp_velocity_scale"] = 0.0
    else:
        # Subtle arp for grief/relief: keep timing grid intact but reduce
        # density and level so it supports the bed without becoming bright.
        try:
            n = str(getattr(emotion, "name", "") or "").strip().lower()
        except Exception:
            n = ""
        if n in {"grief", "relief"}:
            out["arp_enabled"] = max(float(out.get("arp_enabled", 1.0) or 1.0), 1.0)
            out["arp_density_mult"] = float(out.get("arp_density_mult", 1.0)) * 0.62
            out["arp_velocity_scale"] = float(out.get("arp_velocity_scale", 1.0)) * 0.84

    # Drone preference: allow intros/outros to carry it even if role curve disables.
    if bool(a.drone_preferred) and role in {"intro", "outro", "a_prime"}:
        out["drone_enabled"] = 1.0

    # Cadence archetype: bias harmonic color + motion and lead restiness.
    cad = (a.cadence or "authentic").lower()
    if cad == "plagal":
        out["harmonic_color_mult"] = 0.92
        out["chord_motion_mult"] = 0.94
        out["markov_rest_prob_mult"] = 1.06
    elif cad == "avoid":
        out["harmonic_color_mult"] = 1.04  # color substitutions can imply instability
        out["chord_motion_mult"] = 0.90
        out["markov_rest_prob_mult"] = 1.12
    elif cad == "suspended":
        out["harmonic_color_mult"] = 1.02
        out["chord_rhythm_mult"] = 1.10
        out["markov_rest_prob_mult"] = 1.02
    else:  # authentic
        out["harmonic_color_mult"] = 1.02
        out["chord_motion_mult"] = 1.02

    # Rhythmic feel: map swing 0..1 to small arp swing window (0..0.12).
    try:
        out["arp_swing"] = max(0.0, min(0.12, float(a.swing) * 0.12))
    except Exception:
        out["arp_swing"] = 0.0

    # Syncopation bias: small multipliers for arp density + melody density.
    try:
        s = max(0.0, min(1.0, float(a.syncopation)))
        out["arp_density_mult"] = float(out.get("arp_density_mult", 1.0)) * (0.90 + 0.30 * s)
        out["melody_density_mult"] = float(out.get("melody_density_mult", 1.0)) * (0.92 + 0.18 * s)
    except Exception:
        pass

    # Brightness: bias harmonic color and restiness slightly.
    try:
        b = max(-1.0, min(1.0, float(a.brightness)))
        out["harmonic_color_mult"] = float(out.get("harmonic_color_mult", 1.0)) * (1.0 + 0.10 * b)
        out["markov_rest_prob_mult"] = float(out.get("markov_rest_prob_mult", 1.0)) * (1.0 - 0.06 * b)
    except Exception:
        pass

    return out
