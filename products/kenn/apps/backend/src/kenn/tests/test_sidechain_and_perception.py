"""Unit tests for Live Perception and Sidechain/Carving Macro Planners."""

from unittest.mock import MagicMock
from kenn.core.live_control_planner import LiveControlPlanner
from kenn.core.sidechain_planner import (
    find_track_by_role,
    propose_kick_bass_sidechain,
    propose_vocal_carving_eq,
)


def test_find_track_by_role():
    session_tracks = [
        {"name": "Voc Lead Main"},
        {"name": "Kick In D112"},
        {"name": "Sub Bass 808"},
        {"name": "EGtr Rhythm R"},
    ]

    assert find_track_by_role(session_tracks, "vocal_lead") == 0
    assert find_track_by_role(session_tracks, "kick") == 1
    assert find_track_by_role(session_tracks, "sub_bass") == 2
    assert find_track_by_role(session_tracks, "guitar") == 3
    assert find_track_by_role(session_tracks, "snare") is None


def test_find_track_by_role_abstains_on_duplicate_or_ambiguous_identity():
    assert find_track_by_role([
        {"index": 3, "name": "Kick Main"},
        {"index": 9, "name": "Kick Parallel"},
    ], "kick") is None
    assert find_track_by_role([
        {"index": 4, "name": "Lead Vocal Guitar"},
    ], "vocal_lead") is None


def test_perceive_live_session():
    mock_osc = MagicMock()
    mock_osc.get_tracks.return_value = {
        "success": True,
        "tracks": [
            {"name": "Voc Lead"},
            {"name": "Kick Drum"},
            {"name": "Sub Bass"},
        ],
    }

    planner = LiveControlPlanner(osc_client=mock_osc)
    res = planner.perceive_live_session()

    assert res["ok"] is True
    perc = res["session_perception"]
    assert perc["track_count"] == 3
    assert perc["role_summary"]["vocal_lead"] == 1
    assert perc["role_summary"]["kick"] == 1
    assert len(perc["masking_warnings"]) >= 1


def test_propose_kick_bass_sidechain():
    mock_osc = MagicMock()
    mock_osc.get_device_parameters.return_value = {
        "success": True,
        "device_name": "Glue Compressor",
        "parameters": [
            {"name": "Threshold", "value": 0.0, "min": -40.0, "max": 0.0},
            {"name": "Ratio", "value": 2.0, "min": 1.0, "max": 10.0},
        ],
    }

    planner = LiveControlPlanner(osc_client=mock_osc)
    session_tracks = [
        {"name": "Kick Drum"},
        {"name": "Sub Bass 808", "devices": [{"index": 3, "name": "Glue Compressor"}]},
    ]

    res = propose_kick_bass_sidechain(planner, session_tracks)
    assert res["ok"] is True
    proposal = res["proposal"]
    assert proposal["schema"] == "kenn.batch_action_proposal.v1"
    assert len(proposal["proposals"]) == 2
    assert "confirmation_token" in proposal
    assert proposal["confidence"] == 0.58
    assert all(item["confidence"] == 0.58 for item in proposal["proposals"])
    assert "not configured or verified" in proposal["reason"]
    assert all("sidechain routing" in item["reason"].lower() for item in proposal["proposals"][:1])
    assert all(item["device_index"] == 3 for item in proposal["proposals"])
    assert mock_osc.get_device_parameters.call_args_list[0].args == (1, 3)


def test_propose_vocal_carving_eq():
    mock_osc = MagicMock()
    mock_osc.get_device_parameters.return_value = {
        "success": True,
        "device_name": "EQ Eight",
        "parameters": [
            {"name": "Band 3 Gain", "value": 0.0, "min": -15.0, "max": 15.0},
        ],
    }

    planner = LiveControlPlanner(osc_client=mock_osc)
    session_tracks = [
        {"name": "Voc Lead Main"},
        {"name": "EGtr Rhythm", "devices": [{"index": 5, "name": "EQ Eight"}]},
    ]

    res = propose_vocal_carving_eq(planner, session_tracks)
    assert res["ok"] is True
    proposal = res["proposal"]
    assert proposal["schema"] == "kenn.batch_action_proposal.v1"
    assert len(proposal["proposals"]) == 1
    assert "confirmation_token" in proposal
    assert proposal["confidence"] == 0.58
    assert proposal["proposals"][0]["confidence"] == 0.58
    assert proposal["proposals"][0]["device_index"] == 5
    mock_osc.get_device_parameters.assert_called_once_with(1, 5)


def test_role_recipe_refuses_parameter_match_on_wrong_device_family():
    mock_osc = MagicMock()
    mock_osc.get_device_parameters.return_value = {
        "success": True,
        "device_name": "Utility",
        "parameters": [
            {"name": "Threshold", "value": -12.0, "min": -60.0, "max": 0.0},
            {"name": "Ratio", "value": 2.0, "min": 1.0, "max": 10.0},
        ],
    }
    planner = LiveControlPlanner(osc_client=mock_osc)

    result = propose_kick_bass_sidechain(
        planner, [
            {"name": "Kick"},
            {"name": "Sub Bass", "devices": [{"index": 0, "name": "Compressor"}]},
        ],
    )

    assert result["ok"] is False
    assert "required device family 'compressor'" in result["error"]


def test_role_recipe_abstains_without_one_observed_target_device():
    planner = LiveControlPlanner(osc_client=MagicMock())

    missing = propose_kick_bass_sidechain(
        planner, [{"name": "Kick"}, {"name": "Sub Bass", "devices": []}],
    )
    duplicate = propose_kick_bass_sidechain(
        planner,
        [
            {"name": "Kick"},
            {
                "name": "Sub Bass",
                "devices": [
                    {"index": 1, "name": "Compressor"},
                    {"index": 4, "name": "Glue Compressor"},
                ],
            },
        ],
    )

    assert missing["ok"] is False
    assert duplicate["ok"] is False
    assert "uniquely identify an observed compressor" in missing["error"]
    assert "uniquely identify an observed compressor" in duplicate["error"]
    planner.osc_client.get_device_parameters.assert_not_called()
