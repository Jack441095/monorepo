# composition/section_planner/planner.py
# ---------------------------------------------------------------------------
# Per-section plan (melody, bass, chords, …).
# ---------------------------------------------------------------------------
from audiogen_core.config import resolve_config
import random
import logging
import time
import math
from typing import Any, Dict, List, Optional, Tuple, cast

from audiogen_core.composition_runtime_flags import (
    markov_style_strength,
    phrase_length_bars_clamped,
    tension_trajectory_params,
)
from audiogen_core.mixer_config import CHANNEL_NAMES
from midi.midi_range_limiter import RANGE_LIMITER

from ..event import Event
from ..harmonic_plan import HarmonicPlan
from ..section_plan import SectionPlan
from .build_context import comp_proxy_for_voicing, snapshot_section_build_from_config
from .counter_melody_stage import (
    apply_counter_presence_multiplier,
    run_counter_melody_stage,
    thin_counter_against_lead,
)
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
from .observability import log_degraded
from .scale_setup import apply_derived_global_scale
from .section_sampling import run_best_of_k_section_build
from .timeline import _make_texture_by_bar, _make_timeline_targets, _timeline_shape

from .lead_texture_guards import (
    _arp_bed_suppressed_for_section,
    _perceptual_scale_emotion,
    _stabilize_low_flow_lead_harmony,
    _supportive_arp_follow_lead,
)
from .chorus_hook_blueprint import (
    _apply_bright_chorus_payoff_to_melody,
    _apply_chorus_hook_blueprint_to_arp_plan,
    _apply_chorus_hook_blueprint_to_melody,
    _chorus_hook_family_for_emotion,
    _masking_focus_strength_for_emotion,
    _normalized_hook_steps,
    _select_seeded_chorus_hook_blueprint,
    chorus_hook_emotion_key_from_plan,
)
from .melody_event_guards import (
    _break_repeated_lead_notes_events,
    _cap_large_leaps_events,
    _repair_phrase_end_chord_tone_events,
    _smooth_target_emotion_leaps_events,
)
from .section_event_qa import (
    _CHANNEL_VEL_KEYS,
    _apply_arrangement_velocity,
    _apply_arrangement_velocity_typed,
    _apply_arrangement_collision_manager_typed,
    _apply_hook_strength_qa_typed,
    _apply_melody_action_qa_typed,
    _apply_phrase_vocal_grammar_typed,
    _apply_post_generation_qa_typed,
    _apply_section_contrast_qa_typed,
    _apply_section_transition_gestures_typed,
    _apply_slow_emotion_melody_interest_typed,
    _apply_stability_contract_typed,
    _apply_velocity_curves_typed,
)

logger = logging.getLogger(__name__)

from .chorus_hook_memory import (
    apply_chorus_hook_memory,
    capture_chorus_hook_memory,
    apply_chorus_hook_memory as _apply_chorus_hook_memory,
    capture_chorus_hook_memory as _capture_chorus_hook_memory,
)
from .section_event_build import (
    melody_onset_steps_by_bar_for_section,
    prepare_section_events as _prepare_section_events_impl,
)
from .section_finalize import finalize_section_events as _finalize_section_events_impl

from .planner_hook_memory_mixin import _PlannerHookMemoryMixin
from .planner_arrangement_dynamics_mixin import _PlannerArrangementDynamicsMixin
from .planner_build_mixin import _PlannerBuildMixin
from .planner_harmony_voicing_mixin import _PlannerHarmonyVoicingMixin

class SectionPlanner(
    _PlannerHookMemoryMixin,
    _PlannerArrangementDynamicsMixin,
    _PlannerBuildMixin,
    _PlannerHarmonyVoicingMixin,
):
    """Owns the high-level SectionPlan pipeline for CompositionGenerator."""

    def __init__(self, owner):
        self.owner = owner

    def prepare_section_events(
        self,
        plan: SectionPlan,
        temperature: float,
        target_notes_per_bar: float,
        melody_style: str,
        melody_styles: Optional[List[Tuple[int, str]]],
        section_index: int = 0,
    ) -> SectionPlan:
        return _prepare_section_events_impl(
            self,
            plan,
            temperature,
            target_notes_per_bar,
            melody_style,
            melody_styles,
            section_index=section_index,
        )

    def _melody_onset_steps_by_bar_for_section(self, plan: SectionPlan, *, section_role: Optional[str] = None) -> Optional[List[List[int]]]:
        return melody_onset_steps_by_bar_for_section(self, plan, section_role=section_role)

    _apply_arrangement_velocity = staticmethod(_apply_arrangement_velocity)
    _apply_arrangement_velocity_typed = staticmethod(_apply_arrangement_velocity_typed)
    _apply_section_transition_gestures_typed = staticmethod(_apply_section_transition_gestures_typed)
    _apply_phrase_vocal_grammar_typed = staticmethod(_apply_phrase_vocal_grammar_typed)
    _apply_post_generation_qa_typed = staticmethod(_apply_post_generation_qa_typed)
    _apply_slow_emotion_melody_interest_typed = staticmethod(_apply_slow_emotion_melody_interest_typed)
    _apply_melody_action_qa_typed = staticmethod(_apply_melody_action_qa_typed)
    _apply_hook_strength_qa_typed = staticmethod(_apply_hook_strength_qa_typed)
    _apply_arrangement_collision_manager_typed = staticmethod(_apply_arrangement_collision_manager_typed)
    _apply_section_contrast_qa_typed = staticmethod(_apply_section_contrast_qa_typed)
    _apply_stability_contract_typed = staticmethod(_apply_stability_contract_typed)
    _apply_velocity_curves_typed = staticmethod(_apply_velocity_curves_typed)

    def finalize_section_events(self, plan: SectionPlan, humanization_scale: float) -> SectionPlan:
        return _finalize_section_events_impl(self, plan, humanization_scale)
