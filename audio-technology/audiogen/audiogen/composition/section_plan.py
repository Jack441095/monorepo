# composition/section_plan.py
# Project module `section_plan` (composition).

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from data.music_data import EmotionProfile

if TYPE_CHECKING:
    from .harmonic_plan import HarmonicPlan


@dataclass
class SectionPlan:
    emotion: EmotionProfile
    root_note: int
    bars: int
    beats_per_bar: float = 4.0
    # Structural labels for this section (used for motif scheduling + debugging).
    section_index: int = 0
    section_role: str = ""
    chords: List[str] = field(default_factory=list)
    roots: List[int] = field(default_factory=list)
    chosen_bass: List[int] = field(default_factory=list)
    chosen_chord: List[List[int]] = field(default_factory=list)
    chosen_melody: List[int] = field(default_factory=list)
    melody_events: List[Tuple] = field(default_factory=list)
    arp_events: List[Tuple] = field(default_factory=list)
    counter_events: List[Tuple] = field(default_factory=list)
    bass_events: List[Tuple] = field(default_factory=list)
    chord_events: List[Tuple] = field(default_factory=list)
    drone_event: Optional[Tuple] = None
    events: List[Tuple] = field(default_factory=list)
    # Snapshot of ArrangementPolicy.arrangement_curve for this section (velocity / mix).
    arrangement_curve: Optional[Dict[str, Any]] = None
    # Optional per-bar targets for downstream layers (analysis/debugging + future conformity).
    timeline_targets: Optional[Dict[str, Any]] = None
    # Optional semantic annotations aligned 1:1 with `events` (tuple playback remains unchanged).
    # Each annotation is a dict with best-effort keys like:
    #   section_index, role, bar_index, phrase_id, phrase_role, layer, motif_id, motif_variant
    event_annotations: List[Dict[str, Any]] = field(default_factory=list)
    # Optional higher-level phrase spans for debug and motif-aware scheduling.
    # Each item is a dict like: phrase_id, start_beats, length_beats, bar_start, bar_end, phrase_role
    phrase_spans: List[Dict[str, Any]] = field(default_factory=list)
    # Optional compact debug trace (per-bar dicts). Populated in SectionPlanner finalization.
    debug_trace_by_bar: List[Dict[str, Any]] = field(default_factory=list)
    # Optional phrase intent snapshot aligned by bar index.
    # Each item is a compact dict (phrase role, cadence strength, harmony target, activity targets).
    phrase_intent_by_bar: List[Dict[str, Any]] = field(default_factory=list)
    # Compact per-section hook/motif lifecycle trace, populated by MotifPlanManager.
    motif_development: Dict[str, Any] = field(default_factory=dict)
    # Immutable snapshot after voicing/register shaping; see ``refresh_harmonic_plan``.
    harmonic_plan: Optional["HarmonicPlan"] = None
    # Snapshot after late orchestration (e.g. busy voicing trim); see ``refresh_harmonic_plan_comping``.
    harmonic_plan_comping: Optional["HarmonicPlan"] = None
    # When ``arp_chord_harmonic_rhythm_shared_enabled``, per-bar Markov actions (hold/half/anticipate/sus)
    # shared by the arpeggiator and ``generate_chord_events`` so intra-bar chord changes align.
    harmonic_rhythm_action_by_bar: List[Optional[str]] = field(default_factory=list)
    # Phase C: shared harmony/melody/texture intent for this section.
    joint_section_plan: Optional[Dict[str, Any]] = None
    joint_hook_blueprint: Optional[Dict[str, Any]] = None

    def refresh_harmonic_plan(self) -> None:
        """Rebuild ``harmonic_plan`` from current chords/roots/voicing/lanes (call after edits)."""
        from .harmonic_plan import HarmonicPlan

        self.harmonic_plan = HarmonicPlan.from_section_plan(self)

    def refresh_harmonic_plan_comping(self) -> None:
        """Rebuild ``harmonic_plan_comping`` from current plan (call after voicing trim, before chord comping)."""
        from .harmonic_plan import HarmonicPlan

        self.harmonic_plan_comping = HarmonicPlan.from_section_plan(self)
