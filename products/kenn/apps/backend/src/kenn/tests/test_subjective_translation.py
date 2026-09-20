"""Tests for SubjectiveTranslator and deterministic producer metaphor translation."""

from unittest.mock import MagicMock, patch
import pytest

from kenn.core.live_command import handle_command
from kenn.core.subjective_translator import SubjectiveTranslator


@pytest.fixture
def mock_session_snapshot():
    return {
        "status": "connected",
        "tracks": [
            {"index": 0, "name": "Kick", "volume": 0.85, "pan": 0.0, "panning": 0.0, "devices": []},
            {"index": 1, "name": "Sub Bass", "volume": 0.80, "pan": 0.25, "panning": 0.25, "devices": []},
            {"index": 2, "name": "Lead Vocal", "volume": 0.72, "pan": 0.0, "panning": 0.0, "devices": []},
            {"index": 3, "name": "Supersaw Synth", "volume": 0.78, "pan": 0.0, "panning": 0.0, "devices": [{"name": "EQ Eight", "class_name": "Eq8", "parameters": []}]},
            {"index": 4, "name": "Pads", "volume": 0.82, "pan": 0.0, "panning": 0.0, "devices": []},
            {"index": 5, "name": "Drum Bus", "volume": 0.80, "pan": 0.0, "panning": 0.0, "devices": []},
        ],
    }


def test_can_translate_subjective_phrases():
    assert SubjectiveTranslator.can_translate("Make the vocal cut through") is True
    assert SubjectiveTranslator.can_translate("Help the vocals cut through the mix") is True
    assert SubjectiveTranslator.can_translate("Fix low-end mud") is True
    assert SubjectiveTranslator.can_translate("Clean up the muddy low mids") is True
    assert SubjectiveTranslator.can_translate("Glue the drum bus") is True
    assert SubjectiveTranslator.can_translate("Compress the drum bus for punch") is True
    assert SubjectiveTranslator.can_translate("What is on track 2?") is False
    assert SubjectiveTranslator.can_translate("Mute track 1") is False


def test_vocal_cut_through_formulates_unmasking_recipe(mock_session_snapshot):
    with patch("kenn.core.live_action_service.LiveActionService.snapshot", return_value=mock_session_snapshot):
        res = handle_command("Make the vocal cut through", session_id="test-sess")

    assert res["status"] == "confirmation_required"
    assert res["confirmation_required"] is True
    assert res["proposal"]["schema"] == "kenn.ableton_recipe_proposal.v1"
    steps = res["proposal"]["steps"]
    assert len(steps) == 2

    # Step 1: trim competing synth fader (down by <= 3.0 dB)
    assert steps[0]["track_name"] == "Supersaw Synth"
    assert steps[0]["action"] == "set_volume"
    assert steps[0]["after"] < 0.78
    assert abs(steps[0]["after"] - steps[0]["before"]) <= 0.20  # strict gain clamping <= 3.0 dB

    # Step 2: boost vocal presence fader (up by <= 3.0 dB)
    assert steps[1]["track_name"] == "Lead Vocal"
    assert steps[1]["action"] == "set_volume"
    assert steps[1]["after"] > 0.72
    assert abs(steps[1]["after"] - steps[1]["before"]) <= 0.20


def test_vocal_cut_through_missing_vocal_prompts_clarification():
    no_vocal_snapshot = {
        "status": "connected",
        "tracks": [
            {"index": 0, "name": "Kick", "volume": 0.85, "panning": 0.0, "devices": []},
            {"index": 1, "name": "Bass", "volume": 0.80, "panning": 0.0, "devices": []},
        ],
    }
    with patch("kenn.core.live_action_service.LiveActionService.snapshot", return_value=no_vocal_snapshot):
        res = handle_command("Make the vocal cut through", session_id="test-sess")

    assert res["status"] == "clarification_required"
    assert "vocal track" in res["answer"].lower()


def test_fix_low_end_mud_centers_sub_and_trims_rumble(mock_session_snapshot):
    with patch("kenn.core.live_action_service.LiveActionService.snapshot", return_value=mock_session_snapshot):
        res = handle_command("Fix low-end mud", session_id="test-sess")

    assert res["status"] == "confirmation_required"
    assert res["confirmation_required"] is True
    assert res["proposal"]["schema"] == "kenn.ableton_recipe_proposal.v1"
    steps = res["proposal"]["steps"]
    assert len(steps) >= 1

    # Sub bass pan centered to 0.0
    sub_step = next((s for s in steps if s["track_name"] == "Sub Bass" and s["action"] == "set_pan"), None)
    assert sub_step is not None
    assert sub_step["after"] == 0.0

    # Hot non-bass clutter trimmed within 3 dB
    trim_step = next((s for s in steps if s["action"] == "set_volume"), None)
    if trim_step is not None:
        assert abs(trim_step["after"] - trim_step["before"]) <= 0.20


def test_glue_drum_bus_proposes_glue_compressor_insertion(mock_session_snapshot):
    with patch("kenn.core.live_action_service.LiveActionService.snapshot", return_value=mock_session_snapshot):
        res = handle_command("Glue the drum bus", session_id="test-sess")

    assert res["status"] == "confirmation_required"
    assert res["confirmation_required"] is True
    assert res["proposal"]["schema"] == "kenn.ableton_device_insertion_proposal.v1"
    assert res["proposal"]["device_name"] == "Glue Compressor"
    assert res["proposal"]["track_name"] == "Drum Bus"
    assert "Glue Compressor" in res["answer"]


def test_glue_drum_bus_already_present_advises_parameters():
    already_glued_snapshot = {
        "status": "connected",
        "tracks": [
            {
                "index": 0,
                "name": "Drum Bus",
                "volume": 0.80,
                "panning": 0.0,
                "devices": [{"name": "Glue Compressor", "class_name": "GlueCompressor", "parameters": []}],
            },
        ],
    }
    with patch("kenn.core.live_action_service.LiveActionService.snapshot", return_value=already_glued_snapshot):
        res = handle_command("Glue the drum bus", session_id="test-sess")

    assert res["status"] == "planned"
    assert "already has a Glue Compressor loaded" in res["answer"]
    assert "Attack=30ms" in res["answer"]


def test_vocal_cut_through_recipe_undo_formulation(mock_session_snapshot):
    with patch("kenn.core.live_action_service.LiveActionService.snapshot", return_value=mock_session_snapshot):
        res = handle_command("Make the vocal cut through", session_id="test-sess")

    proposal = res["proposal"]
    token = proposal.get("confirmation_token", "")
    assert token != ""

    from kenn.core.live_recipe import LiveRecipeService
    service = MagicMock()
    service.propose_track_action.side_effect = lambda action, track_index, track_name, value, session_id: {
        "ok": True,
        "proposal": {"action": action, "track_index": track_index, "track_name": track_name, "after": value},
    }
    recipe_service = LiveRecipeService(service)

    # Test that reverse recipe steps are formulated properly for undo
    mock_receipt = {
        "schema": "kenn.ableton_recipe_receipt.v1",
        "receipt_id": "receipt-test-123",
        "status": "applied",
        "verified": True,
        "step_receipts": [
            {
                "action": "set_volume",
                "target": {"track_index": 3, "track_name": "Supersaw Synth"},
                "before": 0.78,
                "after": 0.71,
            },
            {
                "action": "set_volume",
                "target": {"track_index": 2, "track_name": "Lead Vocal"},
                "before": 0.72,
                "after": 0.77,
            },
        ],
        "completed_steps": 2,
    }
    undo_res = recipe_service.propose_undo(mock_receipt, session_id="test-sess")
    assert undo_res["ok"] is True
    assert undo_res["proposal"]["schema"] == "kenn.ableton_recipe_proposal.v1"
    undo_steps = undo_res["proposal"]["steps"]
    assert len(undo_steps) == 2
    # Reverse order: step 1 restores Lead Vocal to 0.72, step 2 restores Synth to 0.78
    assert undo_steps[0]["track_name"] == "Lead Vocal"
    assert undo_steps[0]["after"] == 0.72
    assert undo_steps[1]["track_name"] == "Supersaw Synth"
    assert undo_steps[1]["after"] == 0.78

