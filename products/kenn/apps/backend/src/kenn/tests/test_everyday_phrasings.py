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


@pytest.mark.parametrize("request_text, track, send_to", [
    ("put 40% of the bass on reverb", "Bass", "reverb"),
    ("add 25% of the drums bus to delay", "Drum Bus", "delay"),
    ("make the vox go to a-reverb at 50%", "Lead Vocal", "reverb"),
])
def test_a_portion_on_the_reverb_is_a_send_not_a_new_device(snapshot, request_text, track, send_to) -> None:
    # Regression (blind check, 25 Sept): these inserted a Reverb device on the track instead of setting its send.
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "set_send" and parsed["track"]["name"] == track
    assert send_to in str(parsed.get("return_track_name") or "").lower()


def test_a_send_with_no_amount_asks_how_much(snapshot) -> None:
    parsed = parse_request("can you add a reverb send to the lead vocal?", snapshot)
    assert parsed["action"] is None and "send_amount" in parsed["missing_fields"]


def test_a_rename_finds_the_track_before_the_new_name(snapshot) -> None:
    # Regression (blind check): "... to main synth" renamed the Synth because "synth" was in the new name.
    parsed = parse_request("rename the track with no devices to main synth", snapshot)
    assert parsed["action"] is None or (parsed["track"] or {}).get("name") != "Synth"
    assert parse_request("rename the synth to Bass Two", snapshot)["track"]["name"] == "Synth"


@pytest.mark.parametrize("request_text, track, db", [
    ("set hats to -6", "Hi-Hats", -6), ("make the clap -12", "Snare / Clap", -12),
    ("could you bring the drums bus down to -20?", "Drum Bus", -20), ("turn the kick down to -16", "Kick", -16),
])
def test_a_negative_bare_number_after_a_verb_is_a_fader_level(snapshot, request_text, track, db) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "set_volume" and parsed["track"]["name"] == track
    assert parsed["desired_value"] == pytest.approx(volume_law.db_to_raw(db), abs=0.005)


@pytest.mark.parametrize("request_text", ["set the kick to 12", "turn the kick down -3", "set the synth pan to -20"])
def test_numbers_that_are_not_clearly_a_fader_level_still_ask(snapshot, request_text) -> None:
    parsed = parse_request(request_text, snapshot)
    assert not (parsed["action"] == "set_volume" and not parsed["missing_fields"]), parsed


@pytest.mark.parametrize("request_text, name", [
    ("put a loc called 'chorus' at the head.", "chorus"), ("mark this point as 'breakdown' please.", "breakdown"),
    ("add a locator here, name it 'hook 2'", "hook 2"),
])
def test_locator_wordings_name_the_locator(snapshot, request_text, name) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "add_locator" and parsed["locator_name"] == name


def test_comp_means_compressor_only_next_to_a_compressor_setting(snapshot) -> None:
    parsed = parse_request("set the drum bus comp threshold to -20 db", snapshot)
    assert parsed["action"] == "set_device_parameter" and parsed["device"]["name"] == "Compressor"
    assert parse_request("vocal comp needs work", snapshot)["action"] is None


@pytest.mark.parametrize("request_text, action, track", [
    ("lower synth 3", "set_volume", "Synth"), ("hard left on vox", "set_pan", "Lead Vocal"),
    ("move clap to centre", "set_pan", "Snare / Clap"), ("set vol -10 on kick", "set_volume", "Kick"),
    ("drum bus comp thres -12", "set_device_parameter", "Drum Bus"), ("voc comp thres down 2", "set_device_parameter", "Lead Vocal"),
])
def test_terse_session_shorthand(snapshot, request_text, action, track) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == action and parsed["track"]["name"] == track and not parsed["missing_fields"]


@pytest.mark.parametrize("request_text, name", [("mark now as intro", "intro"), ("marker now for drop", "drop"),
                                                ("put a mark here for breakdown", "breakdown")])
def test_shorthand_markers(snapshot, request_text, name) -> None:
    assert parse_request(request_text, snapshot)["locator_name"] == name


@pytest.mark.parametrize("request_text, action, track", [
    ("Could you dis-arm the drum bus track please?", "set_arm", "Drum Bus"),
    ("I want to turn off the solo on the drum bus.", "set_solo", "Drum Bus"),
    ("turn off the mute on the bass", "set_mute", "Bass"),
    ("un-mute the kick", "set_mute", "Kick"),
])
def test_switching_something_off_never_switches_it_on(snapshot, request_text, action, track) -> None:
    # Regression (third blind check, 25 Sept): "dis-arm" armed the track and "turn off the solo" soloed it.
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == action and parsed["track"]["name"] == track and parsed["desired_value"] is False


@pytest.mark.parametrize("request_text", ["How do I solo the lead vocal track?", "Is there a way to solo the lead vocal track?"])
def test_a_how_to_question_changes_nothing(snapshot, request_text) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] is None and parsed["missing_fields"] == ["how_to"]


@pytest.mark.parametrize("request_text, new_name", [
    ("I need to rename the synth track to Synth Lead, can you do that?", "Synth Lead"),
    ("Can you rename the vocal track to 'Vox' for clarity?", "Vox"),
    ("Can you rename the hats track to just Hats?", "Hats"),
])
def test_asides_do_not_end_up_in_a_new_name(snapshot, request_text, new_name) -> None:
    assert parse_request(request_text, snapshot)["desired_value"] == new_name


def test_two_tracks_at_the_same_time_are_both_changed(snapshot) -> None:
    # Regression (third blind check): only the Drum Bus was soloed; the vocal was silently dropped.
    from kenn.core.live_intent import parse_natural_recipe

    recipe = parse_natural_recipe("Can you solo the drum bus and the vocal track at the same time?", snapshot)
    assert recipe is not None and len(recipe["segments"]) == 2 and not recipe["ambiguity"]
