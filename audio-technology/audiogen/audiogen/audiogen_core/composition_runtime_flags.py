"""Lazy readers for composition flags on ``CONFIG`` (deduplicated call sites)."""

from __future__ import annotations

from typing import Any


def markov_style_strength() -> float:
    try:
        from audiogen_core.config import CONFIG

        s = float(getattr(CONFIG.composition, "markov_style_strength", 0.0) or 0.0)
    except Exception:
        s = 0.0
    return max(0.0, min(1.0, float(s)))


def stable_emotion_dynamics_enabled() -> bool:
    try:
        from audiogen_core.config import CONFIG

        return bool(getattr(CONFIG.composition, "stable_emotion_dynamics", False))
    except Exception:
        return False


def stable_emotion_velocity_multiplier(emotion: Any) -> float:
    return 1.0 if stable_emotion_dynamics_enabled() else float(getattr(emotion, "velocity_multiplier", 1.0) or 1.0)


def motif_rhythm_only_enabled() -> bool:
    try:
        from audiogen_core.config import CONFIG

        return bool(getattr(CONFIG.composition, "motif_rhythm_only_enabled", False))
    except Exception:
        return False


def melody_position_conditioning() -> tuple[bool, float]:
    try:
        from audiogen_core.config import CONFIG

        pos_on = bool(getattr(CONFIG.composition, "melody_position_conditioning_enabled", False))
        pos_strength = float(getattr(CONFIG.composition, "melody_position_conditioning_strength", 0.75) or 0.75)
    except Exception:
        pos_on = False
        pos_strength = 0.75
    return pos_on, max(0.0, min(1.0, float(pos_strength)))


def tension_trajectory_params() -> tuple[bool, float]:
    try:
        from audiogen_core.config import CONFIG

        t_enabled = bool(getattr(CONFIG.composition, "tension_trajectory_enabled", True))
        t_strength = float(getattr(CONFIG.composition, "tension_trajectory_strength", 0.85))
    except Exception:
        t_enabled = True
        t_strength = 0.85
    return t_enabled, max(0.0, min(1.0, float(t_strength)))


def phrase_length_bars_clamped(lo: int = 1, hi: int = 16) -> int:
    try:
        from audiogen_core.config import CONFIG

        phrase_len = int(getattr(CONFIG.composition, "phrase_length_bars", 4) or 4)
    except Exception:
        phrase_len = 4
    return max(lo, min(hi, int(phrase_len)))


def superphrase_length_bars_clamped(lo: int = 1, hi: int = 32) -> int:
    try:
        from audiogen_core.config import CONFIG

        v = int(getattr(CONFIG.composition, "superphrase_length_bars", 8) or 8)
    except Exception:
        v = 8
    return max(lo, min(hi, int(v)))
