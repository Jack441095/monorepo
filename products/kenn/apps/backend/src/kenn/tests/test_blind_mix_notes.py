"""Ways of writing a mixer change that the 30 Sept blind round 9 check
(tooling/data/natural_blind_round9_mixnotes_2026-09-30.jsonl) found.

Two of these are wrong plans the round turned up, not misses, so each test says what the producer
would have got by pressing Apply.
"""

from __future__ import annotations

import pytest

from kenn.core import volume_law
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_intent import parse_request


@pytest.fixture(scope="module")
def snapshot():
    return FakeLiveBackend().query_session_state()


def resolved(request_text, snapshot):
    parsed = parse_request(request_text, snapshot)
    return parsed if parsed.get("action") and not parsed.get("missing_fields") else None


@pytest.mark.parametrize("request_text, track", [
    ("Lead Vocal off solo", "Lead Vocal"),      # a mix note says the state, not the verb
    ("Lead Vocal solo off", "Lead Vocal"),
    ("hats out of solo", "Hi-Hats"),
    ("the bass is not soloed", "Bass"),
])
def test_taking_a_track_off_solo_never_solos_it(request_text, track, snapshot) -> None:
    # Round 9 first run: "Lead Vocal off solo" soloed it. The write lands, reads back clean and is
    # journalled as verified, so nothing downstream can see that it is the opposite of the request.
    parsed = resolved(request_text, snapshot)
    assert parsed and parsed["action"] == "set_solo" and parsed["track"]["name"] == track
    assert parsed["desired_value"] is False, parsed


@pytest.mark.parametrize("request_text", [
    "mute the Kick, mute the hats",
    "mute the kick, mute the hats and solo the Bass",
])
def test_a_comma_list_that_repeats_the_verb_never_drops_a_request(request_text, snapshot) -> None:
    # Round 9 first run: "mute the Kick, mute the hats and solo the Bass" proposed muting the Kick
    # and soloing the Bass, and never mentioned the hats. A producer pressing Apply got two of the
    # three requests with nothing to tell them so.
    parsed = parse_request(request_text, snapshot)
    missing = parsed.get("missing_fields") or []
    assert "single_action" in missing or parsed.get("action") != "set_mute", parsed


def test_two_of_the_same_change_in_a_comma_list_is_one_confirmable_recipe(snapshot) -> None:
    from kenn.core.live_intent import parse_natural_recipe

    recipe = parse_natural_recipe("mute the Kick, mute the hats", snapshot)
    assert recipe and recipe["action"] == "recipe", recipe
    muted = [step["track_name"] for step in recipe["steps"] if step["action"] == "set_mute"]
    assert muted == ["Kick", "Hi-Hats"], recipe


@pytest.mark.parametrize("request_text, track, db", [
    ("KICK FADER: -18 dB", "Kick", -18.0),          # the colon separates the note's two columns
    ("**Bass**: -12 dB", "Bass", -12.0),
    ("Drum Bus = -17 dB", "Drum Bus", -17.0),
    ("`Snare / Clap`: -16 dB", "Snare / Clap", -16.0),
    ("FX Print: -6 dB", "FX Print", -6.0),
    ("- Synth: -20 dB", "Synth", -20.0),
    ("TODO: FX Print to -6 dB", "FX Print", -6.0),
])
def test_a_pasted_note_with_a_target_after_the_separator_is_a_fader_level(request_text, track, db, snapshot) -> None:
    # Round 9 first run: eight of these asked "at -18 dB, or 18 dB quieter?". The ambiguity is only
    # real for a bare number; a dB value in a labelled column states where the fader should end up.
    parsed = resolved(request_text, snapshot)
    assert parsed and parsed["action"] == "set_volume" and parsed["track"]["name"] == track, parsed
    assert parsed["desired_value"] == pytest.approx(volume_law.db_to_raw(db), abs=0.005)


@pytest.mark.parametrize("request_text", ["SNARE / CLAP — 16 dB", "KICK - 18 dB"])
def test_a_positive_bare_decibel_next_to_a_track_name_still_asks(request_text, snapshot) -> None:
    # The same level-or-change ambiguity the 25 Sept rules pinned ("kick -3 dB"): only a negative
    # bare number is stated to be dB, so the notes rewrite must not read these as targets.
    assert resolved(request_text, snapshot) is None


@pytest.mark.parametrize("request_text, track, side", [
    ("Drum Bus: centre", "Drum Bus", 0.0),
    ("KICK — 30% RIGHT", "Kick", 0.3),
])
def test_a_pasted_pan_note_reaches_the_panner(request_text, track, side, snapshot) -> None:
    parsed = resolved(request_text, snapshot)
    assert parsed and parsed["action"] == "set_pan" and parsed["track"]["name"] == track, parsed
    assert parsed["desired_value"] == pytest.approx(side)


@pytest.mark.parametrize("request_text, track, send", [
    ("HATS → A-Reverb 30%", "Hi-Hats", 0.30),
    ("Synth -> B-Delay 40%", "Synth", 0.40),
    ("Lead Vocal send into A-Reverb: 25%", "Lead Vocal", 0.25),
])
def test_an_arrow_in_a_note_is_a_send_amount_not_a_track_number(request_text, track, send, snapshot) -> None:
    parsed = resolved(request_text, snapshot)
    assert parsed and parsed["action"] == "set_send" and parsed["track"]["name"] == track, parsed
    assert parsed["desired_value"] == pytest.approx(send)


@pytest.mark.parametrize("request_text, locator", [
    ("MARKER: Pre-drop", "Pre-drop"),
    ("Cue point: Chorus 3", "Chorus 3"),
])
def test_a_marker_heading_with_a_colon_is_still_a_locator_name(request_text, locator, snapshot) -> None:
    parsed = resolved(request_text, snapshot)
    assert parsed and parsed["action"] == "add_locator" and parsed["locator_name"] == locator, parsed


def test_a_section_heading_is_the_verb_it_replaces(snapshot) -> None:
    for request_text, action in [("PLAYBACK: start", "transport_play"), ("TEMPO: 128", "set_tempo"),
                                 ("NEW MIDI TRACK: Keys", "create_midi_track"), ("SHOW: the Bass", "focus_track"),
                                 ("RENAME: FX Print -> Bounce", "rename_track")]:
        parsed = resolved(request_text, snapshot)
        assert parsed and parsed["action"] == action, (request_text, parsed)
    assert resolved("SHOW: the Bass", snapshot)["track"]["name"] == "Bass"
    assert resolved("RENAME: FX Print -> Bounce", snapshot)["desired_value"] == "Bounce"


def test_the_notes_rewrite_leaves_a_line_it_does_not_know_to_ask(snapshot) -> None:
    # A pasted block of several revisions names more than one thing, so the two-things rule holds and
    # KENN asks instead of picking the first line.
    block = "- Kick: -18 dB\n- Hats: -20 dB\n- Bass: -12 dB"
    assert resolved(block, snapshot) is None
    assert resolved("Bass EQ: band 2A -3 dB", snapshot) is None  # a band gain still needs a frequency