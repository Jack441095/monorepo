# composition/section_planner/build_context.py
"""Single CONFIG.composition read per section build (hot-path snapshot)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from .observability import log_degraded


@dataclass(frozen=True)
class SectionBuildSnapshot:
    """Immutable view of composition settings used during one `build_section` call."""

    force_emotion_scale_quantization: bool
    derive_emotion_scale_from_chords: bool
    user_global_scale_intervals: Optional[List[int]]
    realtime_planner_effort: str
    section_k_samples: int
    section_pick_time_budget_s: float
    section_pick_use_wall_clock: bool
    joint_generation_enabled: bool
    joint_generation_max_iters: int
    joint_generation_budget_ms: float
    joint_generation_use_wall_clock: bool
    melody_lane_center_midi: int
    melody_lane_half_width: int
    chords_lane_offset_from_melody: int
    chords_lane_half_width: int
    melody_register_arc_enabled: bool
    transition_bridge_hold_bars: int


def snapshot_section_build_from_config() -> SectionBuildSnapshot:
    """Read `CONFIG.composition` once; safe defaults if import or attributes fail."""
    try:
        from audiogen_core.config import CONFIG

        c = CONFIG.composition
        raw_gs = getattr(c, "global_scale_intervals", None)
        user_gs = list(raw_gs) if raw_gs else None
        # New alias: allow `realtime_effort` while preserving existing `realtime_planner_effort`.
        try:
            eff = str(getattr(c, "realtime_effort", "") or "").strip().lower()
        except Exception:
            eff = ""
        if eff not in {"minimal", "balanced", "full"}:
            try:
                eff = str(c.realtime_form.planner_effort).strip().lower()
            except Exception:
                eff = str(getattr(c, "realtime_planner_effort", "full") or "full").strip().lower()
        return SectionBuildSnapshot(
            force_emotion_scale_quantization=bool(
                getattr(c, "force_emotion_scale_quantization", True)
            ),
            derive_emotion_scale_from_chords=bool(getattr(c, "derive_emotion_scale_from_chords", True)),
            user_global_scale_intervals=user_gs,
            realtime_planner_effort=str(eff or "full"),
            section_k_samples=int(getattr(c, "section_k_samples", 1) or 1),
            section_pick_time_budget_s=float(getattr(c, "section_pick_time_budget_s", 0.35) or 0.35),
            section_pick_use_wall_clock=bool(getattr(c, "section_pick_use_wall_clock", False)),
            joint_generation_enabled=bool(getattr(c, "joint_generation_enabled", False)),
            joint_generation_max_iters=int(getattr(c, "joint_generation_max_iters", 3) or 3),
            joint_generation_budget_ms=float(getattr(c, "joint_generation_budget_ms", 120.0) or 120.0),
            joint_generation_use_wall_clock=bool(getattr(c, "joint_generation_use_wall_clock", False)),
            melody_lane_center_midi=int(getattr(c, "melody_lane_center_midi", 72) or 72),
            melody_lane_half_width=int(getattr(c, "melody_lane_half_width", 10) or 10),
            chords_lane_offset_from_melody=int(getattr(c, "chords_lane_offset_from_melody", 12) or 12),
            chords_lane_half_width=int(getattr(c, "chords_lane_half_width", 10) or 10),
            melody_register_arc_enabled=bool(getattr(c, "melody_register_arc_enabled", True)),
            transition_bridge_hold_bars=int(getattr(c, "transition_bridge_hold_bars", 1) or 1),
        )
    except Exception as exc:
        log_degraded("snapshot_section_build_from_config", exc)
        return SectionBuildSnapshot(
            force_emotion_scale_quantization=True,
            derive_emotion_scale_from_chords=True,
            user_global_scale_intervals=None,
            realtime_planner_effort="full",
            section_k_samples=1,
            section_pick_time_budget_s=0.35,
            section_pick_use_wall_clock=False,
            joint_generation_enabled=False,
            joint_generation_max_iters=3,
            joint_generation_budget_ms=120.0,
            joint_generation_use_wall_clock=False,
            melody_lane_center_midi=72,
            melody_lane_half_width=10,
            chords_lane_offset_from_melody=12,
            chords_lane_half_width=10,
            melody_register_arc_enabled=True,
            transition_bridge_hold_bars=1,
        )


def comp_proxy_for_voicing(snapshot: SectionBuildSnapshot) -> Any:
    """Minimal object with attributes `_apply_timeline_targets_to_voicing` expects."""

    class _CompView:
        __slots__ = (
            "melody_lane_center_midi",
            "melody_lane_half_width",
            "chords_lane_offset_from_melody",
            "chords_lane_half_width",
            "melody_register_arc_enabled",
        )

        def __init__(self, s: SectionBuildSnapshot) -> None:
            self.melody_lane_center_midi = s.melody_lane_center_midi
            self.melody_lane_half_width = s.melody_lane_half_width
            self.chords_lane_offset_from_melody = s.chords_lane_offset_from_melody
            self.chords_lane_half_width = s.chords_lane_half_width
            self.melody_register_arc_enabled = s.melody_register_arc_enabled

    return _CompView(snapshot)
