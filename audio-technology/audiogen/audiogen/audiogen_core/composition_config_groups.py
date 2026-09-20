# core/composition_config_groups.py
"""
Logical bundles over `CompositionConfiguration` for readability and call-site clarity.

`CompositionConfiguration` stays a single flat dataclass (presets, pickle, and
`getattr` sites keep working). Grouping here is a *view* — no duplicate source of
defaults, no second assignment path.

Phase 1 runtime profile: ``CompositionRuntimeProfile`` bundles all four views so they can be
built once per steady-state config (see cached accessors on ``CompositionConfiguration``).
"""

from __future__ import annotations

from dataclasses import dataclass


def _f(obj: object, key: str, default: float) -> float:
    v = getattr(obj, key, default)
    if v is None:
        return float(default)
    return float(v)


def _i(obj: object, key: str, default: int) -> int:
    v = getattr(obj, key, default)
    if v is None:
        return int(default)
    return int(v)


def _b(obj: object, key: str, default: bool) -> bool:
    if not hasattr(obj, key):
        return bool(default)
    v = getattr(obj, key)
    if v is None:
        return bool(default)
    return bool(v)


def _s(obj: object, key: str, default: str) -> str:
    v = getattr(obj, key, default)
    if v is None:
        return str(default)
    return str(v)


@dataclass(frozen=True)
class MelodyRoleDensityGroup:
    """Section-role melody density + soft notes-per-bar guardrails (lead planning)."""

    mult_intro: float
    mult_verse: float
    mult_prechorus: float
    mult_chorus: float
    mult_tag: float
    mult_aprime: float
    mult_outro: float
    target_intro_npb_max: float
    target_intro_npb_min: float
    target_verse_npb_min: float
    target_prechorus_npb_min: float
    target_outro_npb_max: float
    target_chorus_npb_min: float


def melody_role_density_group(comp: object) -> MelodyRoleDensityGroup:
    """Build a read-only view from a `CompositionConfiguration` (or duck-typed test double)."""
    return MelodyRoleDensityGroup(
        mult_intro=_f(comp, "melody_role_density_intro_mult", 0.90),
        mult_verse=_f(comp, "melody_role_density_verse_mult", 0.98),
        mult_prechorus=_f(comp, "melody_role_density_prechorus_mult", 1.04),
        mult_chorus=_f(comp, "melody_role_density_chorus_mult", 1.10),
        mult_tag=_f(comp, "melody_role_density_tag_mult", 1.06),
        mult_aprime=_f(comp, "melody_role_density_aprime_mult", 1.02),
        mult_outro=_f(comp, "melody_role_density_outro_mult", 0.68),
        target_intro_npb_max=_f(comp, "melody_role_intro_target_npb_max", 4.2),
        target_intro_npb_min=_f(comp, "melody_role_intro_target_npb_min", 2.9),
        target_verse_npb_min=_f(comp, "melody_role_verse_target_npb_min", 3.8),
        target_prechorus_npb_min=_f(comp, "melody_role_prechorus_target_npb_min", 4.8),
        target_outro_npb_max=_f(comp, "melody_role_outro_target_npb_max", 3.8),
        target_chorus_npb_min=_f(comp, "melody_role_chorus_target_npb_min", 5.6),
    )


@dataclass(frozen=True)
class HarmonyTensionControlGroup:
    """Realtime harmony tension shaping + harmonic-rhythm sensitivity."""

    strength: float
    color_cap_low: float
    color_cap_high: float
    harmonic_rhythm_sensitivity: float


def harmony_tension_control_group(comp: object) -> HarmonyTensionControlGroup:
    """View over harmony tension / color caps / HR×tension coupling."""
    return HarmonyTensionControlGroup(
        strength=_f(comp, "harmony_tension_control_strength", 0.0),
        color_cap_low=_f(comp, "harmony_color_cap_low_tension", 1.0),
        color_cap_high=_f(comp, "harmony_color_cap_high_tension", 1.0),
        harmonic_rhythm_sensitivity=_f(comp, "harmonic_rhythm_tension_sensitivity", 0.4),
    )


@dataclass(frozen=True)
class MelodyPhrasePlanningGroup:
    """Phrase-level best-of-K, beam frontier, rerank weights, scorers, offline-quality boosts."""

    melody_k_samples: int
    phrase_k_samples: int
    beam_enabled: bool
    beam_width: int
    beam_keep: int
    beam_diversity_weight: float
    beam_lookahead_weight: float
    rerank_entry_leap_penalty: float
    rerank_large_leap_penalty: float
    rerank_large_leap_threshold: int
    rerank_cadence_land_bonus: float
    rerank_cadence_approach_bonus: float
    rerank_cadence_miss_penalty: float
    offline_quality_render_enabled: bool
    offline_quality_k_scale: float
    offline_quality_beam_width: int
    listener_memory_enabled: bool
    listener_memory_strength: float
    lyrical_scorer_enabled: bool
    lyrical_scorer_strength: float
    rerank_masking_weight: float
    rerank_strongbeat_chord_tone_bonus: float
    phrase_objective_enabled: bool
    phrase_objective_static_run_weight: float
    phrase_objective_contour_weight: float
    phrase_objective_long_breath_weight: float
    repair_stack_enabled: bool
    neural_phrase_generator_enabled: bool


def melody_phrase_planning_group(comp: object) -> MelodyPhrasePlanningGroup:
    return MelodyPhrasePlanningGroup(
        melody_k_samples=_i(comp, "melody_k_samples", 4),
        phrase_k_samples=_i(comp, "melody_phrase_k_samples", 3),
        beam_enabled=_b(comp, "melody_phrase_beam_enabled", True),
        beam_width=_i(comp, "melody_phrase_beam_width", 7),
        beam_keep=_i(comp, "melody_phrase_beam_keep", 3),
        beam_diversity_weight=_f(comp, "melody_phrase_beam_diversity_weight", 0.12),
        beam_lookahead_weight=_f(comp, "melody_phrase_beam_lookahead_weight", 0.18),
        rerank_entry_leap_penalty=_f(comp, "melody_phrase_rerank_entry_leap_penalty", 0.26),
        rerank_large_leap_penalty=_f(comp, "melody_phrase_rerank_large_leap_penalty", 0.06),
        rerank_large_leap_threshold=_i(comp, "melody_phrase_rerank_large_leap_threshold", 4),
        rerank_cadence_land_bonus=_f(comp, "melody_phrase_rerank_cadence_land_bonus", 0.55),
        rerank_cadence_approach_bonus=_f(comp, "melody_phrase_rerank_cadence_approach_bonus", 0.24),
        rerank_cadence_miss_penalty=_f(comp, "melody_phrase_rerank_cadence_miss_penalty", 0.22),
        offline_quality_render_enabled=_b(comp, "offline_quality_render_enabled", False),
        offline_quality_k_scale=_f(comp, "offline_quality_k_scale", 1.6),
        offline_quality_beam_width=_i(comp, "offline_quality_beam_width", 10),
        listener_memory_enabled=_b(comp, "melody_listener_memory_scorer_enabled", True),
        listener_memory_strength=_f(comp, "melody_listener_memory_scorer_strength", 0.68),
        lyrical_scorer_enabled=_b(comp, "lyrical_melody_scorer_enabled", True),
        lyrical_scorer_strength=_f(comp, "lyrical_melody_scorer_strength", 0.48),
        rerank_masking_weight=_f(comp, "melody_phrase_rerank_masking_weight", 0.25),
        rerank_strongbeat_chord_tone_bonus=_f(
            comp, "melody_phrase_rerank_strongbeat_chord_tone_bonus", 0.10
        ),
        phrase_objective_enabled=_b(comp, "melody_phrase_objective_enabled", False),
        phrase_objective_static_run_weight=_f(comp, "melody_phrase_objective_static_run_weight", 0.22),
        phrase_objective_contour_weight=_f(comp, "melody_phrase_objective_contour_weight", 0.16),
        phrase_objective_long_breath_weight=_f(comp, "melody_phrase_objective_long_breath_weight", 0.12),
        repair_stack_enabled=_b(comp, "melody_phrase_repair_stack_enabled", True),
        neural_phrase_generator_enabled=_b(comp, "neural_phrase_generator_enabled", False),
    )


@dataclass(frozen=True)
class RealtimeFormGroup:
    """Live loop roles, planner effort tier, and realtime energy arc sizing."""

    loop_enabled: bool
    mode_override: str
    drop_outro: bool
    planner_effort: str
    energy_arc_length: int


def realtime_form_group(comp: object) -> RealtimeFormGroup:
    return RealtimeFormGroup(
        loop_enabled=_b(comp, "realtime_form_loop_enabled", True),
        mode_override=_s(comp, "realtime_form_mode_override", ""),
        drop_outro=_b(comp, "realtime_form_loop_drop_outro", True),
        planner_effort=_s(comp, "realtime_planner_effort", "full"),
        energy_arc_length=_i(comp, "realtime_energy_arc_length", 8),
    )


@dataclass(frozen=True)
class CompositionRuntimeProfile:
    """All grouped composition views materialized together from one ``CompositionConfiguration``."""

    melody_role_density: MelodyRoleDensityGroup
    harmony_tension: HarmonyTensionControlGroup
    melody_phrase_planning: MelodyPhrasePlanningGroup
    realtime_form: RealtimeFormGroup


def build_composition_runtime_profile(comp: object) -> CompositionRuntimeProfile:
    """Construct a full profile (four factories in one pass — suitable for caching)."""
    return CompositionRuntimeProfile(
        melody_role_density=melody_role_density_group(comp),
        harmony_tension=harmony_tension_control_group(comp),
        melody_phrase_planning=melody_phrase_planning_group(comp),
        realtime_form=realtime_form_group(comp),
    )
