"""Phase C: apply ``JointSectionPlan`` before harmony and melody generation."""

from __future__ import annotations
from audiogen_core.config import resolve_config

from typing import Any, Dict, List, Optional, Tuple

from composition.joint_section_plan import (
    apply_joint_plan_to_arrangement_curve,
    build_joint_plan_for_role,
    hook_blueprint_from_joint_plan,
    should_lock_harmony_to_joint_plan,
)


def _primary_emotion(owner: Any, section_emotion: Any) -> str:
    try:
        from data.emotion_aliases import canonical_emotion_name

        primary = str(getattr(owner, "song_primary_emotion_name", "") or "").strip().lower()
        if primary:
            return canonical_emotion_name(primary)
        return canonical_emotion_name(str(getattr(section_emotion, "name", "") or "neutral"))
    except Exception:
        return str(getattr(section_emotion, "name", "neutral") or "neutral").strip().lower()


def integrate_joint_plan_at_harmony(
    owner: Any,
    plan: Any,
    curve: Dict[str, Any],
    *,
    section_index: int,
    section_role: str,
    chord_progression: Optional[List[str]],
    role_occurrence: int = 1,
    section_progress: float = 0.0,
) -> Tuple[Dict[str, Any], Optional[List[str]], Dict[str, Any]]:
    """
    Build shared joint plan, polish curve, optionally override chord progression.

    Returns (curve, chord_progression_override, meta).
    """
    meta: Dict[str, Any] = {"enabled": False}
    if not resolve_config("composition", "joint_generation_enabled", False, bool):
        return dict(curve), chord_progression, meta
    emo = _primary_emotion(owner, getattr(plan, "emotion", None))
    role_lc = str(section_role or "").strip().lower()
    curve2 = dict(curve)
    curve2["section_root_midi"] = int(getattr(plan, "root_note", 60) or 60)
    curve2["section_bars"] = int(getattr(plan, "bars", 8) or 8)

    try:
        from composition.section_planner.section_dynamics_stage import apply_default_form_late_dynamics

        apply_default_form_late_dynamics(
            curve2,
            form_mode=str(getattr(owner.arrangement_policy, "form_mode", "default") or "default"),
            section_emotion_name=str(getattr(plan.emotion, "name", "") or ""),
            song_primary_emotion_name=str(getattr(owner, "song_primary_emotion_name", "") or ""),
            role=str(section_role or ""),
            role_occurrence=int(role_occurrence),
            section_progress=float(section_progress),
        )
    except Exception:
        pass

    joint = build_joint_plan_for_role(
        emotion=str(emo),
        role=str(role_lc),
        root_midi=int(getattr(plan, "root_note", 60) or 60),
        bars=int(getattr(plan, "bars", 8) or 8),
        chord_progression=chord_progression,
    )
    if joint is None:
        return curve2, chord_progression, meta

    strength = 0.88 if role_lc in {"b", "chorus", "hook", "tag"} else 0.72
    apply_joint_plan_to_arrangement_curve(curve2, joint, strength=float(strength))

    hook_bp = None
    if role_lc in {"b", "chorus", "hook", "tag"}:
        hook_bp = hook_blueprint_from_joint_plan(joint)

    prog_override = chord_progression
    if should_lock_harmony_to_joint_plan() and list(joint.chord_symbols or []):
        if not chord_progression:
            prog_override = list(joint.chord_symbols)

    meta = {
        "enabled": True,
        "plan": joint.as_dict(),
        "hook_blueprint": hook_bp,
        "harmony_locked": bool(prog_override is not chord_progression or (prog_override and not chord_progression)),
        "emotion": str(emo),
        "role": str(role_lc),
    }
    return curve2, prog_override, meta


def attach_joint_plan_to_section_plan(plan: Any, meta: Dict[str, Any]) -> None:
    if not bool(meta.get("enabled")):
        return
    try:
        plan.joint_section_plan = dict(meta.get("plan") or {})
    except Exception:
        pass
    hook = meta.get("hook_blueprint")
    if isinstance(hook, dict) and hook:
        try:
            plan.joint_hook_blueprint = dict(hook)
        except Exception:
            pass