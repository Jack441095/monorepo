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


# Typed in a hurry (the phone-shorthand phrasing set, 27 Sept 2026). These used to get "which mix problem?" from chat.
@pytest.mark.parametrize("request_text, action, track, value", [
    ("kik 2db down", "set_volume", "Kick", volume_law.db_to_raw(-16)),
    ("solo kik", "set_solo", "Kick", True),
    ("mute the bus", "set_mute", "Drum Bus", True),
    ("hats 20 left", "set_pan", "Hi-Hats", -0.2),
    ("pan the hats 20 left", "set_pan", "Hi-Hats", -0.2),
    ("snare 0.5 left", "set_pan", "Snare / Clap", -0.5),
    ("hats 20L", "set_pan", "Hi-Hats", -0.4),  # Live's panner reads 50L to 50R
    ("bass eq 200hz cut 3db", "set_eq_band_gain", "Bass", None),
])
def test_shorthand_means_the_plain_command(snapshot, request_text, action, track, value) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == action and parsed["track"]["name"] == track and not parsed["missing_fields"]
    if isinstance(value, bool):
        assert parsed["desired_value"] is value
    elif value is not None:
        assert parsed["desired_value"] == pytest.approx(value, abs=0.005)


@pytest.mark.parametrize("request_text", ["bus comp thresh -10", "teh bus comp thresh -10", "comp thresh -10 on bus"])
def test_compressor_shorthand_reaches_the_drum_bus_compressor(snapshot, request_text) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == "set_device_parameter" and parsed["track"]["name"] == "Drum Bus"


def test_a_bare_signed_number_asks_whether_it_is_a_level_or_a_change(snapshot) -> None:
    parsed = parse_request("kik -3", snapshot)
    assert parsed["track"]["name"] == "Kick" and parsed["missing_fields"] == ["absolute_or_relative"]


@pytest.mark.parametrize("request_text, missing, words", [
    ("comp thresh -10", "which_track", "Drum Bus and Lead Vocal"),
    ("delay 30%", "which_track", "Which track's delay send"),
    ("verb up a hair", "which_track", "Which track's reverb send"),
    ("turn the delay send on the bass down 5 dB", "amount", "What level should Bass's delay send be"),
    ("bass eq 100hz cut", "amount", "cut 100 Hz on the bass by 3 dB"),
])
def test_shorthand_missing_one_thing_asks_for_exactly_that(snapshot, request_text, missing, words) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["missing_fields"] == [missing] and words in parsed["ambiguity"][0]
    assert not parsed["confirmation_required"]


def test_a_new_name_keeps_the_spelling_the_user_typed(snapshot) -> None:
    assert parse_request("rename the kick to kik", snapshot)["desired_value"] == "kik"


def test_the_article_is_not_read_as_a_track(snapshot) -> None:
    # "set the compressor threshold to -10 dB" became "set the the compressor..." and lost the question.
    assert parse_request("set the compressor threshold to -10 dB", snapshot)["missing_fields"] == ["which_track"]


@pytest.mark.parametrize("request_text, action, track", [
    ("auto filter on synth", "insert_device", "Synth"),
    ("bass eq low cut 40hz", "set_device_parameter", "Bass"),
])
def test_device_shorthand_names_the_device_and_the_track(snapshot, request_text, action, track) -> None:
    parsed = parse_request(request_text, snapshot)
    assert parsed["action"] == action and parsed["track"]["name"] == track


def test_a_vague_shorthand_level_asks_how_much(snapshot) -> None:
    parsed = parse_request("bass a bit lower", snapshot)
    assert parsed["action"] == "set_volume" and parsed["missing_fields"] == ["amount"]


def test_describing_the_mix_is_not_shorthand_for_a_change(snapshot) -> None:
    assert parse_request("the kick is lower", snapshot)["action"] is None


# Long chat messages with the request buried in them (round 8 phrasing set, 27 Sept 2026): these got mixing notes.
@pytest.mark.parametrize("message, action, track", [
    ("Hey, the kick is kinda loud but the snare is getting lost in the mix. I think the hi-hats are too bright, maybe "
     "they need some EQ. Oh, and the bass is fighting the kick a bit, can you lower the bass by 2db?", "set_volume", "Bass"),
    ("The hi-hats are too bright, maybe I should add a low cut. Also, the delay is way too long. Anyway, can you lower "
     "the hi-hats by 1db?", "set_volume", "Hi-Hats"),
    ("The bass is fighting the kick. Drop the bass 2 dB.", "set_volume", "Bass"),
])
def test_the_request_is_found_inside_a_longer_message(snapshot, message, action, track) -> None:
    parsed = parse_request(message, snapshot)
    assert parsed["action"] == action and parsed["track"]["name"] == track and not parsed["missing_fields"]


def test_it_in_a_buried_request_is_the_track_just_named(snapshot) -> None:
    parsed = parse_request("The tempo feels fine. The kick is a bit too loud, can you lower it by 2 dB? Also the reverb "
                           "on the vocal is too much.", snapshot)
    assert parsed["action"] == "set_volume" and parsed["track"]["name"] == "Kick"


def test_two_buried_requests_ask_which_first(snapshot) -> None:
    parsed = parse_request("Can you mute the kick? And could you solo the bass please.", snapshot)
    assert parsed["missing_fields"] == ["which_change"] and not parsed["confirmation_required"]


def test_thinking_aloud_is_not_a_buried_request(snapshot) -> None:
    parsed = parse_request("The synth is way too bright. Maybe we can bring it down a little? Or maybe the EQ is too "
                           "harsh?", snapshot)
    assert parsed["action"] is None


@pytest.mark.parametrize("message", ["Mute the kick. No wait, the snare.", "mute the kick no wait the snare"])
def test_a_correction_after_a_full_stop_changes_the_target(snapshot, message) -> None:
    # Both muted the Kick before 27 Sept 2026; only "mute the kick, no wait, the snare" worked.
    assert parse_request(message, snapshot)["track"]["name"] == "Snare / Clap"


def test_a_taken_back_request_is_not_revived_from_its_first_sentence(snapshot) -> None:
    assert parse_request("mute the drum bus? nah", snapshot)["missing_fields"] == ["negated"]


@pytest.mark.parametrize("message", [
    "The delay on the synth is just right, but the bass is still fighting the kick, so let's lower it by 1.5db.",
    "I'm getting a little tired of the reverb on the vocal. Can you turn it off for a moment?",
])
def test_it_is_not_guessed_when_two_tracks_or_an_effect_came_before(snapshot, message) -> None:
    # The first lowered the Kick and the second muted the Lead Vocal while the new rule was being written (27 Sept 2026).
    parsed = parse_request(message, snapshot)
    assert parsed["track"] is None and not parsed["confirmation_required"]
    assert parsed["missing_fields"] in (["which_track"], ["action"])


def test_can_you_maybe_is_still_a_request(snapshot) -> None:
    parsed = parse_request("The hats are too loud. I think the drum bus compressor is too aggressive. Can you maybe "
                           "lower the hi-hats by 1db?", snapshot)
    assert parsed["action"] == "set_volume" and parsed["track"]["name"] == "Hi-Hats"


def test_a_musing_amount_does_not_leak_into_the_request(snapshot) -> None:
    # "Maybe -5 dB? … Can you just lower the synth a bit?" proposed -5 dB (27 Sept 2026); the request has no amount.
    parsed = parse_request("I think I need to bring the synth down. Maybe -5 dB? Or should I just lower the fader? "
                           "Can you just lower the synth a bit?", snapshot)
    assert parsed["action"] == "set_volume" and parsed["missing_fields"] == ["amount"]


def test_a_level_described_earlier_is_not_the_target(snapshot) -> None:
    # "…the FX Print is at 0 dB … can you bring it down?" answered "already at 0 dB" (27 Sept 2026).
    parsed = parse_request("Should I lower it? Wait, the FX Print is at 0 dB. Maybe it's meant to be loud? I'm not sure. "
                           "Anyway, can you bring it down?", snapshot)
    assert parsed["missing_fields"] == ["which_track"]


def test_it_names_the_track_for_a_rename(snapshot) -> None:
    parsed = parse_request("Why is the bass track named Bass? Can you rename it to Bass Line?", snapshot)
    assert parsed["action"] == "rename_track" and parsed["track"]["name"] == "Bass" and parsed["desired_value"] == "Bass Line"
