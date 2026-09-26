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


@pytest.mark.parametrize("request_text, action, track", [
    # The fifth blind set (26 Sept): the reason named another track, and KENN changed that one.
    ("Could you lower the snare by 2 dB to make it sit behind the kick a bit more?", "set_volume", "Snare / Clap"),
    ("I want to mute the snare and clap to focus on the hi-hats. Is that okay?", "set_mute", "Snare / Clap"),
    ("I want to reduce the kick by 4 dB, please.", "set_volume", "Kick"),  # this "to" starts the request
])
def test_the_reason_after_a_request_is_not_part_of_it(snapshot, request_text, action, track) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == action and parsed["track"]["name"] == track


def test_a_hedged_level_is_where_it_should_end_up(snapshot) -> None:
    # "a bit louder, maybe -13 dB" was read as 13 dB louder: the Bass went to about -1 dB.
    parsed = parse_request("I'd like the bass to be slightly louder, maybe -13 dB, so it has more punch, is that okay?", snapshot)
    assert parsed["action"] == "set_volume" and parsed["desired_value"] == pytest.approx(volume_law.db_to_raw(-13), abs=0.005)


def test_a_rename_keeps_only_the_quoted_name(snapshot) -> None:
    parsed = parse_request("I'd like to rename the FX Print track to 'FX Send' for clarity. Is that okay?", snapshot)
    assert parsed["action"] == "rename_track" and parsed["desired_value"] == "FX Send"


@pytest.mark.parametrize("request_text", [
    "The drum bus is set to -14 dB, but I want to make sure the compressor is working properly. Could you check that?",
    "the kick is at -10 dB",
])
def test_describing_the_set_changes_nothing(snapshot, request_text) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] is None and not parsed["confirmation_required"]
