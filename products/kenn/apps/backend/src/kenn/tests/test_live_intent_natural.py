"""Natural phrasing in the rule parser: nicknames, relative dB, and staying safe."""

import pytest

from kenn.core import volume_law
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
