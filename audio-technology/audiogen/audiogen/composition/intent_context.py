from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class IntentContext:
    """
    Shared "musical intent" container to keep composition planning signals
    consistent across harmony + melody samplers.
    """

    section_role: str = ""
    phrase_role: str = ""
    contour: str = "static"
    phrase_idx: int = 0
    total_phrases: int = 1
    output_channel: int = 2

    # Cadence intent (diatonic degree target at phrase end).
    cadence_degree: int = 0
    cadence_zone_start: float = 0.75
    is_final_phrase: bool = False

    # Melody intent targets (soft constraints; best-effort).
    register_center_midi: Optional[int] = None
    register_half_width_midi: Optional[int] = None
    hook_anchor_degree: Optional[int] = None
    chord_tone_push: float = 1.0

    @staticmethod
    def from_phrase_plan(plan) -> Optional["IntentContext"]:
        if plan is None:
            return None
        try:
            return IntentContext(
                section_role=str(getattr(plan, "section_role", "") or ""),
                phrase_role=str(getattr(plan, "phrase_role", "") or ""),
                contour=str(getattr(plan, "contour", "static") or "static"),
                phrase_idx=int(getattr(plan, "phrase_idx", 0) or 0),
                total_phrases=int(getattr(plan, "total_phrases", 1) or 1),
                output_channel=int(getattr(plan, "output_channel", 2) or 2),
                cadence_degree=int(getattr(plan, "cadence_degree", 0) or 0),
                cadence_zone_start=float(getattr(plan, "cadence_zone_start", 0.75) or 0.75),
                is_final_phrase=bool(getattr(plan, "is_final_phrase", False)),
                register_center_midi=getattr(plan, "register_center_midi", None),
                register_half_width_midi=getattr(plan, "register_half_width_midi", None),
                hook_anchor_degree=getattr(plan, "hook_anchor_degree", None),
                chord_tone_push=float(getattr(plan, "chord_tone_push", 1.0) or 1.0),
            )
        except Exception:
            return None

