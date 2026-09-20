"""End-to-end integration test for KENN Autonomous Producer & Ambient Studio Guardian."""

import pytest
from kenn.core.ambient_guardian import AmbientStudioGuardian, get_ambient_guardian
from kenn.autonomous_agent import KennAutonomousAgent
from kenn.orchestrator import KennOrchestrator
from kenn.core.acoustic_calibration import AcousticCalibrationLoop


@pytest.fixture
def complex_multitrack_session():
    return {
        "status": "connected",
        "tracks": [
            {"index": 0, "name": "Kick", "volume": 0.88, "pan": 0.0, "panning": 0.0, "devices": []},
            {"index": 1, "name": "Sub Bass", "volume": 0.86, "pan": 0.28, "panning": 0.28, "devices": []},
            {"index": 2, "name": "Lead Vocal", "volume": 0.68, "pan": 0.0, "panning": 0.0, "devices": []},
            {"index": 3, "name": "Supersaw Lead", "volume": 0.82, "pan": 0.0, "panning": 0.0, "devices": []},
            {"index": 4, "name": "Rhythm Guitar", "volume": 0.76, "pan": -0.4, "panning": -0.4, "devices": []},
        ],
    }


def test_ambient_guardian_evaluates_session(complex_multitrack_session):
    guardian = AmbientStudioGuardian()


    # 1. Evaluate with hot meters (> -0.3 dBFS headroom)
    hot_meters = {
        "peak_dbfs": -0.15,
        "crest_db": 9.2,
        "stereo_correlation": 0.78,
    }


    status = guardian.evaluate_session(
        complex_multitrack_session,
        meters=hot_meters,
        session_id="test-ambient-e2e",
    )


    assert status["connected"] is True
    assert status["headroom_safe"] is False
    assert status["status"] == "advisory"
    assert status["active_clashes_count"] >= 1
    assert len(status["advisories"]) >= 2  # Headroom + at least one clash
    assert status["staged_proposal"] is not None
    assert status["confirmation_token"] != ""
    assert status["frequency_zones"]["sub"]["status"] == "clashing" or status["frequency_zones"]["punch"]["status"] == "clashing"


def test_autonomous_producer_end_to_end_deliberation(complex_multitrack_session):
    orchestrator = KennOrchestrator()


    # 1. Orchestrator classifies imperative unmask request
    prompt = "balance the mix and unmask the lead vocal"
    matched_agent = orchestrator.classify(prompt)
    assert matched_agent == "autonomous_producer"


    # 2. Dispatch autonomous deliberation
    dispatch_res = orchestrator.dispatch(
        prompt,
        session_snapshot=complex_multitrack_session,
        session_id="test-e2e-session",
    )


    assert dispatch_res is not None
    assert dispatch_res["orchestrated"] is True
    assert dispatch_res["agent_name"] == "autonomous_producer"
    assert dispatch_res["status"] == "confirmation_required"
    assert "proposal" in dispatch_res
    assert len(dispatch_res["proposal"]["steps"]) > 0


    # 3. Verify ReAct deliberation trajectory integrity
    trajectory = dispatch_res["trajectory"]
    assert len(trajectory) >= 3
    phases = [s["phase"] for s in trajectory]
    assert "perception" in phases
    assert "diagnosis" in phases
    assert "synthesis" in phases


    # 4. Verify closed-loop acoustic delta evaluation
    calib = AcousticCalibrationLoop()
    baseline = calib.capture_baseline("test-e2e-session", complex_multitrack_session)


    # Simulate applying calibrated adjustments: center sub bass & trim masking track volumes
    applied_tracks = [dict(t) for t in complex_multitrack_session["tracks"]]
    applied_tracks[1]["pan"] = 0.0
    applied_tracks[1]["panning"] = 0.0
    applied_tracks[1]["volume"] = 0.78
    applied_tracks[3]["volume"] = 0.74


    delta_report = calib.verify_acoustic_delta(baseline, applied_tracks)


    assert delta_report.session_id == "test-e2e-session"
    assert delta_report.target_satisfied is True
    assert delta_report.recommendation in {"commit", "refine"}
    assert delta_report.headroom_recovery_db > 0.0 or delta_report.stereo_correlation_delta > 0.0
