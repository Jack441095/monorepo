"""Ways of saying a mixer change that the 29 Sept blind check (tooling/data/natural_blind_claude_2026-09-29.jsonl) found."""

from __future__ import annotations

import pytest

from kenn.core import volume_law
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_intent import parse_request


@pytest.fixture(scope="module")
def snapshot():
    return FakeLiveBackend().query_session_state()


@pytest.mark.parametrize("request_text, track, db", [
    ("get the kick sitting around minus 9", "Kick", -9),
    ("hats @ -17dB", "Hi-Hats", -17),
    ("drum bus at minus eight", "Drum Bus", -8),
    ("bass to zero dB", "Bass", 0),
    ("vocal fader down to -3.5", "Lead Vocal", -3.5),
    ("let's put the bass at minus 10 for now", "Bass", -10),
    ("the clap should live at -13", "Snare / Clap", -13),
    ("put synth on -16", "Synth", -16),
])
def test_a_level_said_the_producers_way_is_a_fader_level(snapshot, request_text, track, db) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "set_volume" and parsed["track"]["name"] == track and not parsed["missing_fields"]
    assert parsed["desired_value"] == pytest.approx(volume_law.db_to_raw(db), abs=0.005)


@pytest.mark.parametrize("request_text, track, delta_db", [
    ("give me 3 more dB on the kick", "Kick", 3),
    ("quieten the hats by four dB", "Hi-Hats", -4),
    ("hi hats too loud, down 3", "Hi-Hats", -3),
])
def test_a_relative_change_said_the_producers_way(snapshot, request_text, track, delta_db) -> None:
    current = next(t for t in snapshot["tracks"] if t["name"] == track)["volume"]
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "set_volume" and parsed["track"]["name"] == track and not parsed["missing_fields"]
    assert parsed["desired_value"] == pytest.approx(volume_law.db_to_raw(volume_law.raw_to_db(current) + delta_db), abs=0.005)


@pytest.mark.parametrize("request_text, action, track, value", [
    ("swing the snare 15% to the right", "set_pan", "Snare / Clap", 0.15),
    ("synth over to the left, 30 percent", "set_pan", "Synth", -0.3),
    ("shut the hats up", "set_mute", "Hi-Hats", True),
    ("I need to hear just the vocal", "set_solo", "Lead Vocal", True),
    ("stop soloing the hats", "set_solo", "Hi-Hats", False),
    ("get the lead vocal armed", "set_arm", "Lead Vocal", True),
])
def test_pan_mute_solo_and_arm_said_the_producers_way(snapshot, request_text, action, track, value) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == action and parsed["track"]["name"] == track and not parsed["missing_fields"]
    assert parsed["desired_value"] == pytest.approx(value) if not isinstance(value, bool) else parsed["desired_value"] is value


@pytest.mark.parametrize("request_text, track", [
    ("feed the synth into the reverb at 50%", "Synth"),
    ("hats to the b-delay about 15 percent", "Hi-Hats"),
    ("turn the vocal reverb send down to 10%", "Lead Vocal"),
    ("clap into the a-reverb 35 percent", "Snare / Clap"),
])
def test_a_send_said_the_producers_way(snapshot, request_text, track) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "set_send" and parsed["track"]["name"] == track and not parsed["missing_fields"]


def test_killing_a_send_never_mutes_the_track(snapshot) -> None:
    # Regression (blind check, 29 Sept): "kill the send from bass to delay" proposed muting the Bass.
    parsed = parse_request("kill the send from bass to delay", snapshot)
    assert parsed["action"] == "set_send" and parsed["track"]["name"] == "Bass" and parsed["desired_value"] == 0.0


@pytest.mark.parametrize("request_text, action", [
    ("pause it there", "transport_stop"), ("let's hear it", "transport_play"),
])
def test_transport_said_the_producers_way(snapshot, request_text, action) -> None:
    assert parse_request(request_text, snapshot)["action"] == action


@pytest.mark.parametrize("request_text, name", [
    ("set a marker: Breakdown", "Breakdown"), ("new locator, name it Pre-drop", "Pre-drop"),
])
def test_locators_said_the_producers_way(snapshot, request_text, name) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "add_locator" and parsed["locator_name"] == name


@pytest.mark.parametrize("request_text, track, new_name", [
    ("the fx print should be called Bounce", "FX Print", "Bounce"),
    ("relabel the hats as Shaker", "Hi-Hats", "Shaker"),
])
def test_renames_said_the_producers_way(snapshot, request_text, track, new_name) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "rename_track" and parsed["track"]["name"] == track and parsed["desired_value"] == new_name


def test_a_rename_with_no_separator_asks_instead_of_guessing_where_the_name_starts(snapshot) -> None:
    # "name the lead vocal Main Vox" could be "lead" + "vocal Main Vox"; it renamed the track to "vocal Main Vox".
    parsed = parse_request("name the lead vocal Main Vox", snapshot)
    assert parsed["action"] is None or parsed["desired_value"] != "vocal Main Vox", parsed


def test_backing_off_a_compressor_threshold_asks_which_way(snapshot) -> None:
    # "back off" means less compression, which is a higher threshold; "lower" would have moved it the other way.
    parsed = parse_request("back the vocal compressor threshold off by 2 dB", snapshot)
    assert parsed["action"] is None or parsed["missing_fields"], parsed


@pytest.mark.parametrize("request_text", [
    "lead vocal to -4",       # no verb and no unit: still asks (test_everyday_phrasings pins this)
    "snare clap -12",         # a level, or 12 dB down: it asks
    "kick 2 more",            # more of what
])
def test_shapes_that_are_not_clearly_a_level_still_ask(snapshot, request_text) -> None:
    parsed = parse_request(request_text, snapshot)
    assert not (parsed["action"] == "set_volume" and not parsed["missing_fields"]), parsed
