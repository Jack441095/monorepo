"""The planner may state volume in dB; KENN converts with the rule parser's mapping."""

import pytest

from kenn.core.live_command import validate_llm_plan

SNAPSHOT = {"tracks": [{"index": 0, "name": "Kick", "volume": 0.5},
                       {"index": 1, "name": "Bass", "volume": 0.9},
                       {"index": 2, "name": "Pad"}]}


def _plan(**fields):
    return {"schema": "kenn.ableton_llm_plan.v1", "action": "set_volume", **fields}


def test_absolute_db_converts_like_the_rule_parser() -> None:
    checked = validate_llm_plan(_plan(track_index=0, track_name="Kick", unit="dB", value=-6.0), SNAPSHOT)
    assert checked["ok"]
    assert checked["plan"]["value"] == pytest.approx(10 ** (-6 / 20), abs=1e-6)
    assert checked["plan"]["unit"] == "normalized" and checked["plan"]["relative"] is False


def test_relative_db_scales_the_current_snapshot_volume() -> None:
    checked = validate_llm_plan(_plan(track_index=0, track_name="Kick", unit="dB", value=3.0, relative=True),
                                SNAPSHOT)
    assert checked["ok"]
    assert checked["plan"]["value"] == pytest.approx(0.5 * 10 ** (3 / 20), abs=1e-6)


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


def test_recipe_steps_return_in_their_validated_converted_form() -> None:
    recipe = {"schema": "kenn.ableton_llm_plan.v1", "action": "recipe", "steps": [
        {"action": "set_mute", "track_index": 1, "track_name": "Bass", "value": True, "unit": "boolean"},
        {"action": "set_volume", "track_index": 0, "track_name": "Kick", "value": -6.0, "unit": "dB"},
    ]}
    checked = validate_llm_plan(recipe, SNAPSHOT)
    assert checked["ok"]
    volume = checked["plan"]["steps"][1]
    assert volume["unit"] == "normalized" and volume["value"] == pytest.approx(10 ** (-6 / 20), abs=1e-6)
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
