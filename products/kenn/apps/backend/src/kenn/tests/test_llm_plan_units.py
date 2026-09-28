"""The planner may state volume in dB; KENN converts with the rule parser's mapping."""

import pytest

from kenn.core import volume_law
from kenn.core.live_command import validate_llm_plan

SNAPSHOT = {"tracks": [{"index": 0, "name": "Kick", "volume": 0.5},
                       {"index": 1, "name": "Bass", "volume": 0.9},
                       {"index": 2, "name": "Pad"}]}


def _fader(current: float, db: float) -> float:
    """Live's fader value after a dB change from a raw fader value."""
    return volume_law.db_to_raw(volume_law.raw_to_db(current) + db)


def _plan(**fields):
    return {"schema": "kenn.ableton_llm_plan.v1", "action": "set_volume", **fields}


def test_absolute_db_converts_like_the_rule_parser() -> None:
    checked = validate_llm_plan(_plan(track_index=0, track_name="Kick", unit="dB", value=-6.0), SNAPSHOT)
    assert checked["ok"]
    assert checked["plan"]["value"] == pytest.approx(volume_law.db_to_raw(-6), abs=1e-6)
    assert checked["plan"]["unit"] == "normalized" and checked["plan"]["relative"] is False


def test_relative_db_scales_the_current_snapshot_volume() -> None:
    checked = validate_llm_plan(_plan(track_index=0, track_name="Kick", unit="dB", value=3.0, relative=True),
                                SNAPSHOT)
    assert checked["ok"]
    assert checked["plan"]["value"] == pytest.approx(_fader(0.5, 3), abs=1e-6)


@pytest.mark.parametrize("fields, message", [
    ({"track_index": 1, "track_name": "Bass", "unit": "dB", "value": 3.0, "relative": True}, "range"),
    ({"track_index": 0, "track_name": "Kick", "unit": "dB", "value": 2.0}, "range"),
    ({"track_index": 2, "track_name": "Pad", "unit": "dB", "value": -3.0, "relative": True}, "current volume"),
    ({"track_index": 0, "track_name": "Kick", "unit": "%", "value": 50.0}, "normalized"),
])
def test_unsafe_or_unconvertible_volumes_are_rejected(fields, message) -> None:
    checked = validate_llm_plan(_plan(**fields), SNAPSHOT)
    assert not checked["ok"] and message in checked["error"]


def test_normalized_volume_is_unchanged() -> None:
    checked = validate_llm_plan(_plan(track_index=0, track_name="Kick", unit="normalized", value=0.7), SNAPSHOT)
    assert checked["ok"] and checked["plan"]["value"] == 0.7


def test_relative_normalized_volume_resolves_against_snapshot_volume() -> None:
    # Kick in SNAPSHOT has volume 0.5; +0.15 relative normalized should resolve to 0.65
    checked = validate_llm_plan(_plan(track_index=0, track_name="Kick", unit="normalized", value=0.15, relative=True), SNAPSHOT)
    assert checked["ok"] is True
    assert checked["plan"]["value"] == pytest.approx(0.65, abs=1e-6)
    assert checked["plan"]["relative"] is False

    # Negative relative volume past 0.0 should be rejected
    rejected = validate_llm_plan(_plan(track_index=0, track_name="Kick", unit="normalized", value=-0.6, relative=True), SNAPSHOT)
    assert rejected["ok"] is False
    assert "normalized range" in rejected["error"]


def test_recipe_steps_return_in_their_validated_converted_form() -> None:
    recipe = {"schema": "kenn.ableton_llm_plan.v1", "action": "recipe", "steps": [
        {"action": "set_mute", "track_index": 1, "track_name": "Bass", "value": True, "unit": "boolean"},
        {"action": "set_volume", "track_index": 0, "track_name": "Kick", "value": -6.0, "unit": "dB"},
    ]}
    checked = validate_llm_plan(recipe, SNAPSHOT)
    assert checked["ok"]
    volume = checked["plan"]["steps"][1]
    assert volume["unit"] == "normalized" and volume["value"] == pytest.approx(volume_law.db_to_raw(-6), abs=1e-6)
    assert "schema" not in volume and checked["plan"]["steps"][0]["value"] is True


@pytest.mark.parametrize("query, expected", [
    ("mute the bass", False), ("pan the bass left 20", False), ("solo the drum bus", False),
    ("cut 200 Hz on the bass by 3 dB, band 2A", True), ("boost band 2A on the bass eq by 2 dB", True),
    ("set the drum bus compressor threshold to -12 dB", True), ("what's on the bass EQ Eight?", True),
])
def test_parameter_evidence_only_for_device_requests(query, expected) -> None:
    from kenn.core.fake_live import FakeLiveBackend
    from kenn.core.live_action_service import LiveActionService
    from kenn.core.live_command import _llm_planner_snapshot
    from kenn.core.live_intent import parse_request

    fake = FakeLiveBackend()
    snapshot = fake.query_session_state()
    enriched = _llm_planner_snapshot(LiveActionService(fake), snapshot, parse_request(query, snapshot))
    assert ("planner_capabilities" in enriched) is expected


PAN_SNAPSHOT = {"tracks": [{"index": 0, "name": "Kick", "pan": 0.0}, {"index": 1, "name": "Synth", "pan": 0.9}],
                "return_tracks": [{"index": 0, "name": "A-Reverb"}]}


@pytest.mark.parametrize("fields, expected", [
    ({"value": -30.0, "unit": "%"}, -0.3),
    ({"value": 100.0, "unit": "percent"}, 1.0),
    ({"value": -20.0, "unit": "%", "relative": True, "track_index": 1, "track_name": "Synth"}, 0.7),
])
def test_pan_in_percent_converts_like_the_rule_parser(fields, expected) -> None:
    plan = {"schema": "kenn.ableton_llm_plan.v1", "action": "set_pan", "track_index": 0, "track_name": "Kick", **fields}
    checked = validate_llm_plan(plan, PAN_SNAPSHOT)
    assert checked["ok"], checked
    assert checked["plan"]["value"] == pytest.approx(expected) and checked["plan"]["unit"] == "normalized"
    assert checked["plan"]["relative"] is False


def test_a_percent_pan_past_hard_right_is_rejected() -> None:
    plan = {"schema": "kenn.ableton_llm_plan.v1", "action": "set_pan", "track_index": 1, "track_name": "Synth",
            "value": 20.0, "unit": "%", "relative": True}
    checked = validate_llm_plan(plan, PAN_SNAPSHOT)
    assert not checked["ok"] and "hard right" in checked["error"]


def test_a_send_in_percent_is_converted() -> None:
    plan = {"schema": "kenn.ableton_llm_plan.v1", "action": "set_send", "track_index": 0, "track_name": "Kick",
            "return_track_index": 0, "return_track_name": "A-Reverb", "value": 20.0, "unit": "%", "relative": False}
    checked = validate_llm_plan(plan, PAN_SNAPSHOT)
    assert checked["ok"], checked
    assert checked["plan"]["value"] == pytest.approx(0.2) and checked["plan"]["unit"] == "normalized"


def test_a_send_over_100_percent_is_rejected() -> None:
    plan = {"schema": "kenn.ableton_llm_plan.v1", "action": "set_send", "track_index": 0, "track_name": "Kick",
            "return_track_index": 0, "return_track_name": "A-Reverb", "value": 120.0, "unit": "%"}
    assert not validate_llm_plan(plan, PAN_SNAPSHOT)["ok"]


SONG_SNAPSHOT = {"tracks": [{"index": 0, "name": "Kick"}], "tempo": 120.0}


@pytest.mark.parametrize("fields, expected", [
    ({"action": "set_tempo", "value": 124, "unit": "bpm"}, 124.0),
    ({"action": "set_tempo", "value": -4, "unit": "bpm", "relative": True}, 116.0),
    ({"action": "set_time_signature", "value": "6/8"}, {"numerator": 6, "denominator": 8}),
])
def test_the_planner_can_state_tempo_and_signature_in_musical_units(fields, expected) -> None:
    checked = validate_llm_plan({"schema": "kenn.ableton_llm_plan.v1", **fields}, SONG_SNAPSHOT)
    assert checked["ok"], checked
    assert checked["plan"]["value"] == expected and checked["plan"]["relative"] is False


@pytest.mark.parametrize("fields", [
    {"action": "set_tempo", "value": 1200},
    {"action": "set_tempo", "value": 124, "track_index": 0, "track_name": "Kick"},
    {"action": "set_time_signature", "value": "4/3"},
    {"action": "set_time_signature", "value": 3},
])
def test_song_plans_outside_lives_limits_or_with_a_track_are_rejected(fields) -> None:
    assert not validate_llm_plan({"schema": "kenn.ableton_llm_plan.v1", **fields}, SONG_SNAPSHOT)["ok"]
