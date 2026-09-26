"""Dictated and hurried requests, found by the fourth blind set (Qwen3 8B writing the way speech-to-text comes out)."""

from __future__ import annotations

import pytest

from kenn.core import volume_law
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_intent import parse_request


@pytest.fixture(scope="module")
def snapshot():
    return FakeLiveBackend().query_session_state()


@pytest.mark.parametrize("request_text, action, track, value", [
    ("um can you set the kick to minus ten dee bee", "set_volume", "Kick", volume_law.db_to_raw(-10)),
    ("yeah so okay can you set the synth to minus twenty five db", "set_volume", "Synth", volume_law.db_to_raw(-25)),
    ("turn the snare down to minus fifteen", "set_volume", "Snare / Clap", volume_law.db_to_raw(-15)),
    ("i want the drums bus to be minus ten dee bee", "set_volume", "Drum Bus", volume_law.db_to_raw(-10)),
    ("make sure the kick is not muted", "set_mute", "Kick", False),
    ("make sure the hats are muted", "set_mute", "Hi-Hats", True),
    ("make sure the vocal isn't soloed", "set_solo", "Lead Vocal", False),
    ("set the pan on the bass to zero", "set_pan", "Bass", 0.0),
    ("set the send for a reverb to fifty percent on the drum bus", "set_send", "Drum Bus", 0.5),
])
def test_a_dictated_request_means_the_plain_command(snapshot, request_text, action, track, value) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == action and parsed["track"]["name"] == track and not parsed["missing_fields"]
    if isinstance(value, bool):
        assert parsed["desired_value"] is value
    else:
        assert parsed["desired_value"] == pytest.approx(value, abs=0.005)


def test_fillers_in_front_of_a_locator_are_dropped(snapshot) -> None:
    parsed = parse_request("um can you add a locator called intro at the playhead", snapshot)
    assert parsed["action"] == "add_locator" and parsed["locator_name"] == "intro"


def test_make_it_called_is_a_rename(snapshot) -> None:
    parsed = parse_request("yeah so make the snare called clap", snapshot)
    assert parsed["action"] == "rename_track" and parsed["track"]["name"] == "Snare / Clap"


def test_a_compressor_threshold_said_backwards_is_still_the_threshold(snapshot) -> None:
    parsed = parse_request("set the compressor on the drum bus to threshold minus twenty", snapshot)
    assert parsed["action"] == "set_device_parameter" and parsed["track"]["name"] == "Drum Bus"
    assert parsed["parameter"]["name"] == "Threshold" and parsed["desired_value"] == -20.0 and parsed["unit"] == "db"


@pytest.mark.parametrize("request_text, action, track", [
    # Before 26 Sept 2026 the first one changed the Vocal's fader and the second muted track 2.
    ("Set Vocal volume to minus six—actually pan it twenty percent right.", "set_pan", "Lead Vocal"),
    ("mute track 2, actually track 3", "set_mute", "Hi-Hats"),
    ("turn the bass down 2 dB, actually mute it", "set_mute", "Bass"),
])
def test_what_follows_a_correction_is_what_happens(snapshot, request_text, action, track) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == action and parsed["track"]["name"] == track


@pytest.mark.parametrize("request_text", [
    "make the clap a little more snappy and maybe add a little bit of reverb",
    "make the synth a bit brighter maybe add a high shelf on the eq",
])
def test_thinking_aloud_about_an_effect_inserts_nothing(snapshot, request_text) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] is None and "still deciding" in parsed["ambiguity"][0]


@pytest.mark.parametrize("request_text, device", [
    ("add a utility to the synth", "Utility"),
    ("add a filter delay to the synth", "Filter Delay"),  # used to become an Auto Filter
    ("add an eq three to the bass", "EQ Three"),          # used to become an EQ Eight
])
def test_a_device_kenn_cannot_add_is_named_plainly(snapshot, request_text, device) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] is None and parsed["ambiguity"][0].startswith(f"KENN can't add {device} yet")


def test_roar_and_multiband_dynamics_are_recognised(snapshot) -> None:
    assert parse_request("add a roar to the bass", snapshot)["action"] == "insert_device"
    assert parse_request("add a multiband compressor to the synth", snapshot)["device"]["name"] == "Multiband Dynamics"


@pytest.mark.parametrize("request_text, expected", [
    ("mute a-reverb", "A-Reverb is a return track"),
    ("set the volume of the return track b to minus fifteen db", "return track"),
    ("set the send on the hats to delay at minus ten dee bee", "Send level must be 0–100%"),
])
def test_what_kenn_cannot_change_yet_says_so(snapshot, request_text, expected) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] is None and expected in parsed["ambiguity"][0]


def test_two_names_for_one_track_are_one_change() -> None:
    from kenn.core.live_intent import parse_natural_recipe

    # "snare and clap" is the one Snare / Clap track: it used to become a two-step recipe muting it twice.
    assert parse_natural_recipe("mute the snare and clap", FakeLiveBackend().query_session_state()) is None
