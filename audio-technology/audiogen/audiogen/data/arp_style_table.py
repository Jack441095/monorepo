from __future__ import annotations

from typing import Dict

from data.emotion_aliases import canonical_emotion_name


# ---------------------------------------------------------------------------
# Per-emotion section-level arp style lock.
#
# This complements `data/arp_curve_defaults.EMOTION_ARP_PROFILES` (which shapes the
# arpeggiator's micro-behavior like grid/syncopation/accent/octave reach).
#
# Here we lock macro choices that otherwise drift per section: mode, lane width,
# swing/velocity, and whether to allow scheduled variation.
# ---------------------------------------------------------------------------

ARP_STYLE_TABLE: Dict[str, Dict[str, float | str | bool | int]] = {
    # Gold standards (reference matched)
    "optimism": {
        "mode": "updown",
        "lane_half_width": 7,
        "velocity_scale": 1.00,
        "swing": 0.0,
        "allow_mode_variation": False,
    },
    "neutral": {
        "mode": "updown",
        "lane_half_width": 6,
        "velocity_scale": 1.00,
        "swing": 0.0,
        "allow_mode_variation": False,
    },
    "admiration": {
        "mode": "updown",
        "lane_half_width": 6,
        "velocity_scale": 1.00,
        "swing": 0.0,
        "allow_mode_variation": False,
    },
}


def arp_style_for_emotion(emotion_name: str) -> Dict[str, float | str | bool | int]:
    key = canonical_emotion_name(emotion_name or "neutral")
    return dict(ARP_STYLE_TABLE.get(key, {}))


def pick_style_value(
    style: Dict[str, float | str | bool | int],
    name: str,
    default,
):
    if not style:
        return default
    v = style.get(name)
    return default if v is None else v

