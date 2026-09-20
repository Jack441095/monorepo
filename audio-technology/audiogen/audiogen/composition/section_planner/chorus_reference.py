# composition/section_planner/chorus_reference.py
"""Reference chorus tuning profiles (arp / melody) for hook-like section roles."""
from __future__ import annotations
from audiogen_core.config import resolve_config

from typing import Dict

from .observability import log_degraded


def chorus_reference_arp_overrides(
    *,
    emotion_name: str,
    section_role: str,
) -> Dict[str, float]:
    role = str(section_role or "").strip().lower()
    if role not in {"b", "chorus", "hook", "tag"}:
        return {}
    comp = resolve_config("composition", "", None)
    if comp is None or not bool(getattr(comp, "chorus_reference_arp_enabled", False)):
        return {}
    path = str(getattr(comp, "chorus_reference_arp_path", ".cache/tuning_suggestions.json") or ".cache/tuning_suggestions.json")
    try:
        from data.reference_chorus_arp import chorus_reference_arp_for_emotion

        return chorus_reference_arp_for_emotion(
            emotion_name=str(emotion_name or ""),
            profile_path=path,
        )
    except Exception as exc:
        log_degraded("chorus_reference_arp.profile", exc, emotion_name=emotion_name)
        return {}


def chorus_reference_melody_overrides(
    *,
    emotion_name: str,
    section_role: str,
) -> Dict[str, float]:
    role = str(section_role or "").strip().lower()
    if role not in {"b", "chorus", "hook", "tag"}:
        return {}
    comp = resolve_config("composition", "", None)
    if comp is None or not bool(getattr(comp, "chorus_reference_melody_enabled", False)):
        return {}
    path = str(
        getattr(comp, "chorus_reference_melody_path", ".cache/tuning_suggestions.json")
        or ".cache/tuning_suggestions.json"
    )
    try:
        from data.reference_chorus_melody import chorus_reference_melody_for_emotion

        return chorus_reference_melody_for_emotion(
            emotion_name=str(emotion_name or ""),
            profile_path=path,
        )
    except Exception as exc:
        log_degraded("chorus_reference_melody.profile", exc, emotion_name=emotion_name)
        return {}