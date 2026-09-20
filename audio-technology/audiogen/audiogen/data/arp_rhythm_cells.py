from __future__ import annotations

from typing import Dict, List, TypedDict

from data.emotion_aliases import canonical_emotion_name


class ArpRhythmCell(TypedDict, total=False):
    name: str
    grid: float
    onset_steps: List[int]          # step indices inside one bar
    accent_steps: List[int]
    swing_hint: float


# Deterministic, DAW-like arp rhythm vocabulary (per bar, 16th grid by default).
# These are *onset* shapes; actual density is still bounded by arpeggiator targets.
ARP_RHYTHM_CELLS: Dict[str, ArpRhythmCell] = {
    # Straight pulse shapes
    "quarters": {"name": "quarters", "grid": 1.0, "onset_steps": [0, 1, 2, 3]},
    "eighths": {"name": "eighths", "grid": 0.5, "onset_steps": [0, 1, 2, 3, 4, 5, 6, 7]},
    "sixteenths_sparse": {"name": "sixteenths_sparse", "grid": 0.25, "onset_steps": [0, 2, 4, 6, 8, 10, 12, 14]},
    "sixteenths": {"name": "sixteenths", "grid": 0.25, "onset_steps": list(range(16))},

    # Syncopated / gap-fill shapes (good for call/response)
    "offbeat_push": {"name": "offbeat_push", "grid": 0.25, "onset_steps": [0, 3, 6, 7, 10, 14]},
    "anticipate_2_4": {"name": "anticipate_2_4", "grid": 0.25, "onset_steps": [0, 7, 8, 15]},
    "claveish": {"name": "claveish", "grid": 0.25, "onset_steps": [0, 6, 8, 12, 14]},

    # Ambient / "snowfall"-style beds (8th grid, breathing holes + anchor bars)
    # These are designed to feel like a loop that evolves, not a constant sequencer.
    "snowfall_breathe": {"name": "snowfall_breathe", "grid": 0.5, "onset_steps": [0, 2, 4, 6]},
    "snowfall_anchor": {"name": "snowfall_anchor", "grid": 0.5, "onset_steps": [0]},
    "snowfall_holes": {"name": "snowfall_holes", "grid": 0.5, "onset_steps": [0, 3, 4, 7]},
}


# Per-emotion macro weights (keep small and safe; section role can override later).
EMOTION_ARP_RHYTHM_WEIGHTS: Dict[str, Dict[str, float]] = {
    "neutral": {"sixteenths_sparse": 1.2, "eighths": 1.0, "offbeat_push": 0.8},
    "optimism": {"sixteenths_sparse": 1.3, "offbeat_push": 1.0, "claveish": 0.9},
    "joy": {"offbeat_push": 1.2, "claveish": 1.1, "sixteenths_sparse": 0.9},
    "excitement": {"sixteenths": 1.2, "offbeat_push": 1.1, "claveish": 0.9},
    "sadness": {"quarters": 1.2, "eighths": 1.0, "sixteenths_sparse": 0.5},
    "grief": {"quarters": 1.3, "eighths": 0.9},

    # Ambient-forward emotions: prefer "breathing" 8ths with occasional anchor bars.
    "serenity": {"snowfall_breathe": 2.4, "snowfall_anchor": 1.6, "eighths": 0.6, "quarters": 0.6},
    "realization": {"snowfall_breathe": 2.0, "snowfall_holes": 1.4, "eighths": 0.7, "sixteenths_sparse": 0.4},
    "curiosity": {"snowfall_holes": 1.8, "snowfall_breathe": 1.4, "offbeat_push": 0.6, "eighths": 0.5},
}


def arp_rhythm_weights_for_emotion(emotion_name: str) -> Dict[str, float]:
    key = canonical_emotion_name(emotion_name or "neutral")
    return dict(EMOTION_ARP_RHYTHM_WEIGHTS.get(key, EMOTION_ARP_RHYTHM_WEIGHTS.get("neutral", {})))

