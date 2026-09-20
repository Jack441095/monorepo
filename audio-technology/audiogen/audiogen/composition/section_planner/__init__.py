# composition/section_planner/__init__.py
from .counter_melody_stage import (
    CounterMelodyStageResult,
    apply_counter_presence_multiplier,
    run_counter_melody_stage,
    thin_counter_against_lead,
)
from .section_dynamics_stage import (
    SectionDynamicsResult,
    apply_default_form_contrast_polish,
    apply_default_form_late_dynamics,
    apply_final_tension_arc_dynamics,
)
from .planner import SectionPlanner
from .timeline import _apply_transition_composer_targets, _make_texture_by_bar, _make_timeline_targets, _timeline_shape

__all__ = [
    "SectionPlanner",
    "CounterMelodyStageResult",
    "run_counter_melody_stage",
    "thin_counter_against_lead",
    "apply_counter_presence_multiplier",
    "SectionDynamicsResult",
    "apply_default_form_contrast_polish",
    "apply_default_form_late_dynamics",
    "apply_final_tension_arc_dynamics",
    "_make_texture_by_bar",
    "_make_timeline_targets",
    "_timeline_shape",
    "_apply_transition_composer_targets",
]
