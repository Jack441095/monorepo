from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class PhraseIntent:
    """
    Shared, realtime-safe phrase intent used to coordinate arp + melody.

    This is intentionally lightweight. It is safe to omit fields by leaving them as
    None/empty; consumers must treat it as advisory.
    """

    phrase_idx: int
    phrase_role: str = ""  # opening|continuation|answer|cadence
    contour: str = ""      # asc|desc|arch|static

    # Suggested lead register lane for this phrase (MIDI).
    register_center_midi: Optional[int] = None
    register_half_width_midi: Optional[int] = None

    # 16th-grid onset steps per bar (0..steps_per_bar-1) for the phrase window.
    # Indexed by absolute bar index within the section.
    melody_onset_steps_by_bar: Optional[List[List[int]]] = None

    # How the arp should relate to the melody onset lattice for this phrase.
    # mirror|complement|hybrid
    arp_onset_policy: str = ""

    # Optional dialogue slots as beat windows (start,end) inside the section timeline.
    # Can be used for explicit “you play / I play” scheduling.
    dialogue_slots: Optional[Sequence[Tuple[float, float, str]]] = None

    # Optional harmony-role hints: support|avoid|answer
    harmony_role: str = ""

