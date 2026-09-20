"""
Shared section plan consumed by harmony, melody, and texture lanes (Phase C).

When ``joint_generation_enabled`` is on, ``joint_plan_stage`` builds a
``JointSectionPlan`` before harmony and melody sampling so all lanes share
progression + hook skeleton targets.
"""

from __future__ import annotations
from audiogen_core.config import resolve_config

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

_CHORUS_ROLES = frozenset({"b", "chorus", "hook", "tag"})
_VERSE_ROLES = frozenset({"a", "verse", "a_prime", "intro"})
_PRE_ROLES = frozenset({"pre_chorus"})


@dataclass
class JointSectionPlan:
    """Single-section intent shared across generation lanes."""

    emotion: str
    role: str
    root_midi: int
    bars: int
    beats_per_bar: float = 4.0
    chord_symbols: List[str] = field(default_factory=list)
    hook_degrees: List[int] = field(default_factory=list)
    target_lead_notes_per_bar: float = 2.5
    target_counter_mult: float = 0.0
    target_arp_notes_per_bar: float = 0.0
    contour_bias: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "emotion": str(self.emotion),
            "role": str(self.role),
            "root_midi": int(self.root_midi),
            "bars": int(self.bars),
            "beats_per_bar": float(self.beats_per_bar),
            "chord_symbols": list(self.chord_symbols),
            "hook_degrees": list(self.hook_degrees),
            "target_lead_notes_per_bar": float(self.target_lead_notes_per_bar),
            "target_counter_mult": float(self.target_counter_mult),
            "target_arp_notes_per_bar": float(self.target_arp_notes_per_bar),
            "contour_bias": int(self.contour_bias),
            "metadata": dict(self.metadata),
        }


def _cycle_symbols(pool: Sequence[str], bars: int) -> List[str]:
    syms = [str(x) for x in list(pool or []) if str(x).strip()]
    if not syms:
        syms = ["I", "vi", "IV", "V"]
    out: List[str] = []
    for i in range(max(1, int(bars))):
        out.append(str(syms[i % len(syms)]))
    return out


def _scale_for_emotion(emotion: str) -> List[int]:
    try:
        from data.emotion_scales import melody_scale_intervals_for_emotion
        from data.music_data import EMOTION_BY_NAME

        emo_obj = EMOTION_BY_NAME.get(str(emotion or "neutral").strip().lower(), emotion)
        scale = list(melody_scale_intervals_for_emotion(emo_obj) or [0, 2, 4, 5, 7, 9, 11])
    except Exception:
        scale = [0, 2, 4, 5, 7, 9, 11]
    return scale if len(scale) >= 3 else [0, 2, 4, 5, 7, 9, 11]


def _counter_mult_for_emotion(emo: str) -> float:
    if emo in {"anger", "fear", "disgust", "disapproval", "love", "nervousness", "relief", "desire", "confusion", "embarrassment"}:
        return 0.06
    if emo in {"grief", "sadness", "remorse", "caring", "approval", "joy", "amusement"}:
        return 0.24
    return 0.12


def _contour_for_emotion(emo: str, role: str) -> int:
    role_lc = str(role or "").strip().lower()
    if emo in {"grief", "remorse", "sadness"}:
        return -2 if role_lc in _CHORUS_ROLES else -1
    if emo in {"joy", "amusement", "excitement", "approval", "optimism", "pride"}:
        return 2 if role_lc in _CHORUS_ROLES else 1
    return 0


def build_joint_plan_for_role(
    *,
    emotion: str,
    role: str,
    root_midi: int,
    bars: int,
    chord_progression: Optional[Sequence[str]] = None,
    beats_per_bar: float = 4.0,
) -> Optional[JointSectionPlan]:
    """Build a role-appropriate joint plan (chorus gets hook skeleton; verse locks harmony)."""
    emo = str(emotion or "neutral").strip().lower()
    role_lc = str(role or "").strip().lower()
    b = int(max(1, bars))

    if role_lc in _CHORUS_ROLES:
        return build_chorus_joint_plan(
            emotion=emo,
            root_midi=int(root_midi),
            bars=b,
            chord_progression=chord_progression,
            beats_per_bar=float(beats_per_bar),
        )

    if role_lc in _VERSE_ROLES | _PRE_ROLES:
        if role_lc in _PRE_ROLES:
            pool = ["I", "V", "vi", "IV"]
            arp_npb = 5.0
            lead_npb = 2.4
        else:
            pool = ["I", "vi", "IV", "V"]
            arp_npb = 4.0 if role_lc == "intro" else 3.2
            lead_npb = 2.2 if role_lc == "intro" else 2.6
        symbols = _cycle_symbols(list(chord_progression or pool), b)
        scale = _scale_for_emotion(emo)
        hook = [int(scale[0]), int(scale[min(2, len(scale) - 1)])] if role_lc in _PRE_ROLES else []
        return JointSectionPlan(
            emotion=emo,
            role=role_lc,
            root_midi=int(root_midi),
            bars=b,
            beats_per_bar=float(beats_per_bar),
            chord_symbols=symbols,
            hook_degrees=hook,
            target_lead_notes_per_bar=float(lead_npb),
            target_counter_mult=0.0 if role_lc == "intro" else min(0.10, _counter_mult_for_emotion(emo) * 0.5),
            target_arp_notes_per_bar=float(arp_npb),
            contour_bias=int(_contour_for_emotion(emo, role_lc)),
            metadata={"phase": "verse_mvp", "source": "joint_section_plan"},
        )
    return None


def build_chorus_joint_plan(
    *,
    emotion: str,
    root_midi: int,
    bars: int,
    chord_progression: Optional[Sequence[str]] = None,
    beats_per_bar: float = 4.0,
) -> JointSectionPlan:
    """Chorus plan: locked progression + 3–4 note hook skeleton in scale degrees."""
    emo = str(emotion or "neutral").strip().lower()
    symbols = _cycle_symbols(list(chord_progression or ["I", "vi", "IV", "V"]), int(bars))
    scale = _scale_for_emotion(emo)
    hook_degrees = [int(scale[i % len(scale)]) for i in (0, 2, 4, 2)]

    return JointSectionPlan(
        emotion=emo,
        role="chorus",
        root_midi=int(root_midi),
        bars=int(max(1, bars)),
        beats_per_bar=float(beats_per_bar),
        chord_symbols=symbols,
        hook_degrees=hook_degrees,
        target_lead_notes_per_bar=2.8,
        target_counter_mult=float(_counter_mult_for_emotion(emo)),
        target_arp_notes_per_bar=6.0,
        contour_bias=int(_contour_for_emotion(emo, "chorus")),
        metadata={"phase": "chorus_mvp", "source": "joint_section_plan"},
    )


def hook_blueprint_from_joint_plan(
    joint: JointSectionPlan,
    *,
    span_bars: int = 2,
) -> Optional[Dict[str, Any]]:
    """Convert scale-degree hook skeleton into chorus_hook_blueprint shape."""
    degrees = list(joint.hook_degrees or [])
    if len(degrees) < 2:
        return None
    span = max(1, min(int(joint.bars), int(span_bars)))
    bar0 = [int(degrees[i % len(degrees)]) for i in range(min(4, len(degrees)))]
    bar1 = [int(degrees[(i + 1) % len(degrees)]) for i in range(min(4, len(degrees)))]
    while len(bar0) < 2:
        bar0.append(int(bar0[-1]))
    while len(bar1) < 2:
        bar1.append(int(bar1[-1]))
    floor = 70
    try:
        floor = int(joint.root_midi) + 10
    except Exception:
        pass
    floor = max(60, min(84, int(floor)))
    return {
        "name": "joint_plan_hook",
        "span_bars": int(span),
        "melody_steps_by_bar": [bar0, bar1],
        "arp_steps_by_bar": [bar0 + [int(bar0[-1]) + 2], bar1 + [int(bar1[-1]) + 2]],
        "melody_register_floor": int(floor),
        "arp_density_mult_min": 1.0,
        "target_notes_per_bar_min": max(5.0, float(joint.target_arp_notes_per_bar) * 0.85),
        "chorus_interaction_mode": "coexist",
        "source": "joint_section_plan",
    }


def apply_joint_plan_to_arrangement_curve(
    curve: Dict[str, Any],
    plan: JointSectionPlan,
    *,
    strength: float = 0.85,
) -> None:
    """Nudge arrangement curve targets toward a shared ``JointSectionPlan``."""
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return

    def _toward(key: str, target: float, *, lo: float | None = None, hi: float | None = None) -> None:
        try:
            cur = float(curve.get(key, target) or target)
        except Exception:
            cur = float(target)
        val = cur + (float(target) - cur) * s
        if lo is not None:
            val = max(float(lo), val)
        if hi is not None:
            val = min(float(hi), val)
        curve[key] = float(val)

    _toward("melody_total_notes_mult", 0.95 + 0.08 * min(2.0, float(plan.target_lead_notes_per_bar) / 3.0), hi=1.12)
    _toward("melody_density_mult", 0.92 + 0.06 * min(2.0, float(plan.target_lead_notes_per_bar) / 3.0), hi=1.18)
    _toward("counter_melody_enabled_mult", float(plan.target_counter_mult), lo=0.0, hi=0.40)
    if int(plan.contour_bias) < 0:
        _toward("melody_contour_variation_mult", 0.92, lo=0.82, hi=1.05)
    if float(plan.target_arp_notes_per_bar) > 1e-6:
        curve["arp_enabled"] = 1.0
        _toward("arp_target_notes_per_bar", float(plan.target_arp_notes_per_bar), lo=2.5, hi=14.0)
    mode = str((plan.metadata or {}).get("chorus_interaction_mode", "") or "").strip().lower()
    if mode in {"coexist", "unison", "dialogue", "fill"}:
        curve["chorus_interaction_mode"] = str(mode)
    curve["joint_section_plan"] = plan.as_dict()


def hook_degrees_from_plan_dict(plan_dict: Optional[Dict[str, Any]]) -> List[int]:
    """Extract scale-degree hook cell from a serialized ``JointSectionPlan`` dict."""
    if not isinstance(plan_dict, dict):
        return []
    out: List[int] = []
    for raw in list(plan_dict.get("hook_degrees") or []):
        try:
            out.append(int(raw) % 7)
        except Exception:
            continue
    return out


def should_lock_harmony_to_joint_plan() -> bool:
    if not resolve_config("composition", "joint_generation_enabled", False, bool):
        return False
    return resolve_config("composition", "joint_plan_lock_harmony", True, bool)