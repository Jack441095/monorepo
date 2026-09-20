# composition/song_postprocess — whole-song polish after section stitch.
# Submodules: _common, scale_guards, form_polish, texture_floors.

from __future__ import annotations

from ._common import Event, _section_starts
from .form_polish import (
    add_arrangement_continuity_anchors,
    add_melody_reprises,
    add_section_boundary_melodic_pickups,
    cap_song_lead_leaps,
    develop_song_theme_and_rewrite_hooks,
    reinforce_song_hook_identity,
    guard_excessive_chorus_register_jumps,
    guard_reflective_chorus_register,
    lift_bright_chorus_registers,
    professionalize_song_form,
    reduce_repeated_song_lead_pitches,
    reinforce_bright_chorus_payoffs,
    reinforce_chorus_harmonic_motion,
    reinforce_chorus_melody_action,
    shape_emotional_lead_contours,
    shape_phrase_level_emotional_contours,
    shape_reflective_chorus_breathing,
    shape_reflective_song_negative_space,
)
from .scale_guards import (
    anchor_strongbeat_lead_to_chords,
    repair_song_phrase_end_chord_tones,
    snap_lead_to_section_scales,
    snap_song_notes_to_section_scales,
)
from .texture_floors import (
    duck_arp_under_active_lead,
    reduce_chorus_arp_lead_overlap,
    reduce_song_lead_arp_overlap,
    reinforce_chorus_arp_floor,
    reinforce_chorus_counterline_floor,
    reinforce_nonchorus_ambient_arp_floor,
    separate_chorus_lead_from_arp_bed,
    soften_reflective_harmonic_motion,
    strip_arp_outside_chorus_for_suppressed_primary,
)

__all__ = [
    "Event",
    "_section_starts",
    "add_arrangement_continuity_anchors",
    "add_melody_reprises",
    "add_section_boundary_melodic_pickups",
    "anchor_strongbeat_lead_to_chords",
    "cap_song_lead_leaps",
    "develop_song_theme_and_rewrite_hooks",
    "duck_arp_under_active_lead",
    "guard_excessive_chorus_register_jumps",
    "guard_reflective_chorus_register",
    "lift_bright_chorus_registers",
    "professionalize_song_form",
    "reduce_chorus_arp_lead_overlap",
    "reduce_song_lead_arp_overlap",
    "reduce_repeated_song_lead_pitches",
    "reinforce_bright_chorus_payoffs",
    "reinforce_chorus_arp_floor",
    "reinforce_chorus_counterline_floor",
    "reinforce_song_hook_identity",
    "reinforce_chorus_harmonic_motion",
    "reinforce_chorus_melody_action",
    "reinforce_nonchorus_ambient_arp_floor",
    "repair_song_phrase_end_chord_tones",
    "separate_chorus_lead_from_arp_bed",
    "shape_emotional_lead_contours",
    "shape_phrase_level_emotional_contours",
    "shape_reflective_chorus_breathing",
    "shape_reflective_song_negative_space",
    "snap_lead_to_section_scales",
    "snap_song_notes_to_section_scales",
    "soften_reflective_harmonic_motion",
    "strip_arp_outside_chorus_for_suppressed_primary",
]
