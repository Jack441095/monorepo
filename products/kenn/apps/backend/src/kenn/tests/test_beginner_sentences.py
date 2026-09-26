"""Whole polite sentences from beginners, the register the third blind set scored worst on (75%)."""

from __future__ import annotations

import pytest

from kenn.core import volume_law
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_intent import parse_request


@pytest.fixture(scope="module")
def snapshot():
    return FakeLiveBackend().query_session_state()


@pytest.mark.parametrize("request_text, action, track, value", [
    ("I need the bass track to be at -17 dB. Can you adjust that?", "set_volume", "Bass", volume_law.db_to_raw(-17)),
    ("The synth track should be at -15 dB. Could you set it for me?", "set_volume", "Synth", volume_law.db_to_raw(-15)),
    ("Could you move the kick track all the way to the right?", "set_pan", "Kick", 1.0),
    ("I want to move the FX Print track to the far left of the stereo field.", "set_pan", "FX Print", -1.0),
    ("I want the lead vocal track to be perfectly centered again.", "set_pan", "Lead Vocal", 0.0),
    ("I want the clap track to send 30% of its signal to B-Delay. Can you do that?", "set_send", "Snare / Clap", 0.3),
    ("I think the bass track should send 20% to B-Delay. Can you set that for me?", "set_send", "Bass", 0.2),
])
def test_a_sentence_that_states_what_it_wants_is_that_change(snapshot, request_text, action, track, value) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == action and parsed["track"]["name"] == track and not parsed["missing_fields"]
    assert parsed["desired_value"] == pytest.approx(value, abs=0.005)


@pytest.mark.parametrize("request_text, track", [
    ("Can you change the threshold on the compressor for the drums bus by 3 dB up?", "Drum Bus"),
    ("Could you adjust the threshold on the compressor of the lead vocal by -4 dB?", "Lead Vocal"),
])
def test_a_threshold_change_said_the_long_way(snapshot, request_text, track) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "set_device_parameter" and parsed["track"]["name"] == track
    assert parsed["parameter"]["name"] == "Threshold"


@pytest.mark.parametrize("request_text, name", [
    ("Can you add a marker here at the playhead called 'intro start'?", "intro start"),
    ("Could you add a marker named 'chorus' at the current playhead position?", "chorus"),
    ("I want to mark this point as 'transition' with a locator.", "transition"),
])
def test_where_the_locator_goes_is_not_part_of_its_name(snapshot, request_text, name) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "add_locator" and parsed["locator_name"] == name


def test_what_a_new_track_is_for_is_not_its_name(snapshot) -> None:
    parsed = parse_request("Can you create a new MIDI track for me called 'Pads'?", snapshot)
    assert parsed["action"] == "create_midi_track" and parsed["new_track_name"] == "Pads"
    assert parse_request("Can you make a new audio track for my vocal recordings?", snapshot)["action"] == "create_audio_track"


@pytest.mark.parametrize("request_text, track", [
    ("Can you go to the track that has the bass?", "Bass"),
    ("Could you select the track where the hats are?", "Hi-Hats"),
    # Both used to make the change described in the first sentence instead of going to the track.
    ("I want to solo the synth track. Can you go there?", "Synth"),
    ("I want to lower the volume of the hats by 3 dB. Can you show me the hats track?", "Hi-Hats"),
])
def test_go_there_goes_to_the_track(snapshot, request_text, track) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "focus_track" and parsed["track"]["name"] == track
