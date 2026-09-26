"""Requests in the words of someone coming from Logic or FL Studio, from the fourth blind set's sealed half."""

from __future__ import annotations

import pytest

from kenn.core import volume_law
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_intent import parse_request


@pytest.fixture(scope="module")
def snapshot():
    return FakeLiveBackend().query_session_state()


@pytest.mark.parametrize("request_text, track, db", [
    # Both used to change the track numbered by the value: track 5 is the Bass, track 3 the Hi-Hats.
    ("Move the synth track 5 dB louder", "Synth", -9),
    ("move the kick track 3 dB louder", "Kick", -11),
])
def test_a_value_after_the_word_track_is_not_a_track_number(snapshot, request_text, track, db) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "set_volume" and parsed["track"]["name"] == track
    assert parsed["desired_value"] == pytest.approx(volume_law.db_to_raw(db), abs=0.005)


def test_track_numbers_still_work(snapshot) -> None:
    parsed = parse_request("turn track 5 down 3 dB", snapshot)
    assert parsed["action"] == "set_volume" and parsed["track"]["name"] == "Bass"


@pytest.mark.parametrize("request_text", [
    "Why is the FX Print track set to 0 dB?",  # used to propose setting it to 0 dB
    "should the kick be at -10 db?",
])
def test_a_question_about_the_set_changes_nothing(snapshot, request_text) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] is None and parsed["ambiguity"][0].startswith("That's a question")


def test_is_it_possible_to_is_still_a_request(snapshot) -> None:
    parsed = parse_request("is it possible to mute the hats", snapshot)
    assert parsed["action"] == "set_mute" and parsed["track"]["name"] == "Hi-Hats"


@pytest.mark.parametrize("request_text, track, value", [
    ("Send the kick track to A-Reverb with 50%", "Kick", 0.5),
    ("Set the A-Reverb send to 50% on the Drum Bus.", "Drum Bus", 0.5),
    ("Set the B-Delay send to 30% on the Bass track.", "Bass", 0.3),
    ("Send the 'Lead Vocal' track to the 'A-Reverb' bus at 50%.", "Lead Vocal", 0.5),
])
def test_sends_in_logic_and_fl_wording(snapshot, request_text, track, value) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "set_send" and parsed["track"]["name"] == track
    assert parsed["desired_value"] == pytest.approx(value)


@pytest.mark.parametrize("request_text, new_name", [
    ("Rename the track 'Kick' to 'Kick (Original)'.", "Kick (Original)"),
    ("rename the kick to Big Kick.", "Big Kick"),  # the full stop used to end up in the name
    ("rename the kick to v1.2", "v1.2"),
])
def test_quotes_and_the_closing_full_stop_are_not_part_of_a_new_name(snapshot, request_text, new_name) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "rename_track" and parsed["desired_value"] == new_name
