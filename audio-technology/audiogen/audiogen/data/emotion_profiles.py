from __future__ import annotations

from typing import Any, Dict, Optional

from data.emotion_aliases import canonical_emotion_name

"""
Central per-emotion "mix + arrangement" intent tables.

These are deliberately lightweight, human-editable overrides that bias the system
toward sounding like the label. They are not meant to be exhaustive or to replace
style profiles / conversation presets; they are applied as a final, emotion-scoped
layer.
"""

def _clip(x: float, lo: float, hi: float) -> float:
    try:
        v = float(x)
    except Exception:
        v = 0.0
    return float(lo if v < lo else hi if v > hi else v)


def _energy(tempo_mult: float, velocity_mult: float, density: float) -> float:
    # Normalize each axis into a comparable range then average.
    t = _clip(float(tempo_mult), 0.35, 2.0)
    v = _clip(float(velocity_mult), 0.65, 1.25)
    d = _clip(float(density), 0.15, 1.0)
    # Map tempo ~[0.35..2.0] into ~[0..1]
    t01 = (t - 0.35) / (2.0 - 0.35)
    # Map velocity ~[0.65..1.25] into ~[0..1]
    v01 = (v - 0.65) / (1.25 - 0.65)
    # Density already near 0..1; clamp.
    d01 = _clip(d, 0.0, 1.0)
    return float((t01 + v01 + d01) / 3.0)


def derive_arrangement_overrides(
    *,
    emotion_name: str,
    tempo_multiplier: float,
    velocity_multiplier: float,
    density: float,
) -> Dict[str, Any]:
    """
    For emotions not explicitly tuned in EMOTION_ARRANGEMENT_OVERRIDES, derive a
    distinctive but stable bias from tempo/velocity/density.

    This keeps the system "emotionful" without requiring a giant hand-tuned table.
    """
    key = (emotion_name or "").strip().lower()
    e = _energy(tempo_multiplier, velocity_multiplier, density)

    # Activity / density
    melody_density_mult = 0.70 + 0.70 * e          # ~0.70..1.40
    melody_total_notes_mult = 0.78 + 0.52 * e      # ~0.78..1.30
    # More energy -> fewer rests.
    markov_rest_prob_mult = 1.20 - 0.45 * e        # ~0.75..1.20

    # Harmonic motion: energy -> more chord motion; low energy -> stickier pads.
    chord_motion_mult = 0.82 + 0.48 * e            # ~0.82..1.30
    chord_rhythm_mult = 0.86 + 0.34 * e            # ~0.86..1.20

    # Arp: more energy -> denser, but keep loudness stable across emotions.
    arp_target = 4.0 + 10.0 * e                    # ~4..14
    arp_target = _clip(arp_target, 4.0, 13.0)
    arp_density_mult = 0.75 + 0.75 * e             # ~0.75..1.50

    # Drone: more common for low energy, rarer for high energy.
    drone_enabled = 1.0 if e <= 0.42 else 0.0

    # Guardrails for known sparse/no-arp emotions.
    if key in {"grief", "relief"}:
        drone_enabled = 1.0 if key == "grief" else 0.0

    out: Dict[str, Any] = {
        "melody_density_mult": float(_clip(melody_density_mult, 0.55, 1.45)),
        "melody_total_notes_mult": float(_clip(melody_total_notes_mult, 0.60, 1.35)),
        "markov_rest_prob_mult": float(_clip(markov_rest_prob_mult, 0.72, 1.28)),
        "chord_motion_mult": float(_clip(chord_motion_mult, 0.75, 1.30)),
        "chord_rhythm_mult": float(_clip(chord_rhythm_mult, 0.80, 1.22)),
        "arp_target_notes_per_bar": float(arp_target),
        "arp_density_mult": float(_clip(arp_density_mult, 0.60, 1.55)),
        "arp_velocity_scale": 1.0,
        "drone_enabled": float(drone_enabled),
    }

    # Keep arp subtle for grief/relief, but present enough to glue the arrangement.
    if key in {"grief", "relief"}:
        out["arp_enabled"] = 1.0
        out["arp_density_mult"] = float(out.get("arp_density_mult", 1.0)) * 0.55
        out["arp_target_notes_per_bar"] = float(max(4.8, min(float(out.get("arp_target_notes_per_bar", 4.8)), 5.6)))
        out["arp_velocity_scale"] = float(out.get("arp_velocity_scale", 1.0)) * 0.82

    return out


# ---------------------------------------------------------------------------
# Arrangement overrides (merged into ArrangementPolicy.arrangement_curve)
# ---------------------------------------------------------------------------

# Keys should match those produced by ArrangementPolicy.arrangement_curve (see
# composition/policies.py). Values are simple scalars or booleans encoded as 0/1.
EMOTION_ARRANGEMENT_OVERRIDES: Dict[str, Dict[str, Any]] = {
    # Bright, forward motion; more activity and clearer chorus lift.
    "optimism": {
        "melody_density_mult": 1.10,
        "melody_total_notes_mult": 1.08,
        "markov_rest_prob_mult": 0.92,
        "chord_motion_mult": 1.10,
        "chord_rhythm_mult": 1.06,
        "arp_density_mult": 1.15,
        "arp_target_notes_per_bar": 10.0,
        "arp_velocity_scale": 1.0,
    },
    "admiration": {
        "melody_density_mult": 0.86,
        "melody_total_notes_mult": 0.92,
        "markov_rest_prob_mult": 1.06,
        "chord_motion_mult": 0.92,
        "chord_rhythm_mult": 0.92,
        "arp_density_mult": 0.85,
        "arp_target_notes_per_bar": 5.0,
        "arp_velocity_scale": 1.0,
        "drone_enabled": 1.0,
    },
    "amusement": {
        "melody_density_mult": 1.18,
        "melody_total_notes_mult": 1.12,
        "markov_rest_prob_mult": 0.90,
        "chord_motion_mult": 1.08,
        "chord_rhythm_mult": 1.08,
        "arp_density_mult": 1.18,
        "arp_target_notes_per_bar": 10.5,
        "arp_velocity_scale": 1.0,
        "drone_enabled": 0.0,
    },
    "approval": {
        "melody_density_mult": 1.04,
        "melody_total_notes_mult": 1.03,
        "markov_rest_prob_mult": 0.96,
        "chord_motion_mult": 1.04,
        "chord_rhythm_mult": 1.02,
        "arp_density_mult": 1.02,
        "arp_target_notes_per_bar": 7.0,
        "arp_velocity_scale": 1.0,
        "drone_enabled": 0.0,
    },
    "caring": {
        "melody_density_mult": 0.84,
        "melody_total_notes_mult": 0.90,
        "markov_rest_prob_mult": 1.04,
        "chord_motion_mult": 0.86,
        "chord_rhythm_mult": 0.88,
        "arp_enabled": 1.0,
        "arp_density_mult": 0.62,
        "arp_target_notes_per_bar": 5.2,
        "arp_velocity_scale": 0.84,
        "drone_enabled": 1.0,
    },
    # Default bed: keep it centered and not too busy.
    "neutral": {
        "melody_density_mult": 0.95,
        "melody_total_notes_mult": 0.95,
        "markov_rest_prob_mult": 1.02,
        "chord_motion_mult": 1.00,
        # Keep harmony diatonic/clean for neutral (reduce secondary-dominant/interchange pressure).
        "harmonic_color_mult": 0.88,
        "arp_density_mult": 0.95,
        "arp_target_notes_per_bar": 6.0,
        "arp_velocity_scale": 1.0,
    },
    # High-energy emotions: more motion and activity; less drone.
    "excitement": {
        "melody_density_mult": 1.22,
        "melody_total_notes_mult": 1.18,
        "markov_rest_prob_mult": 0.86,
        "chord_motion_mult": 1.18,
        "chord_rhythm_mult": 1.14,
        "arp_density_mult": 1.30,
        "arp_target_notes_per_bar": 12.0,
        "arp_velocity_scale": 1.0,
        "drone_enabled": 0.0,
    },
    "gratitude": {
        "melody_density_mult": 0.94,
        "melody_total_notes_mult": 0.98,
        "markov_rest_prob_mult": 1.00,
        "chord_motion_mult": 0.94,
        "chord_rhythm_mult": 0.94,
        "arp_enabled": 1.0,
        "arp_density_mult": 0.76,
        "arp_target_notes_per_bar": 5.8,
        "arp_velocity_scale": 0.90,
        "drone_enabled": 1.0,
    },
    "joy": {
        "melody_density_mult": 1.16,
        "melody_total_notes_mult": 1.12,
        "markov_rest_prob_mult": 0.88,
        "chord_motion_mult": 1.12,
        "chord_rhythm_mult": 1.08,
        "arp_density_mult": 1.22,
        "arp_target_notes_per_bar": 11.0,
        "arp_velocity_scale": 1.0,
        "drone_enabled": 0.0,
    },
    "love": {
        "melody_density_mult": 0.92,
        "melody_total_notes_mult": 0.97,
        "markov_rest_prob_mult": 1.00,
        "chord_motion_mult": 0.90,
        "chord_rhythm_mult": 0.90,
        "arp_enabled": 1.0,
        "arp_density_mult": 0.72,
        "arp_target_notes_per_bar": 5.8,
        "arp_velocity_scale": 0.90,
        "drone_enabled": 1.0,
    },
    "anger": {
        "melody_density_mult": 1.12,
        "melody_total_notes_mult": 1.10,
        "markov_rest_prob_mult": 0.90,
        "chord_motion_mult": 1.12,
        "chord_rhythm_mult": 1.10,
        "arp_density_mult": 1.15,
        "arp_target_notes_per_bar": 9.0,
        "arp_velocity_scale": 1.0,
        "drone_enabled": 0.0,
    },
    # Annoyance: less "bubbly", more tense/tight. Disable arp bed and
    # push harmony toward the Phrygian neighbor + unresolved motion.
    "annoyance": {
        "arp_enabled": 0.0,
        "arp_density_mult": 0.0,
        "arp_velocity_scale": 0.0,
        "arp_target_notes_per_bar": 0.0,
        "melody_density_mult": 0.92,
        "melody_total_notes_mult": 0.92,
        # A little more space (short, stabbing phrases rather than streams).
        "markov_rest_prob_mult": 1.08,
        "chord_motion_mult": 1.08,
        "chord_rhythm_mult": 1.10,
        "drone_enabled": 0.0,
    },
    # Fear: no arpeggio bed (tighter, more empty/tense texture).
    "fear": {
        "arp_enabled": 0.0,
        "arp_density_mult": 0.0,
        "arp_velocity_scale": 0.0,
        "arp_target_notes_per_bar": 0.0,
    },
    # Low-energy / negative valence: sparser, more rests, slower motion.
    "sadness": {
        "melody_density_mult": 0.96,
        "melody_total_notes_mult": 1.02,
        "markov_rest_prob_mult": 0.98,
        "chord_motion_mult": 0.84,
        "chord_rhythm_mult": 0.88,
        "arp_enabled": 1.0,
        "arp_density_mult": 0.82,
        "arp_target_notes_per_bar": 5.4,
        "arp_velocity_scale": 0.92,
        "drone_enabled": 1.0,
    },
    "disappointment": {
        "melody_density_mult": 0.91,
        "melody_total_notes_mult": 0.96,
        "markov_rest_prob_mult": 1.00,
        "chord_motion_mult": 0.88,
        "chord_rhythm_mult": 0.90,
        "arp_enabled": 1.0,
        "arp_density_mult": 0.72,
        "arp_target_notes_per_bar": 5.0,
        "arp_velocity_scale": 0.86,
        "drone_enabled": 1.0,
    },
    "grief": {
        "melody_density_mult": 0.82,
        "melody_total_notes_mult": 0.90,
        "markov_rest_prob_mult": 1.05,
        "chord_motion_mult": 0.75,
        "chord_rhythm_mult": 0.82,
        "arp_enabled": 1.0,
        "arp_density_mult": 0.52,
        "arp_target_notes_per_bar": 4.8,
        "arp_velocity_scale": 0.80,
        "drone_enabled": 1.0,
    },
    "remorse": {
        "melody_density_mult": 0.86,
        "melody_total_notes_mult": 0.91,
        "markov_rest_prob_mult": 1.04,
        "chord_motion_mult": 0.78,
        "chord_rhythm_mult": 0.84,
        "arp_enabled": 1.0,
        "arp_density_mult": 0.50,
        "arp_target_notes_per_bar": 4.8,
        "arp_velocity_scale": 0.78,
        "drone_enabled": 1.0,
    },
    "relief": {
        "melody_density_mult": 0.88,
        "melody_total_notes_mult": 0.93,
        "markov_rest_prob_mult": 1.02,
        "chord_motion_mult": 0.86,
        "chord_rhythm_mult": 0.88,
        "arp_enabled": 1.0,
        "arp_density_mult": 0.54,
        "arp_target_notes_per_bar": 5.0,
        "arp_velocity_scale": 0.82,
        "drone_enabled": 0.0,  # (player suppresses drone for relief already)
    },
    "surprise": {
        "melody_density_mult": 1.10,
        "melody_total_notes_mult": 1.06,
        "markov_rest_prob_mult": 0.94,
        "chord_motion_mult": 1.08,
        "chord_rhythm_mult": 1.10,
        "arp_density_mult": 1.06,
        "arp_target_notes_per_bar": 8.0,
        "arp_velocity_scale": 1.0,
        "drone_enabled": 0.0,
    },
}


def arrangement_overrides_for_emotion(
    emotion, *, default: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Get explicit override if present; otherwise derive from emotion scalars."""
    default = default or {}
    if emotion is None:
        return dict(default)
    key = canonical_emotion_name(getattr(emotion, "name", "") or "")
    explicit = EMOTION_ARRANGEMENT_OVERRIDES.get(key)
    base = dict(explicit) if explicit else derive_arrangement_overrides(
        emotion_name=key,
        tempo_multiplier=float(getattr(emotion, "tempo_multiplier", 1.0) or 1.0),
        velocity_multiplier=float(getattr(emotion, "velocity_multiplier", 1.0) or 1.0),
        density=float(getattr(emotion, "density", 0.5) or 0.5),
    )
    # Loudness stability: compensate section-level dynamics for extreme emotion velocity multipliers.
    # This keeps output amplitude more consistent across emotions while still allowing role curves
    # and per-channel velocity scales to shape dynamics.
    if "section_dynamic" not in base:
        try:
            vel = float(getattr(emotion, "velocity_multiplier", 1.0) or 1.0)
        except Exception:
            vel = 1.0
        # Inverse-power compensation (gentler than 1/vel): vel 1.25 -> ~0.86, vel 0.75 -> ~1.18
        comp = 1.0 / max(0.6, min(1.4, vel)) ** 0.75
        # Keep within the global clamp window used by normalize_arrangement_curve.
        base["section_dynamic"] = float(max(0.85, min(1.12, comp)))
    return base
