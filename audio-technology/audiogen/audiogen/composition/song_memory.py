# composition/song_memory.py
# Project module `song_memory` (composition).

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple


def _event_midi(event: Tuple[Any, ...]) -> Optional[int]:
    if not (isinstance(event, tuple) and len(event) == 6):
        return None
    if int(event[0]) != 2:
        return None
    notes = event[5]
    try:
        if isinstance(notes, list) and notes:
            return int(notes[0])
        return int(event[1])
    except Exception:
        return None


@dataclass
class SongMemory:
    """Compact whole-song state shared across composition subsystems.

    This deliberately mirrors existing legacy attributes first. Call sites can
    migrate gradually without changing playback behavior.
    """

    max_recent_sections: int = 8
    section_count: int = 0
    last_section_role: str = ""
    last_section_index: int = -1
    last_chord_signature: Tuple[str, ...] = ()
    last_register_center: Optional[float] = None
    last_cadence_strength: Optional[float] = None
    last_motif_development: Dict[str, Any] = field(default_factory=dict)
    chorus_hook_signature: Tuple[int, ...] = ()
    chorus_hook_span: float = 0.0
    chorus_hook_events: List[Dict[str, Any]] = field(default_factory=list)
    cross_lane_motif_bus: Dict[str, Any] = field(default_factory=dict)
    recent_roles: Deque[str] = field(default_factory=lambda: deque(maxlen=8))
    recent_chord_signatures: Deque[Tuple[str, ...]] = field(default_factory=lambda: deque(maxlen=8))
    recent_register_centers: Deque[float] = field(default_factory=lambda: deque(maxlen=8))

    def __post_init__(self) -> None:
        self.recent_roles = deque(self.recent_roles, maxlen=int(self.max_recent_sections))
        self.recent_chord_signatures = deque(
            self.recent_chord_signatures,
            maxlen=int(self.max_recent_sections),
        )
        self.recent_register_centers = deque(
            self.recent_register_centers,
            maxlen=int(self.max_recent_sections),
        )

    def reset(self) -> None:
        self.section_count = 0
        self.last_section_role = ""
        self.last_section_index = -1
        self.last_chord_signature = ()
        self.last_register_center = None
        self.last_cadence_strength = None
        self.last_motif_development = {}
        self.chorus_hook_signature = ()
        self.chorus_hook_span = 0.0
        self.chorus_hook_events = []
        self.cross_lane_motif_bus = {}
        self.recent_roles.clear()
        self.recent_chord_signatures.clear()
        self.recent_register_centers.clear()

    def remember_chorus_hook(self, memory: Dict[str, Any]) -> None:
        rows = list(memory.get("events", []) or [])
        self.chorus_hook_span = float(memory.get("span", 0.0) or 0.0)
        self.chorus_hook_events = [dict(row) for row in rows if isinstance(row, dict)]
        signature: List[int] = []
        for row in self.chorus_hook_events[:8]:
            try:
                signature.append(int(row.get("root_offset", 0)))
            except Exception:
                continue
        self.chorus_hook_signature = tuple(signature)

    def remember_section(
        self,
        plan: Any,
        *,
        section_role: str = "",
        section_index: int = -1,
    ) -> None:
        role = str(section_role or getattr(plan, "section_role", "") or "").strip().lower()
        chords = list(getattr(plan, "chords", []) or [])
        signature = tuple(str(c) for c in chords[: min(4, len(chords))])

        melody_events = list(getattr(plan, "melody_events", []) or [])
        mids = [m for m in (_event_midi(ev) for ev in melody_events) if m is not None]
        register_center = (sum(mids) / float(len(mids))) if mids else None

        cadence_strength = self._cadence_strength(getattr(plan, "phrase_intent_by_bar", []) or [])

        self.section_count += 1
        self.last_section_role = role
        self.last_section_index = int(section_index)
        self.last_chord_signature = signature
        self.last_register_center = register_center
        self.last_cadence_strength = cadence_strength
        self.last_motif_development = dict(getattr(plan, "motif_development", {}) or {})

        if role:
            self.recent_roles.append(role)
        if signature:
            self.recent_chord_signatures.append(signature)
        if register_center is not None:
            self.recent_register_centers.append(float(register_center))

    @staticmethod
    def _cadence_strength(rows: Iterable[Any]) -> Optional[float]:
        vals: List[float] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw = row.get("cadence_strength", row.get("cadence"))
            try:
                vals.append(float(raw))
            except Exception:
                continue
        if not vals:
            return None
        tail = vals[-2:] if len(vals) >= 2 else vals
        return sum(tail) / float(len(tail))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "section_count": int(self.section_count),
            "last_section_role": self.last_section_role,
            "last_section_index": int(self.last_section_index),
            "last_chord_signature": list(self.last_chord_signature),
            "last_register_center": self.last_register_center,
            "last_cadence_strength": self.last_cadence_strength,
            "last_motif_development": dict(self.last_motif_development),
            "chorus_hook_signature": list(self.chorus_hook_signature),
            "chorus_hook_span": float(self.chorus_hook_span),
            "recent_roles": list(self.recent_roles),
            "recent_chord_signatures": [list(sig) for sig in self.recent_chord_signatures],
            "recent_register_centers": list(self.recent_register_centers),
        }
