from __future__ import annotations

from typing import Any, Dict


STYLE_ARCHITECTURE_MACROS: Dict[str, Dict[str, Any]] = {
    # Neutral baseline.
    "default": {
        "melody_amount_scale": 0.82,
        "motif_use_chance": 0.88,
        "motif_variation_prob": 0.12,
        "extension_prob": 0.30,
        "interchange_prob": 0.20,
        "secondary_dominant_prob": 0.15,
        "chord_comping_strength": 0.80,
        "chord_comping_anticipation_prob": 0.06,
        "swing_enabled": False,
        "melody_swing_enabled": False,
    },
    # Hook-forward, cleaner harmony, lower harmonic surprise.
    "pop": {
        "melody_amount_scale": 0.92,
        "motif_use_chance": 0.94,
        "motif_variation_prob": 0.10,
        "extension_prob": 0.16,
        "interchange_prob": 0.08,
        "secondary_dominant_prob": 0.10,
        "chord_comping_strength": 0.70,
        "chord_comping_anticipation_prob": 0.04,
        "cadence_strength": 1.35,
        "melody_cadence_strength": 1.30,
        "swing_enabled": False,
        "melody_swing_enabled": False,
    },
    # Richer harmony and more syncopated feel.
    "jazz": {
        "melody_amount_scale": 0.78,
        "motif_use_chance": 0.84,
        "motif_variation_prob": 0.16,
        "extension_prob": 0.56,
        "interchange_prob": 0.34,
        "secondary_dominant_prob": 0.28,
        "chord_comping_strength": 0.92,
        "chord_comping_anticipation_prob": 0.10,
        "use_voice_leading": True,
        "humanization_enabled": True,
        "humanization_amount": 0.03,
        "swing_enabled": True,
        "swing_amount": 0.08,
        "melody_swing_enabled": True,
        "melody_swing_amount": 0.10,
    },
    # Spacious, less busy movement.
    "ambient": {
        "melody_amount_scale": 0.62,
        "motif_use_chance": 0.80,
        "motif_variation_prob": 0.08,
        "extension_prob": 0.34,
        "interchange_prob": 0.22,
        "secondary_dominant_prob": 0.08,
        "chord_comping_strength": 0.86,
        "chord_comping_anticipation_prob": 0.02,
        "texture_fx_gesture_strength": 0.40,
        "harmony_tension_control_strength": 0.20,
        "swing_enabled": False,
        "melody_swing_enabled": False,
    },
}


STYLE_ALIASES = {
    "standard": "default",
    "neutral": "default",
}


def canonical_style_name(name: str) -> str:
    key = str(name or "").strip().lower()
    if key in STYLE_ARCHITECTURE_MACROS:
        return key
    return str(STYLE_ALIASES.get(key, key))


def apply_style_architecture(comp: Any, style_name: str) -> bool:
    """
    Apply style macro values onto a composition config object.
    Returns True if a matching macro was applied.
    """
    key = canonical_style_name(style_name)
    macro = STYLE_ARCHITECTURE_MACROS.get(key)
    if not isinstance(macro, dict) or comp is None:
        return False
    for field, value in macro.items():
        try:
            setattr(comp, str(field), value)
        except Exception:
            pass
    return True
