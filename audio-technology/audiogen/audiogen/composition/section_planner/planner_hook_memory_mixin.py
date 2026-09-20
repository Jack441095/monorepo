# composition/section_planner/planner_hook_memory_mixin.py
# ---------------------------------------------------------------------------
# SectionPlanner mixin: chorus-reference overrides, final-chorus-payoff state
# plumbing, cross-lane motif bus / chorus-hook-memory glue, and counter-melody
# thinning. Split out of planner.py (see planner.py for the assembled class).
# ---------------------------------------------------------------------------
from typing import Any, Dict, List, Optional, Tuple

from ..section_plan import SectionPlan
from .chorus_reference import (
    chorus_reference_arp_overrides,
    chorus_reference_melody_overrides,
)
from .final_chorus_payoff import (
    apply_final_chorus_payoff_curve,
    apply_final_chorus_payoff_targets,
    resolve_final_chorus_payoff_state,
)
from .motif_bus import (
    cross_lane_motif_bus_from_melody,
    motif_hook_from_cross_lane_bus,
)
from .chorus_hook_blueprint import chorus_hook_emotion_key_from_plan
from .chorus_hook_memory import (
    apply_chorus_hook_memory,
    capture_chorus_hook_memory,
)
from .counter_melody_stage import (
    apply_counter_presence_multiplier,
    thin_counter_against_lead,
)


class _PlannerHookMemoryMixin:
    """Chorus-reference/payoff/motif-bus/hook-memory static helpers."""

    @staticmethod
    def _chorus_reference_arp_overrides(
        *,
        emotion_name: str,
        section_role: str,
    ) -> Dict[str, float]:
        return chorus_reference_arp_overrides(emotion_name=emotion_name, section_role=section_role)

    @staticmethod
    def _chorus_reference_melody_overrides(
        *,
        emotion_name: str,
        section_role: str,
    ) -> Dict[str, float]:
        return chorus_reference_melody_overrides(emotion_name=emotion_name, section_role=section_role)

    @staticmethod
    def _resolve_final_chorus_payoff_state(
        owner: Any,
        *,
        role: str,
        section_index: int,
        form_section_count: int,
    ) -> Dict[str, Any]:
        return resolve_final_chorus_payoff_state(
            owner,
            role=role,
            section_index=section_index,
            form_section_count=form_section_count,
        )

    @staticmethod
    def _cross_lane_motif_bus_from_melody(
        melody_events: List[Tuple],
        *,
        bars: int,
        beats_per_bar: float,
        section_role: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return cross_lane_motif_bus_from_melody(
            melody_events,
            bars=bars,
            beats_per_bar=beats_per_bar,
            section_role=section_role,
        )

    @staticmethod
    def _motif_hook_from_cross_lane_bus(bus: Optional[Dict[str, Any]]):
        return motif_hook_from_cross_lane_bus(bus)

    @staticmethod
    def _apply_final_chorus_payoff_targets(
        targets: Dict[str, List[float]],
        *,
        payoff_state: Dict[str, Any],
        strength: float,
    ) -> Dict[str, List[float]]:
        return apply_final_chorus_payoff_targets(
            targets, payoff_state=payoff_state, strength=strength
        )

    @staticmethod
    def _apply_final_chorus_payoff_curve(
        curve: Dict[str, Any],
        *,
        payoff_state: Dict[str, Any],
        strength: float,
    ) -> Dict[str, Any]:
        return apply_final_chorus_payoff_curve(
            curve, payoff_state=payoff_state, strength=strength
        )

    @staticmethod
    def _chorus_hook_emotion_key_from_plan(plan: SectionPlan) -> str:
        return chorus_hook_emotion_key_from_plan(plan)

    @staticmethod
    def _capture_chorus_hook_memory(owner: Any, plan: SectionPlan, *, section_role: str, section_index: int) -> None:
        capture_chorus_hook_memory(owner, plan, section_role=section_role, section_index=section_index)

    @staticmethod
    def _apply_chorus_hook_memory(owner: Any, plan: SectionPlan, *, section_role: str, section_index: int) -> None:
        apply_chorus_hook_memory(owner, plan, section_role=section_role, section_index=section_index)

    @staticmethod
    def _thin_counter_against_lead(plan: SectionPlan, *, strength: float) -> None:
        thin_counter_against_lead(plan, strength=strength)

    @staticmethod
    def _apply_counter_presence_multiplier(
        plan: SectionPlan,
        *,
        role: str,
        multiplier: float,
    ) -> None:
        apply_counter_presence_multiplier(plan, role=role, multiplier=multiplier)

