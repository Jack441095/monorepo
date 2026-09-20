"""Late arrangement-curve dynamics: default-form role contrast + tension-arc shaping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from data.emotion_aliases import canonical_emotion_name
from data.tension_arc_dynamics import (
    apply_tension_arc_to_arrangement_curve,
    apply_tension_arc_to_professionalizer_velocities,
    tension_arc_for_emotion,
    tension_arc_role_velocity_table,
)

# Audit targets: sparse-counter emotions want ~0.02–0.10 events/bar; rich-counter ~0.10–0.24.
SPARSE_COUNTER_EMOTIONS = frozenset(
    {
        "anger",
        "fear",
        "disgust",
        "disapproval",
        "love",
        "nervousness",
        "relief",
        "desire",
        "confusion",
        "embarrassment",
    }
)
RICH_COUNTER_EMOTIONS = frozenset(
    {"grief", "sadness", "remorse", "caring", "approval", "joy", "amusement"}
)
# Sparse dynamics but still need a minimal postprocess counter bed for hook identity.
LIGHT_COUNTERLINE_FLOOR_EMOTIONS = frozenset(
    {"embarrassment", "nervousness", "confusion"}
)
HEAVY_DESCENT_EMOTIONS = frozenset({"grief", "sadness", "remorse"})


@dataclass(frozen=True)
class SectionDynamicsResult:
    tension_arc: str
    section_dynamic: float
    melody_vel_scale: float
    contrast_polish_applied: bool = False


def resolve_dynamics_emotion_name(
    *,
    section_emotion_name: str,
    song_primary_emotion_name: str = "",
) -> str:
    primary = canonical_emotion_name(str(song_primary_emotion_name or ""))
    if primary:
        return primary
    return canonical_emotion_name(str(section_emotion_name or "")) or "neutral"


def apply_default_form_contrast_polish(
    curve: Dict[str, Any],
    *,
    emotion_name: str,
    role: str,
    role_occurrence: int = 0,
    section_progress: float = 0.0,
    strength: float = 0.62,
) -> None:
    """Late curve polish for the simplified default form (intro / verse / chorus / outro)."""
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return

    role_lc = str(role or "").strip().lower()
    emo = canonical_emotion_name(str(emotion_name or ""))
    occ = max(1, int(role_occurrence or 1))
    quiet = emo in {"grief", "sadness", "remorse", "relief", "disappointment", "embarrassment"}

    def _f(key: str, default: float = 1.0) -> float:
        try:
            return float(curve.get(key, default) or default)
        except Exception:
            return float(default)

    def _mul(key: str, mult: float, *, lo: float | None = None, hi: float | None = None) -> None:
        val = _f(key) * (1.0 + (float(mult) - 1.0) * s)
        if lo is not None:
            val = max(float(lo), val)
        if hi is not None:
            val = min(float(hi), val)
        curve[key] = float(val)

    def _toward(key: str, target: float, *, lo: float | None = None, hi: float | None = None) -> None:
        val = _f(key) + (float(target) - _f(key)) * s
        if lo is not None:
            val = max(float(lo), val)
        if hi is not None:
            val = min(float(hi), val)
        curve[key] = float(val)

    role_contrast = {
        "intro": 0.76,
        "a": 0.86 if occ <= 1 else 0.92,
        "verse": 0.86 if occ <= 1 else 0.92,
        "pre_chorus": 1.05,
        "b": 1.12 if occ <= 1 else 1.20,
        "chorus": 1.12 if occ <= 1 else 1.20,
        "hook": 1.12 if occ <= 1 else 1.20,
        "tag": 1.10,
        "outro": 0.70,
        "ending": 0.70,
    }.get(role_lc, 1.0)
    curve["section_contrast_strength"] = float(max(_f("section_contrast_strength", 1.0), role_contrast))

    if role_lc == "intro":
        _mul("section_dynamic", 0.94, hi=0.96)
        _mul("melody_total_notes_mult", 0.94, lo=0.92)
        _mul("chord_motion_mult", 0.92, hi=1.06)
        _mul("chord_rhythm_mult", 0.94, hi=1.02)
        if _f("arp_enabled", 0.0) >= 0.5:
            _mul("arp_density_mult", 0.76, hi=0.62)
            _toward("arp_target_notes_per_bar", 3.4, hi=4.2)
        curve["counter_melody_enabled_mult"] = 0.0
    elif role_lc in {"a", "verse"}:
        if occ <= 1:
            _mul("chord_motion_mult", 0.96, hi=1.04)
            _mul("chord_rhythm_mult", 0.97, hi=1.04)
            _mul("arp_density_mult", 0.88, hi=1.18)
            curve["counter_melody_enabled_mult"] = float(min(_f("counter_melody_enabled_mult", 0.0), 0.02))
        else:
            _mul("melody_total_notes_mult", 1.04, hi=1.06)
            _mul("melody_density_mult", 1.03, hi=1.18 if not quiet else 1.10)
            _mul("chord_motion_mult", 1.04, hi=1.16)
            _mul("arp_density_mult", 1.05, hi=1.42 if not quiet else 0.44)
            cm_cap = 0.10 if emo in SPARSE_COUNTER_EMOTIONS else 0.24
            curve["counter_melody_enabled_mult"] = float(
                min(cm_cap, _f("counter_melody_enabled_mult", 0.0) + 0.06 * s)
            )
        _mul("section_dynamic", 1.01 + 0.025 * min(1.0, occ - 1), hi=1.10)
    elif role_lc == "pre_chorus":
        _mul("section_dynamic", 1.045, lo=1.05, hi=1.14)
        _mul("chord_motion_mult", 1.08, lo=1.08, hi=1.22)
        _mul("chord_rhythm_mult", 1.04, lo=1.02, hi=1.15)
        _mul("arp_density_mult", 1.06, lo=0.80 if quiet else 1.00, hi=1.50)
        _mul("harmonic_color_mult", 1.04, hi=1.24)
        _mul("melody_total_notes_mult", 0.96, hi=0.98)
        pre_cap = 0.04 if emo in SPARSE_COUNTER_EMOTIONS else 0.08
        curve["counter_melody_enabled_mult"] = float(min(_f("counter_melody_enabled_mult", 0.0), pre_cap))
    elif role_lc in {"b", "chorus", "hook", "tag"}:
        _mul("section_dynamic", 1.04 + 0.025 * min(2.0, occ - 1), lo=1.06, hi=1.16 if not quiet else 1.08)
        _mul("motif_prob_mult", 1.05 + 0.03 * min(2.0, occ - 1), lo=1.42)
        _mul("phrase_repeat_mult", 1.08 + 0.05 * min(2.0, occ - 1), lo=0.82)
        _mul("melody_total_notes_mult", 0.94, hi=0.82 if not quiet else 0.88)
        _mul("chord_motion_mult", 0.98 if occ <= 1 else 1.03, hi=1.12)
        if _f("arp_enabled", 0.0) >= 0.5:
            _mul("arp_density_mult", 1.04 if occ <= 1 else 1.08, hi=1.28 if not quiet else 0.70)
            floor = 5.2 if quiet else 7.0
            curve["arp_target_notes_per_bar"] = float(max(floor, _f("arp_target_notes_per_bar", floor)))
        if emo in SPARSE_COUNTER_EMOTIONS:
            cm_cap = 0.08 if occ <= 1 else 0.05
            curve["counter_melody_enabled_mult"] = float(
                min(cm_cap, _f("counter_melody_enabled_mult", 0.0))
            )
        elif emo in RICH_COUNTER_EMOTIONS:
            cm_floor = 0.26 if occ <= 1 else 0.30
            curve["counter_melody_enabled_mult"] = float(
                max(cm_floor, _f("counter_melody_enabled_mult", 0.0))
            )
        else:
            curve["counter_melody_enabled_mult"] = float(
                max(_f("counter_melody_enabled_mult", 0.0), 0.20 if occ <= 1 else 0.26)
            )
        if occ > 1:
            curve["melody_lane_center_offset"] = int(round(_f("melody_lane_center_offset", 0.0) + 1.0 * s))
            if emo in SPARSE_COUNTER_EMOTIONS:
                curve["counter_melody_enabled_mult"] = float(
                    min(0.10, _f("counter_melody_enabled_mult", 0.0) + 0.04 * s)
                )
            elif emo in RICH_COUNTER_EMOTIONS:
                curve["counter_melody_enabled_mult"] = float(
                    min(0.42, _f("counter_melody_enabled_mult", 0.0) + 0.10 * s)
                )
            else:
                curve["counter_melody_enabled_mult"] = float(
                    min(0.40, _f("counter_melody_enabled_mult", 0.0) + 0.10 * s)
                )
        if emo in {"love", "caring"}:
            curve["phrase_repeat_mult"] = float(min(_f("phrase_repeat_mult", 1.0), 0.98 if occ <= 1 else 1.10))
            curve["melody_contour_variation_mult"] = float(max(_f("melody_contour_variation_mult", 1.0), 0.98))
            curve["chorus_interaction_mode"] = "coexist"
    elif role_lc in {"outro", "ending"}:
        _mul("section_dynamic", 0.86, hi=0.88)
        _mul("melody_density_mult", 0.86, hi=0.84)
        _mul("melody_total_notes_mult", 0.82, hi=0.62)
        _mul("chord_motion_mult", 0.82, hi=0.90)
        _mul("chord_rhythm_mult", 0.86, hi=0.92)
        curve["arp_enabled"] = 0.0
        curve["arp_density_mult"] = 0.0
        curve["arp_target_notes_per_bar"] = 0.0
        curve["arp_velocity_scale"] = 0.0
        curve["counter_melody_enabled_mult"] = 0.0

    curve["arrangement_contrast_polish"] = float(s)
    curve["arrangement_section_progress"] = float(max(0.0, min(1.0, float(section_progress))))


def apply_final_tension_arc_dynamics(
    curve: Dict[str, Any],
    *,
    role: str,
    section_emotion_name: str,
    song_primary_emotion_name: str = "",
    blend: float = 0.72,
) -> SectionDynamicsResult:
    """Apply anchor ``tension_arc`` targets to ``section_dynamic`` and ``melody_vel_scale``."""
    emo = resolve_dynamics_emotion_name(
        section_emotion_name=str(section_emotion_name or ""),
        song_primary_emotion_name=str(song_primary_emotion_name or ""),
    )
    apply_tension_arc_to_arrangement_curve(
        curve,
        role=str(role),
        emotion_name=str(emo),
        blend=float(blend),
    )
    arc = str(curve.get("tension_arc_applied", "") or tension_arc_for_emotion(emo))
    try:
        sd = float(curve.get("section_dynamic", 1.0) or 1.0)
    except Exception:
        sd = 1.0
    try:
        mv = float(curve.get("melody_vel_scale", 1.0) or 1.0)
    except Exception:
        mv = 1.0
    return SectionDynamicsResult(
        tension_arc=str(arc),
        section_dynamic=float(sd),
        melody_vel_scale=float(mv),
    )


def apply_default_form_late_dynamics(
    curve: Dict[str, Any],
    *,
    form_mode: str,
    section_emotion_name: str,
    song_primary_emotion_name: str,
    role: str,
    role_occurrence: int,
    section_progress: float,
    contrast_enabled: bool = True,
    contrast_strength: float = 0.62,
    tension_blend: float = 0.72,
) -> SectionDynamicsResult:
    """Default-form late passes: role contrast polish, then tension arc (call after emotion identity)."""
    contrast_applied = False
    if str(form_mode or "").strip().lower() == "default" and contrast_enabled:
        apply_default_form_contrast_polish(
            curve,
            emotion_name=str(section_emotion_name or ""),
            role=str(role),
            role_occurrence=int(role_occurrence),
            section_progress=float(section_progress),
            strength=float(contrast_strength),
        )
        contrast_applied = True
    result = apply_final_tension_arc_dynamics(
        curve,
        role=str(role),
        section_emotion_name=str(section_emotion_name or ""),
        song_primary_emotion_name=str(song_primary_emotion_name or ""),
        blend=float(tension_blend),
    )
    return SectionDynamicsResult(
        tension_arc=result.tension_arc,
        section_dynamic=result.section_dynamic,
        melody_vel_scale=result.melody_vel_scale,
        contrast_polish_applied=contrast_applied,
    )


__all__ = [
    "SectionDynamicsResult",
    "apply_default_form_contrast_polish",
    "apply_default_form_late_dynamics",
    "apply_final_tension_arc_dynamics",
    "apply_tension_arc_to_professionalizer_velocities",
    "resolve_dynamics_emotion_name",
    "tension_arc_for_emotion",
    "tension_arc_role_velocity_table",
]
