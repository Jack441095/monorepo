"""Map emotion anchor ``tension_arc`` templates to per-role dynamics."""

from __future__ import annotations

from typing import Any, Dict

from data.emotion_aliases import canonical_emotion_name

# Target ``section_dynamic`` multipliers by role (1.0 = neutral reference).
_TENSION_ARC_SECTION_DYNAMIC: Dict[str, Dict[str, float]] = {
    "flat": {
        "intro": 0.94,
        "a": 0.96,
        "verse": 0.96,
        "pre_chorus": 0.98,
        "b": 1.02,
        "chorus": 1.02,
        "hook": 1.02,
        "tag": 1.02,
        "a_prime": 0.98,
        "outro": 0.90,
        "ending": 0.90,
    },
    "fall": {
        "intro": 1.00,
        "a": 0.98,
        "verse": 0.96,
        "pre_chorus": 0.92,
        "b": 0.88,
        "chorus": 0.86,
        "hook": 0.86,
        "tag": 0.84,
        "a_prime": 0.90,
        "outro": 0.78,
        "ending": 0.78,
    },
    "rise": {
        "intro": 0.86,
        "a": 0.94,
        "verse": 0.94,
        "pre_chorus": 1.02,
        "b": 1.10,
        "chorus": 1.10,
        "hook": 1.10,
        "tag": 1.11,
        "a_prime": 0.98,
        "outro": 0.90,
        "ending": 0.90,
    },
    "spike": {
        "intro": 0.88,
        "a": 0.92,
        "verse": 0.94,
        "pre_chorus": 1.06,
        "b": 1.14,
        "chorus": 1.14,
        "hook": 1.16,
        "tag": 1.16,
        "a_prime": 1.04,
        "outro": 0.76,
        "ending": 0.76,
    },
}

# Whole-song professionalizer velocity multipliers (postprocess).
_TENSION_ARC_ROLE_VELOCITY: Dict[str, Dict[str, float]] = {
    "flat": {
        "intro": 0.92,
        "a": 0.94,
        "verse": 0.94,
        "pre_chorus": 0.96,
        "b": 1.00,
        "chorus": 1.00,
        "hook": 1.00,
        "tag": 1.00,
        "a_prime": 0.96,
        "outro": 0.90,
        "ending": 0.90,
    },
    "fall": {
        "intro": 0.98,
        "a": 0.96,
        "verse": 0.94,
        "pre_chorus": 0.92,
        "b": 0.88,
        "chorus": 0.86,
        "hook": 0.86,
        "tag": 0.84,
        "a_prime": 0.92,
        "outro": 0.80,
        "ending": 0.80,
    },
    "rise": {
        "intro": 0.84,
        "a": 0.92,
        "verse": 0.92,
        "pre_chorus": 1.00,
        "b": 1.08,
        "chorus": 1.08,
        "hook": 1.08,
        "tag": 1.09,
        "a_prime": 0.96,
        "outro": 0.88,
        "ending": 0.88,
    },
    "spike": {
        "intro": 0.86,
        "a": 0.90,
        "verse": 0.92,
        "pre_chorus": 1.04,
        "b": 1.12,
        "chorus": 1.12,
        "hook": 1.14,
        "tag": 1.14,
        "a_prime": 1.02,
        "outro": 0.78,
        "ending": 0.78,
    },
}


def _normalize_role(role: str) -> str:
    r = str(role or "").strip().lower()
    if r in {"chorus", "hook", "tag"}:
        return r
    if r in {"verse"}:
        return "a"
    if r in {"ending"}:
        return "outro"
    return r if r else "a"


def tension_arc_for_emotion(emotion_name: str) -> str:
    try:
        from data.emotion_anchors import EMOTION_ANCHORS

        emo = canonical_emotion_name(str(emotion_name or ""))
        anc = EMOTION_ANCHORS.get(emo)
        if anc is not None:
            return str(getattr(anc, "tension_arc", "rise") or "rise").strip().lower()
    except Exception:
        pass
    return "rise"


def apply_tension_arc_to_arrangement_curve(
    curve: Dict[str, Any],
    *,
    role: str,
    emotion_name: str,
    blend: float = 0.72,
) -> None:
    """Blend ``section_dynamic`` toward anchor tension-arc role targets."""
    arc = tension_arc_for_emotion(emotion_name)
    targets = _TENSION_ARC_SECTION_DYNAMIC.get(arc) or _TENSION_ARC_SECTION_DYNAMIC["rise"]
    role_lc = _normalize_role(role)
    target = float(targets.get(role_lc, 1.0))
    s = max(0.0, min(1.0, float(blend)))
    for key in ("section_dynamic", "melody_vel_scale"):
        try:
            current = float(curve.get(key, 1.0) or 1.0)
        except Exception:
            current = 1.0
        curve[key] = float(current * (1.0 - s) + target * s)
    curve["tension_arc_applied"] = str(arc)


def tension_arc_role_velocity_table(tension_arc: str) -> Dict[str, float]:
    arc = str(tension_arc or "rise").strip().lower()
    return dict(_TENSION_ARC_ROLE_VELOCITY.get(arc) or _TENSION_ARC_ROLE_VELOCITY["rise"])


def apply_tension_arc_to_professionalizer_velocities(
    base_role_vel: Dict[str, float],
    *,
    emotion_name: str,
    blend: float = 0.80,
) -> Dict[str, float]:
    arc = tension_arc_for_emotion(emotion_name)
    targets = tension_arc_role_velocity_table(arc)
    s = max(0.0, min(1.0, float(blend)))
    out: Dict[str, float] = {}
    for role, base in dict(base_role_vel or {}).items():
        role_lc = _normalize_role(str(role))
        target = float(targets.get(role_lc, float(base)))
        out[str(role)] = float(float(base) * (1.0 - s) + target * s)
    return out
