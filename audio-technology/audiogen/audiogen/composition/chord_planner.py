# composition/chord_planner.py
"""ChordPlanner: symbolic chord progression planning and extension restoration.

Split 2026-07-14 from a single 2,065-line flat module
(docs/codebase_scan_12_07.md, "large un-decomposed files") into this file
plus three sibling mixin files, layered by dependency (mirrors the existing
composition/mixins/ pattern used for CompositionGenerator's
CachingMixin/PerformanceMixin, since ChordPlanner -- unlike llm_improvement.py
or server.py -- is a single class spanning nearly the entire original file,
not a set of independent module-level functions):

  chord_planner_bias.py         -- leaf layer: token helpers + static bias
                                    functions (opening/cadence/section-role/
                                    phrase-start bias, cadence degree/weight,
                                    tonal-center drift, handoff pivot scoring)
  chord_planner_weighting.py    -- build_chord_candidate_weights, which only
                                    calls into the bias layer (via self.) plus
                                    self.owner state
  chord_planner_sampling.py     -- sample_next_simplified_chord and
                                    restore_chord_extension, which call into
                                    the weighting + bias layers (via self.)
  chord_planner_progression.py  -- prepare_chord_progression and
                                    generate_chord_progression, the top of the
                                    call graph, calling every lower layer

Every name the flat module exposed (the `ChordPlanner` class and its public
methods) is unchanged here, so `from .chord_planner import ChordPlanner` /
`from composition.chord_planner import ChordPlanner` and
`<owner>.chord_planner.<method>(...)` call sites (the only import styles used
anywhere in this codebase for this module -- verified via a repo-wide grep)
keep working with zero changes. Because Python resolves `self.<method>` via
MRO at call time, cross-layer calls between the mixins need no imports
between the mixin files themselves; only this file needs to know about all
four and combine them via multiple inheritance.
"""

from audiogen_core.config import resolve_config

from .chord_planner_bias import _ChordBiasMixin
from .chord_planner_weighting import _ChordWeightingMixin
from .chord_planner_sampling import _ChordSamplingMixin
from .chord_planner_progression import _ChordProgressionMixin


class ChordPlanner(
    _ChordProgressionMixin,
    _ChordSamplingMixin,
    _ChordWeightingMixin,
    _ChordBiasMixin,
):
    """Owns symbolic chord progression planning and extension restoration."""

    def __init__(self, owner):
        self.owner = owner
        # Opt-in richer Markov tokens (degree:function bucket). Keep default off to
        # preserve existing deterministic snapshot outputs unless explicitly enabled.
        self._use_degree_tokens = resolve_config("composition", "harmony_markov_use_degree_tokens", False, bool)
