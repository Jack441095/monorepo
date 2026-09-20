# ai/markov/melody/note_generator/_interval_role_blend.py
"""Phrase-role interval distribution blend (extracted from NoteGeneratorIntervalMixin)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def blend_interval_probs_with_phrase_role(
    markov: Any,
    plan: Any,
    intent: Optional[Any],
    interval_probs: Dict[Any, float],
    interval_context: List[int],
    temperature: float,
    *,
    blend: float,
    role_enabled: bool,
) -> Dict[Any, float]:
    """Optionally mix in ``get_interval_probs_for_role`` when configured and available."""
    if (
        not hasattr(markov, "get_interval_probs_for_role")
        or plan is None
        or not (
            getattr(intent, "phrase_role", None) if intent is not None else getattr(plan, "phrase_role", None)
        )
        or blend <= 1e-6
        or not role_enabled
    ):
        return interval_probs
    try:
        from composition.scoring_utils import blend_probs

        role = (
            str(getattr(intent, "phrase_role", "") or "")
            if intent is not None
            else str(getattr(plan, "phrase_role", "") or "")
        )
        rp = markov.get_interval_probs_for_role(role, interval_context, temperature)
        if rp:
            return blend_probs(interval_probs, rp, float(blend))
    except Exception:
        pass
    return interval_probs
