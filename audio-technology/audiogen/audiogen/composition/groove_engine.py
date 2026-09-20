"""Groove Engine module for LLM AudioGen.

Provides micro-timing offsets, swing ratios, and velocity dynamics humanization
across genres (Lo-Fi, Hip-Hop, EDM, Pop, Acoustic).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


GROOVE_PROFILES = {
    "lofi_swing": {
        "swing_ratio": 0.60,       # 60% 16th swing
        "laidback_ticks": 8,       # Laid-back feel
        "velocity_jitter": 8,
        "timing_jitter_ticks": 5,
    },
    "hiphop_boombap": {
        "swing_ratio": 0.58,
        "laidback_ticks": 12,      # Snare drag
        "velocity_jitter": 12,
        "timing_jitter_ticks": 6,
    },
    "edm_shuffle": {
        "swing_ratio": 0.54,
        "laidback_ticks": 0,
        "velocity_jitter": 4,
        "timing_jitter_ticks": 2,
    },
    "acoustic_human": {
        "swing_ratio": 0.52,
        "laidback_ticks": 4,
        "velocity_jitter": 10,
        "timing_jitter_ticks": 7,
    },
    "straight": {
        "swing_ratio": 0.50,
        "laidback_ticks": 0,
        "velocity_jitter": 3,
        "timing_jitter_ticks": 1,
    },
}


@dataclass
class GrooveConfig:
    profile_name: str = "straight"
    swing_ratio: float = 0.50
    laidback_ticks: int = 0
    velocity_jitter: int = 4
    timing_jitter_ticks: int = 2


def get_groove_config(genre_or_profile: str) -> GrooveConfig:
    """Retrieve GrooveConfig by profile or genre name."""
    name = genre_or_profile.lower()
    if name in ("lofi", "lo-fi", "lofi_swing"):
        key = "lofi_swing"
    elif name in ("hiphop", "hip-hop", "hiphop_boombap", "boom_bap"):
        key = "hiphop_boombap"
    elif name in ("edm", "electronic", "dance", "edm_shuffle"):
        key = "edm_shuffle"
    elif name in ("acoustic", "folk", "jazz", "acoustic_human"):
        key = "acoustic_human"
    else:
        key = "straight"

    prof = GROOVE_PROFILES[key]
    return GrooveConfig(
        profile_name=key,
        swing_ratio=prof["swing_ratio"],
        laidback_ticks=prof["laidback_ticks"],
        velocity_jitter=prof["velocity_jitter"],
        timing_jitter_ticks=prof["timing_jitter_ticks"],
    )


def apply_groove_to_events(
    events: list[dict[str, Any]],
    groove: GrooveConfig | str = "straight",
    ticks_per_16th: int = 120,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Applies micro-timing swing, laidback offset, and velocity humanization to MIDI events.

    Parameters
    ----------
    events : list[dict]
        Each event dict has keys: 'start_tick', 'duration_ticks', 'velocity', 'pitch', etc.
    groove : GrooveConfig or str
        Target groove profile.
    ticks_per_16th : int
        Number of ticks per 16th note (default 120 ticks = 480 PPQ).
    seed : int, optional
        Random seed for deterministic testing.

    Returns
    -------
    list[dict]
        New list of humanized MIDI events.
    """
    if isinstance(groove, str):
        config = get_groove_config(groove)
    else:
        config = groove

    rng = random.Random(seed) if seed is not None else random.Random()
    modified_events = []

    for ev in events:
        new_ev = dict(ev)
        start = new_ev.get("start_tick", 0)
        vel = new_ev.get("velocity", 80)
        role = new_ev.get("role", "").lower()

        # 1. Swing Calculation for offbeat 16ths (odd 16th note index)
        subdiv_16th = (start // ticks_per_16th) % 2
        swing_offset = 0
        if subdiv_16th == 1 and config.swing_ratio > 0.50:
            swing_offset = int((config.swing_ratio - 0.50) * 2 * ticks_per_16th)

        # 2. Laidback snare/backbeat offset
        laidback_offset = 0
        if "snare" in role or "backbeat" in role:
            laidback_offset = config.laidback_ticks

        # 3. Timing Jitter
        jitter = rng.randint(-config.timing_jitter_ticks, config.timing_jitter_ticks) if config.timing_jitter_ticks > 0 else 0

        # Apply final start tick offset
        final_start = max(0, start + swing_offset + laidback_offset + jitter)
        new_ev["start_tick"] = final_start

        # 4. Velocity Humanization & Downbeat Accent
        vel_jitter = rng.randint(-config.velocity_jitter, config.velocity_jitter) if config.velocity_jitter > 0 else 0
        bar_pos_16th = (start // ticks_per_16th) % 16
        accent = 6 if bar_pos_16th in (0, 8) else (3 if bar_pos_16th in (4, 12) else 0)

        final_vel = max(1, min(127, vel + vel_jitter + accent))
        new_ev["velocity"] = final_vel

        modified_events.append(new_ev)

    return modified_events
