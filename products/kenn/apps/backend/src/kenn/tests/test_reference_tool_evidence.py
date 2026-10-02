"""Reference tools cannot turn a missing measurement into an EQ proposal."""

from types import SimpleNamespace

import pytest

from kenn.autonomous_agent import KennAutonomousAgent, tool_match_reference_track


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"session_spectrum": [], "reference_spectrum": []},
        {"session_spectrum": [-20.0] * 40},
        {"reference_spectrum": [-20.0] * 40},
        {"session_spectrum": [-20.0] * 40, "reference_spectrum": [None] * 40},
    ],
)
def test_registered_reference_tool_refuses_missing_or_invalid_evidence(kwargs):
    # The tool had its own fake-spectrum fallback even after the matcher was called.
    agent = KennAutonomousAgent()
    result = agent.tools["match_reference_track"].execute(**kwargs)
    assert result["available"] is False
    assert result["rms_spectral_delta_db"] is None
    assert result["delta_curve"] == []
    assert result["eq_recipe"] == []


def test_reference_tool_preserves_supplied_spectral_difference_and_request_isolation():
    session = [-20.0] * 40
    reference = [-20.0] * 40
    reference[30] = -17.0
    measured = tool_match_reference_track(reference, session, "Measured fixture")
    assert measured["available"] is True
    assert measured["reference_name"] == "Measured fixture"
    assert measured["rms_spectral_delta_db"] > 0.0
    assert measured["delta_curve"][30]["delta_db"] == 3.0
    missing = tool_match_reference_track()
    assert missing["available"] is False
    assert missing["delta_curve"] == []
    assert measured["delta_curve"][30]["delta_db"] == 3.0


def test_reference_voice_intent_requests_measurements_before_running_its_tool():
    from kenn.speech.voice_copilot import VoiceCopilot

    # Voice supplied an action but falsely announced extraction from a commercial master.
    intent = VoiceCopilot().classify_intent("KENN, match the reference")
    assert intent.intent_type == "MATCH_REFERENCE"
    assert "needs measured session and reference spectra" in intent.response_speech.lower()
    command = intent.execution_command
    assert command == {"action": "match_reference_track"}
    result = KennAutonomousAgent().tools[command["action"]].execute()
    assert result["available"] is False and result["eq_recipe"] == []


def test_reference_objective_without_spectra_does_not_propose_eq_or_claim_balance(monkeypatch):
    from kenn import audio_telemetry
    from kenn.core import acoustic_calibration, subjective_translator

    monkeypatch.setattr(audio_telemetry, "get_telemetry_manager", lambda: SimpleNamespace(get_latest=lambda: None))
    monkeypatch.setattr(acoustic_calibration.AcousticCalibrationLoop, "capture_baseline", lambda *args, **kwargs: {})
    monkeypatch.setattr(acoustic_calibration.AcousticCalibrationLoop, "diagnose_clashes", lambda *args: [])
    monkeypatch.setattr(subjective_translator.SubjectiveTranslator, "can_translate", lambda *args: False)
    result = KennAutonomousAgent().react_deliberate(
        "Match reference spectrum",
        session_id="reference-fixture",
        session_snapshot={"tracks": [{"index": 0, "name": "Synth", "devices": []}]},
    )
    reference = next(item for item in result["trajectory"] if item["phase"] == "reference_matching")
    assert reference["observation"]["available"] is False
    assert reference["observation"]["eq_recipe"] == []
    assert result["ok"] is False
    assert result["status"] == "reference_unavailable"
    assert "measured" in result["answer"].lower()
    assert "proposal" not in result
    assert result["requires_confirmation"] is False
