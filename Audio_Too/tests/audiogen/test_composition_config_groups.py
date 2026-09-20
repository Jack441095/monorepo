# tests/test_composition_config_groups.py
from __future__ import annotations

from audiogen_core.composition_config import CompositionConfiguration
from audiogen_core.composition_config_groups import (
    CompositionRuntimeProfile,
    HarmonyTensionControlGroup,
    MelodyPhrasePlanningGroup,
    MelodyRoleDensityGroup,
    RealtimeFormGroup,
    build_composition_runtime_profile,
    melody_role_density_group,
    realtime_form_group,
)


def test_melody_role_density_group_matches_flat_comp_fields() -> None:
    comp = CompositionConfiguration()
    g = comp.melody_role_density
    assert isinstance(g, MelodyRoleDensityGroup)
    assert g.mult_intro == comp.melody_role_density_intro_mult
    assert g.target_chorus_npb_min == comp.melody_role_chorus_target_npb_min
    assert g is not melody_role_density_group(comp)  # new frozen instance each time


def test_melody_role_density_group_duck_typed() -> None:
    class _Mini:
        melody_role_density_intro_mult = 0.5
        melody_role_density_verse_mult = 1.0
        melody_role_density_prechorus_mult = 1.0
        melody_role_density_chorus_mult = 1.0
        melody_role_density_tag_mult = 1.0
        melody_role_density_aprime_mult = 1.0
        melody_role_density_outro_mult = 0.5
        melody_role_intro_target_npb_max = 4.0
        melody_role_intro_target_npb_min = 2.0
        melody_role_verse_target_npb_min = 3.0
        melody_role_prechorus_target_npb_min = 4.0
        melody_role_outro_target_npb_max = 3.0
        melody_role_chorus_target_npb_min = 5.0

    g = melody_role_density_group(_Mini())
    assert g.mult_intro == 0.5
    assert g.target_intro_npb_min == 2.0


def test_harmony_tension_group_matches_flat_comp_fields() -> None:
    comp = CompositionConfiguration()
    g = comp.harmony_tension
    assert isinstance(g, HarmonyTensionControlGroup)
    assert g.strength == comp.harmony_tension_control_strength
    assert g.color_cap_low == comp.harmony_color_cap_low_tension
    assert g.color_cap_high == comp.harmony_color_cap_high_tension
    assert g.harmonic_rhythm_sensitivity == comp.harmonic_rhythm_tension_sensitivity


def test_melody_phrase_planning_group_matches_flat_comp_fields() -> None:
    comp = CompositionConfiguration()
    g = comp.melody_phrase_planning
    assert isinstance(g, MelodyPhrasePlanningGroup)
    assert g.phrase_k_samples == comp.melody_phrase_k_samples
    assert g.beam_width == comp.melody_phrase_beam_width
    assert g.listener_memory_strength == comp.melody_listener_memory_scorer_strength
    assert g.repair_stack_enabled == comp.melody_phrase_repair_stack_enabled


def test_realtime_form_group_matches_flat_comp_fields() -> None:
    comp = CompositionConfiguration()
    g = comp.realtime_form
    assert isinstance(g, RealtimeFormGroup)
    assert g.loop_enabled == comp.realtime_form_loop_enabled
    assert g.planner_effort == comp.realtime_planner_effort
    assert g.energy_arc_length == comp.realtime_energy_arc_length


def test_realtime_form_group_factory_duck_typed() -> None:
    class _Rt:
        realtime_form_loop_enabled = False
        realtime_form_mode_override = "pop"
        realtime_form_loop_drop_outro = False
        realtime_planner_effort = "minimal"
        realtime_energy_arc_length = 12

    g = realtime_form_group(_Rt())
    assert g.loop_enabled is False
    assert g.mode_override == "pop"
    assert g.planner_effort == "minimal"
    assert g.energy_arc_length == 12


def test_build_composition_runtime_profile_matches_wiring() -> None:
    comp = CompositionConfiguration()
    built = build_composition_runtime_profile(comp)
    assert isinstance(built, CompositionRuntimeProfile)
    assert built.melody_role_density.mult_intro == comp.melody_role_density_intro_mult
    assert built.melody_phrase_planning.melody_k_samples == comp.melody_k_samples
    assert built.harmony_tension.strength == comp.harmony_tension_control_strength
    assert built.realtime_form.energy_arc_length == comp.realtime_energy_arc_length


def test_runtime_profile_cache_shared_across_group_properties() -> None:
    comp = CompositionConfiguration()
    a = comp.melody_role_density
    b = comp.melody_role_density
    assert a is b
    p1 = comp.runtime_profile
    p2 = comp.runtime_profile
    assert p1 is p2
    # Independent factory call is still a distinct object
    assert a is not melody_role_density_group(comp)


def test_runtime_profile_cache_clears_on_mutation() -> None:
    comp = CompositionConfiguration()
    before = comp.melody_role_density
    comp.melody_role_density_intro_mult = 0.11
    after = comp.melody_role_density
    assert after is not before
    assert after.mult_intro == 0.11
