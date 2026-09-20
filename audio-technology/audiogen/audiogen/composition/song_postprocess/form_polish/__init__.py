# composition/song_postprocess/form_polish/__init__.py
# Public entry point for `composition.song_postprocess.form_polish`.
#
# Re-exports every name external callers import from this module, preserved
# exactly from the pre-split flat file:
#   - `composition/song_postprocess/__init__.py` does `from .form_polish import (...)`
#     for the 18 public postprocess passes below.
#   - tests/audiogen/test_song_postprocess_motif_development.py imports the
#     PRIVATE helper `_apply_developed_motif_variation` directly, so it must stay
#     re-exported here too, not just the public passes.
#   - tests/audiogen/test_song_postprocess_hook_identity.py imports
#     `reinforce_song_hook_identity` directly.
#
# Submodules (leaf-to-root):
#   _constants.py        -> shared emotion/family frozensets (no deps within this package)
#   contours.py           -> shape_emotional_lead_contours, shape_phrase_level_emotional_contours
#   motif_theme.py        -> _apply_developed_motif_variation, develop_song_theme_and_rewrite_hooks
#   reprise_hooks.py      -> add_melody_reprises, reinforce_song_hook_identity
#   continuity.py         -> add_section_boundary_melodic_pickups, add_arrangement_continuity_anchors
#   chorus_registers.py   -> reinforce_bright_chorus_payoffs, lift_bright_chorus_registers,
#                            reinforce_chorus_melody_action
#   reflective.py         -> shape_reflective_chorus_breathing, shape_reflective_song_negative_space,
#                            guard_reflective_chorus_register
#   chorus_guards.py      -> guard_excessive_chorus_register_jumps, reinforce_chorus_harmonic_motion
#   lead_cleanup.py        -> reduce_repeated_song_lead_pitches, cap_song_lead_leaps
#   professionalize.py    -> professionalize_song_form
#
# None of these passes call each other across files (mapped via the internal call
# graph before splitting) except `develop_song_theme_and_rewrite_hooks` calling its
# own private `_apply_developed_motif_variation`, which is why those two stayed
# together in `motif_theme.py`.

from __future__ import annotations

from .chorus_guards import guard_excessive_chorus_register_jumps, reinforce_chorus_harmonic_motion
from .chorus_registers import (
    lift_bright_chorus_registers,
    reinforce_bright_chorus_payoffs,
    reinforce_chorus_melody_action,
)
from .continuity import add_arrangement_continuity_anchors, add_section_boundary_melodic_pickups
from .contours import shape_emotional_lead_contours, shape_phrase_level_emotional_contours
from .lead_cleanup import cap_song_lead_leaps, reduce_repeated_song_lead_pitches
from .motif_theme import _apply_developed_motif_variation, develop_song_theme_and_rewrite_hooks
from .professionalize import professionalize_song_form
from .reflective import (
    guard_reflective_chorus_register,
    shape_reflective_chorus_breathing,
    shape_reflective_song_negative_space,
)
from .reprise_hooks import add_melody_reprises, reinforce_song_hook_identity

__all__ = [
    "_apply_developed_motif_variation",
    "add_arrangement_continuity_anchors",
    "add_melody_reprises",
    "add_section_boundary_melodic_pickups",
    "cap_song_lead_leaps",
    "develop_song_theme_and_rewrite_hooks",
    "guard_excessive_chorus_register_jumps",
    "guard_reflective_chorus_register",
    "lift_bright_chorus_registers",
    "professionalize_song_form",
    "reduce_repeated_song_lead_pitches",
    "reinforce_bright_chorus_payoffs",
    "reinforce_chorus_harmonic_motion",
    "reinforce_chorus_melody_action",
    "reinforce_song_hook_identity",
    "shape_emotional_lead_contours",
    "shape_phrase_level_emotional_contours",
    "shape_reflective_chorus_breathing",
    "shape_reflective_song_negative_space",
]
