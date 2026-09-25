"""Everyday ways of saying a mixer change, found by the 505-phrasing check (tooling/data/natural_holdout*.jsonl)."""

from __future__ import annotations

import pytest

from kenn.core import volume_law
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_intent import parse_request


@pytest.fixture(scope="module")
def snapshot():
    return FakeLiveBackend().query_session_state()


@pytest.mark.parametrize("request_text, action, track, value", [
    ("hats at -18 dB please", "set_volume", "Hi-Hats", volume_law.db_to_raw(-18)),
    ("fx print at -15", "set_volume", "FX Print", volume_law.db_to_raw(-15)),
    ("kick fader to minus 10", "set_volume", "Kick", volume_law.db_to_raw(-10)),
    ("yo bass down 2", "set_volume", "Bass", volume_law.db_to_raw(-16)),
    ("kick +2 dB", "set_volume", "Kick", volume_law.db_to_raw(-12)),
    ("hats -3 relative", "set_volume", "Hi-Hats", volume_law.db_to_raw(-17)),
    ("drum bus up a dB", "set_volume", "Drum Bus", volume_law.db_to_raw(-13)),
    ("drumbus down 2 dB", "set_volume", "Drum Bus", volume_law.db_to_raw(-16)),
    ("hats 20% left", "set_pan", "Hi-Hats", -0.2),
    ("synth R30", "set_pan", "Synth", 0.3),
    ("kick dead center", "set_pan", "Kick", 0.0),
    ("re-centre the bass", "set_pan", "Bass", 0.0),
    ("synth off", "set_mute", "Synth", True),
    ("cut the kick out", "set_mute", "Kick", True),
    ("turn the vocal back on", "set_mute", "Lead Vocal", False),
    ("mute the fx print", "set_mute", "FX Print", True),
    ("let me hear the synth alone", "set_solo", "Synth", True),
    ("take the synth out of record", "set_arm", "Synth", False),
])
def test_the_everyday_phrasing_means_the_plain_command(snapshot, request_text, action, track, value) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == action and parsed["track"]["name"] == track and not parsed["missing_fields"]
    assert parsed["desired_value"] == pytest.approx(value, abs=0.005) if not isinstance(value, bool) else parsed["desired_value"] is value


@pytest.mark.parametrize("request_text", [
    "turn it off",            # no track named; stays with the context rules
    "metronome off",          # not a track
    "turn the reverb off",    # a device, not a track mute
    "kick to -9",             # bare number with "to": still asks, as before
    "leave the synth alone",  # "alone" without "hear" is not a solo
])
def test_look_alikes_are_not_rewritten_into_a_change(snapshot, request_text) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] is None or parsed["missing_fields"], parsed


def test_a_marker_placed_here_is_not_named_here(snapshot) -> None:
    # Regression: "put a marker called Build here" named the locator "Build here".
    assert parse_request("put a marker called Build here", snapshot)["locator_name"] == "Build"
