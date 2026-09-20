"""Tests for AudioGen composition/groove_engine.py."""

from __future__ import annotations

from composition.groove_engine import (
    get_groove_config,
    apply_groove_to_events,
)


def test_get_groove_config_profiles():
    lofi = get_groove_config("lofi")
    assert lofi.profile_name == "lofi_swing"
    assert lofi.swing_ratio == 0.60

    boombap = get_groove_config("hiphop")
    assert boombap.profile_name == "hiphop_boombap"
    assert boombap.laidback_ticks == 12

    straight = get_groove_config("unknown_genre")
    assert straight.profile_name == "straight"
    assert straight.swing_ratio == 0.50


def test_apply_groove_to_events_swing_and_velocity():
    events = [
        {"start_tick": 0, "duration_ticks": 120, "velocity": 80, "role": "kick"},
        {"start_tick": 120, "duration_ticks": 120, "velocity": 80, "role": "hihat"},
        {"start_tick": 240, "duration_ticks": 120, "velocity": 80, "role": "snare"},
    ]

    humanized = apply_groove_to_events(events, groove="lofi", ticks_per_16th=120, seed=42)
    assert len(humanized) == 3

    # Offbeat 16th (start_tick=120) should receive swing offset
    assert humanized[1]["start_tick"] > 120

    # Downbeat (start_tick=0) should receive downbeat accent
    assert humanized[0]["velocity"] >= 80
