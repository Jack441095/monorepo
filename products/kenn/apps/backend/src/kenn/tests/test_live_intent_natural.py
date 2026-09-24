"""Natural phrasing in the rule parser: nicknames, relative dB, and staying safe."""

import pytest

from kenn.core import volume_law
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_intent import parse_request

DEMO = {"status": "connected", "tracks": [
    {"index": 0, "name": "Kick", "volume": 0.5}, {"index": 1, "name": "Snare / Clap", "volume": 0.5},
    {"index": 2, "name": "Hi-Hats", "volume": 0.5}, {"index": 3, "name": "Drum Bus", "volume": 0.5},
    {"index": 4, "name": "Bass", "volume": 0.5}, {"index": 6, "name": "Lead Vocal", "volume": 0.5},
]}


def _fader(current: float, db: float) -> float:
    """Live's fader value after a dB change from a raw fader value."""
    return volume_law.db_to_raw(volume_law.raw_to_db(current) + db)


def resolved(query, snapshot=DEMO):
    parsed = parse_request(query, snapshot)
    ok = parsed.get("action") and not parsed.get("missing_fields") and not parsed.get("ambiguity")
    return parsed if ok else None


@pytest.mark.parametrize("query, track, db", [
    ("tuck the high hats back a couple of dbs", "Hi-Hats", -2.0),   # owner-written test command
    ("turn the hats down 2 dB", "Hi-Hats", -2.0),
    ("bring the bass up 3 dB", "Bass", 3.0),
    ("take 4 dB off the snare", "Snare / Clap", -4.0),
    ("drums down 3 dB", "Drum Bus", -3.0),
    ("vox down 1.5 dB", "Lead Vocal", -1.5),
])
def test_relative_db_on_nicknamed_tracks(query, track, db) -> None:
    parsed = resolved(query)
    assert parsed and parsed["action"] == "set_volume" and parsed["track"]["name"] == track
    assert parsed["requested_relative_db"] == db
    assert parsed["desired_value"] == pytest.approx(_fader(0.5, db))


@pytest.mark.parametrize("query", [
    "kick -6 dB",                       # no direction: to -6 or by 6?
    "hats down a touch",                # no amount
    "Vocals louder.",
    "turn the hats down 2 dB and up 1 dB",
    "solo the bass and turn it up 2 dB",  # two changes: never propose only the first
    "put some reverb on the snare",      # vague: how much, insert or send?
    "lead vocal up 20 dB",               # above 0 dB
])
def test_vague_conflicting_or_unsafe_requests_still_ask(query) -> None:
    assert resolved(query) is None


def test_a_qualifier_naming_another_track_is_not_matched_by_a_shared_word() -> None:
    only_backing = {"status": "connected", "tracks": [{"index": 0, "name": "Backing Vocal", "volume": 0.5}]}
    assert resolved("Turn down the Lead Vocal by 2 dB.", only_backing) is None
    assert resolved("turn down the lead vocal by 2 dB", only_backing) is None
    assert resolved("turn the vocal down 2 dB", only_backing)["track"]["name"] == "Backing Vocal"


def test_two_tracks_sharing_a_nickname_is_ambiguous() -> None:
    two_vocals = {"status": "connected", "tracks": [{"index": 0, "name": "Lead Vocal", "volume": 0.5},
                                                     {"index": 1, "name": "Backing Vocal", "volume": 0.5}]}
    assert resolved("vocal down 2 dB", two_vocals) is None


def test_existing_behaviour_is_unchanged() -> None:
    assert resolved("set Bass volume to -6 dB")["desired_value"] == pytest.approx(volume_law.db_to_raw(-6))
    assert resolved("mute the kick drum")["track"]["name"] == "Kick"
    assert resolved("add a reverb to the snare")["action"] == "insert_device"
    assert resolved("Append Hybrid Reverb to Lead Vocal and set Dry/Wet to 40%")["action"] == "insert_device_with_parameter"


def test_take_the_solo_or_mute_off_means_off() -> None:
    assert resolved("take the solo off the lead vocal")["desired_value"] is False
    assert resolved("take the mute off the kick")["desired_value"] is False
    assert resolved("solo the lead vocal")["desired_value"] is True


@pytest.mark.parametrize("query, track, value", [
    ("send the lead vocal to A-Reverb at 25%", "Lead Vocal", 0.25),
    ("set the kick send to B-Delay at 10%", "Kick", 0.10),
    ("send the vocal to the reverb at 30%", "Lead Vocal", 0.30),
])
def test_track_first_send_phrasing(query, track, value) -> None:
    parsed = resolved(query)
    assert parsed and parsed["action"] == "set_send" and parsed["track"]["name"] == track
    assert parsed["desired_value"] == pytest.approx(value)


def test_send_without_a_level_or_out_of_range_still_asks() -> None:
    assert resolved("send the vocal to the reverb") is None
    assert resolved("send the hats to B-Delay at 150%") is None


@pytest.mark.parametrize("query, track, db", [
    ("put the kick at minus 12 dB", "Kick", -12.0),
    ("set the snare to -10 dB", "Snare / Clap", -10.0),
])
def test_absolute_db_without_the_word_volume(query, track, db) -> None:
    parsed = resolved(query)
    assert parsed and parsed["action"] == "set_volume" and parsed["track"]["name"] == track
    assert parsed["desired_value"] == pytest.approx(volume_law.db_to_raw(db))


@pytest.mark.parametrize("query", [
    "set the snare compressor output to 3 dB",   # device wording keeps the device path
    "put the bass send to -6 dB",                # sends are not track volume
    "Bass to -9",                                 # no unit: still asks
])
def test_absolute_db_shape_does_not_take_device_send_or_unitless_requests(query) -> None:
    parsed = resolved(query)
    assert not parsed or parsed["action"] != "set_volume"


@pytest.mark.parametrize("query, track", [
    ("Select the Drum Bus", "Drum Bus"), ("focus the bass.", "Bass"), ("select the vocal", "Lead Vocal"),
])
def test_focus_a_track_by_name_without_the_word_track(query, track) -> None:
    parsed = resolved(query)
    assert parsed and parsed["action"] == "focus_track" and parsed["track"]["name"] == track


@pytest.mark.parametrize("query", ["focus the drum bus compressor", "focus on the low end", "select all clips"])
def test_bare_name_focus_needs_every_word_in_one_track_name(query) -> None:
    parsed = resolved(query)
    assert not parsed or parsed["action"] != "focus_track"


# The recorded demo set (all eight tracks, including Synth and FX Print).
FAKE_SET = FakeLiveBackend().query_session_state()


@pytest.mark.parametrize("query, action, track", [
    ("slap a compressor on the snare", "insert_device", "Snare / Clap"),
    ("throw an echo on the synth", "insert_device", "Synth"),
    ("new audio track", "create_audio_track", None),
    ("make a new return channel", "create_return_track", None),
    ("start the set", "transport_play", None),
    ("place a locator named Drop", "add_locator", None),
    ("sorry, solo the bass not the kick", "set_solo", "Bass"),
    ("call track 3 Tops", "rename_track", "Hi-Hats"),
    ("nuke the snare", "set_mute", "Snare / Clap"),
    ("take the synth out of the mix", "set_mute", "Synth"),
    ("the bass on its own", "set_solo", "Bass"),
    ("only the kick", "set_solo", "Kick"),
    ("tuck the synth to -8 dB", "set_volume", "Synth"),
    ("snare at -10 dB", "set_volume", "Snare / Clap"),
    ("bass hard left", "set_pan", "Bass"),
    ("synth right 30", "set_pan", "Synth"),
    ("nudge track 6 15 percent to the right", "set_pan", "Synth"),
    ("go to the snare", "focus_track", "Snare / Clap"),
    ("show me the third channel", "focus_track", "Hi-Hats"),
    ("take me to the fifth channel", "focus_track", "Bass"),
])
def test_everyday_phrasings(query, action, track) -> None:
    parsed = resolved(query, FAKE_SET)
    assert parsed and parsed["action"] == action
    if track:
        assert parsed["track"]["name"] == track


@pytest.mark.parametrize("query", [
    "drop the reverb send on the snare by 3 dB",  # a send change, not an insert
    "kill playback",                              # transport, not a mute
    "leave the vocal alone",                      # not a solo
    "the left side sounds thin",                  # not a pan
    "how do I kill the reverb tail?",             # a question
    "jump to the bass compressor",                # device focus by name is not supported yet: ask
])
def test_everyday_phrasings_that_must_not_act(query) -> None:
    assert resolved(query, FAKE_SET) is None


def test_pan_amounts_in_terse_forms_are_percent() -> None:
    assert resolved("synth right 30", FAKE_SET)["desired_value"] == pytest.approx(0.3)
    assert resolved("bass hard left", FAKE_SET)["desired_value"] == -1.0


@pytest.mark.parametrize("query, track, device", [
    ("show me the bass eq", "Bass", "EQ Eight"),
    ("open the compressor on the vocal", "Lead Vocal", "Compressor"),
    ("focus the drum bus compressor", "Drum Bus", "Compressor"),
    ("show me the vox comp", "Lead Vocal", "Compressor"),
    ("open the drums compressor", "Drum Bus", "Compressor"),
])
def test_focus_a_device_by_name(query, track, device) -> None:
    parsed = resolved(query, FAKE_SET)
    assert parsed and parsed["action"] == "focus_device"
    assert parsed["track"]["name"] == track and parsed["device"]["name"] == device


@pytest.mark.parametrize("query", [
    "focus the drum bus compressor ratio",  # an extra word: not just a focus
    "jump to the bass compressor",          # the bass has no compressor
    "open the eq on the kick",              # the kick has no EQ
])
def test_device_focus_by_name_needs_a_real_unique_device(query) -> None:
    parsed = resolved(query, FAKE_SET)
    assert not parsed or parsed["action"] != "focus_device"


@pytest.mark.parametrize("query, track, value", [
    ("synth to the delay at 20 percent", "Synth", 0.2),
    ("put the snare to the reverb at 15%", "Snare / Clap", 0.15),
])
def test_send_to_a_named_return_without_the_word_send(query, track, value) -> None:
    parsed = resolved(query, FAKE_SET)
    assert parsed and parsed["action"] == "set_send" and parsed["track"]["name"] == track
    assert parsed["desired_value"] == pytest.approx(value)


@pytest.mark.parametrize("query", ["bass to the chorus at 20%", "set eq band 2 to 200 hz at 3 db", "kick to the delay at 20 dB"])
def test_track_to_return_needs_a_real_return_and_a_percentage(query) -> None:
    parsed = resolved(query, FAKE_SET)
    assert not parsed or parsed["action"] != "set_send"


@pytest.mark.parametrize("query, steps", [
    ("mute the hats and the snare", [("set_mute", "Hi-Hats"), ("set_mute", "Snare / Clap")]),
    ("solo the bass and turn it up 2 dB", [("set_solo", "Bass"), ("set_volume", "Bass")]),
    ("mute the kick and solo the bass", [("set_mute", "Kick"), ("set_solo", "Bass")]),
    ("Solo the Drum Bus, then park the Vocal twenty percent right.", [("set_solo", "Drum Bus"), ("set_pan", "Lead Vocal")]),
])
def test_two_part_requests_become_recipes(query, steps) -> None:
    from kenn.core.live_intent import parse_natural_recipe

    recipe = parse_natural_recipe(query, FAKE_SET)
    assert recipe and not recipe.get("ambiguity")
    assert [(step["action"], step["track_name"]) for step in recipe["steps"]] == steps


@pytest.mark.parametrize("query", [
    "pan the synth left and the FX print right",               # how far? each half must be clear
    "set eq frequency to 200 hz and gain to 3 dB on track 5",  # one EQ command, not two
    "mute the kick and make it louder",                         # "louder" by how much?
    "rock and roll",
])
def test_plain_and_needs_two_clear_halves(query) -> None:
    from kenn.core.live_intent import parse_natural_recipe

    assert parse_natural_recipe(query, FAKE_SET) is None


@pytest.mark.parametrize("query, action, phrase", [
    ("kick -3 dB", "set_volume", "Do you want Kick at -3 dB, or 3 dB quieter"),
    ("make the bass louder", "set_volume", "By how much?"),
    ("turn the vocal down", "set_volume", "turn Lead Vocal down 2 dB"),
    ("pan the synth left", "set_pan", "How far left?"),
])
def test_a_missing_value_gets_a_precise_question(query, action, phrase) -> None:
    parsed = parse_request(query, FAKE_SET)
    assert parsed["action"] == action and parsed["missing_fields"]
    assert any(phrase in text for text in parsed["ambiguity"])


@pytest.mark.parametrize("query, track, db", [
    ("FX print to -12 dB", "FX Print", -12.0),
    ("kick to minus 6 dB", "Kick", -6.0),
    ("the bass at -9 dB", "Bass", -9.0),
    ("track 3 to -8 dB", "Hi-Hats", -8.0),
])
def test_terse_track_to_level_is_an_absolute_volume(query, track, db) -> None:
    parsed = parse_request(query, FAKE_SET)
    assert parsed["action"] == "set_volume" and not parsed["missing_fields"]
    assert parsed["track"]["name"] == track
    assert parsed["desired_value"] == pytest.approx(volume_law.db_to_raw(db), abs=1e-4)


@pytest.mark.parametrize("query", [
    "Bass to -9",                            # no unit said: still a question
    "synth send to -6 dB",                   # a send, not the fader
    "send the synth to the delay at -6 dB",  # a send level
    "master to -3 dB",                       # master level is never set from chat
])
def test_terse_level_rewrite_leaves_other_requests_alone(query) -> None:
    parsed = parse_request(query, FAKE_SET)
    assert parsed["action"] != "set_volume" or parsed["missing_fields"]
