"""Tests for KENN Closed-Loop Acoustic Calibration Engine ("Genelec GLM Loop")."""

import pytest
from kenn.core.acoustic_calibration import (
    AcousticCalibrationLoop,
    AcousticBaseline,
    AcousticDeltaReport,
)


@pytest.fixture
def mock_clashing_session():
    return {
        "status": "connected",
        "tracks": [
            {"index": 0, "name": "Kick", "volume": 0.88, "pan": 0.0, "panning": 0.0, "devices": []},
            {"index": 1, "name": "Sub Bass", "volume": 0.85, "pan": 0.30, "panning": 0.30, "devices": []},
            {"index": 2, "name": "Lead Vocal", "volume": 0.70, "pan": 0.0, "panning": 0.0, "devices": []},
            {"index": 3, "name": "Supersaw Synth", "volume": 0.82, "pan": 0.0, "panning": 0.0, "devices": []},
        ],
    }


def test_acoustic_baseline_capture(mock_clashing_session):
    loop = AcousticCalibrationLoop()
    baseline = loop.capture_baseline("test-sess", mock_clashing_session)

    assert baseline.session_id == "test-sess"
    assert baseline.track_count == 4
    assert len(baseline.erb_bands) == 40
    assert 0 in baseline.track_energies
    assert len(baseline.track_energies[0]) == 40
    assert len(baseline.masking_matrix) > 0


def test_diagnose_clashes(mock_clashing_session):
    loop = AcousticCalibrationLoop()
    baseline = loop.capture_baseline("test-sess", mock_clashing_session)
    clashes = loop.diagnose_clashes(baseline)

    assert len(clashes) >= 1
    # Verify clash metadata
    for c in clashes:
        assert "masker_name" in c
        assert "victim_name" in c
        assert "frequency_hz" in c
        assert c["masking_ratio"] >= 0.35


def test_formulate_calibration_recipe_clamping(mock_clashing_session):
    loop = AcousticCalibrationLoop()
    baseline = loop.capture_baseline("test-sess", mock_clashing_session)
    clashes = loop.diagnose_clashes(baseline)
    recipe_res = loop.formulate_calibration_recipe(baseline, clashes)

    assert recipe_res["ok"] is True
    proposal = recipe_res["proposal"]
    assert proposal["requires_confirmation"] is True
    assert len(proposal["steps"]) > 0

    # Ensure all fader movements strictly adhere to <= 3.0 dB safety clamp
    for step in proposal["steps"]:
        if step["action"] == "set_volume":
            assert abs(step["after"] - step["before"]) <= 0.20
        elif step["action"] == "set_pan":
            assert step["after"] == 0.0  # Sub bass centering


def test_verify_acoustic_delta_evaluation(mock_clashing_session):
    loop = AcousticCalibrationLoop()
    baseline = loop.capture_baseline("test-sess", mock_clashing_session)

    # Post-intervention session where synth has been trimmed and vocal boosted
    post_tracks = [
        {"index": 0, "name": "Kick", "volume": 0.88, "pan": 0.0, "panning": 0.0, "devices": []},
        {"index": 1, "name": "Sub Bass", "volume": 0.80, "pan": 0.0, "panning": 0.0, "devices": []},
        {"index": 2, "name": "Lead Vocal", "volume": 0.75, "pan": 0.0, "panning": 0.0, "devices": []},
        {"index": 3, "name": "Supersaw Synth", "volume": 0.75, "pan": 0.0, "panning": 0.0, "devices": []},
    ]

    report = loop.verify_acoustic_delta(baseline, post_tracks)
    assert isinstance(report, AcousticDeltaReport)
    assert report.session_id == "test-sess"
    assert report.recommendation in {"commit", "refine"}
    assert report.target_satisfied is True


def test_refine_intervention_paths(mock_clashing_session):
    loop = AcousticCalibrationLoop()
    baseline = loop.capture_baseline("test-sess", mock_clashing_session)
    clashes = loop.diagnose_clashes(baseline)
    initial_recipe = loop.formulate_calibration_recipe(baseline, clashes)["proposal"]

    # Test "commit" report -> proposal should be None
    commit_report = AcousticDeltaReport(
        session_id="test-sess",
        pre_intervention_clash_count=3,
        post_intervention_clash_count=0,
        resolved_clashes=["Synth -> Vocal"],
        residual_clashes=[],
        masking_reduction_db=2.5,
        stereo_correlation_delta=0.05,
        headroom_recovery_db=0.8,
        target_satisfied=True,
        confidence_score=0.95,
        recommendation="commit",
    )
    commit_res = loop.refine_intervention(baseline, commit_report, initial_recipe)
    assert commit_res["status"] == "committed"
    assert commit_res["proposal"] is None

    # Test "refine" report -> proposal should have refined steps
    refine_report = AcousticDeltaReport(
        session_id="test-sess",
        pre_intervention_clash_count=3,
        post_intervention_clash_count=1,
        resolved_clashes=["Synth -> Vocal"],
        residual_clashes=["Kick -> Bass"],
        masking_reduction_db=0.8,
        stereo_correlation_delta=0.0,
        headroom_recovery_db=0.2,
        target_satisfied=False,
        confidence_score=0.65,
        recommendation="refine",
    )
    refine_res = loop.refine_intervention(baseline, refine_report, initial_recipe)
    assert refine_res["status"] == "refined_proposal"
    assert refine_res["proposal"]["is_refinement"] is True

    # Test "rollback" report -> proposal should invert steps
    rollback_report = AcousticDeltaReport(
        session_id="test-sess",
        pre_intervention_clash_count=2,
        post_intervention_clash_count=4,
        resolved_clashes=[],
        residual_clashes=["Kick -> Bass", "Synth -> Vocal", "Cymbal -> Snare", "Bass -> Kick"],
        masking_reduction_db=0.0,
        stereo_correlation_delta=-0.1,
        headroom_recovery_db=-0.5,
        target_satisfied=False,
        confidence_score=0.3,
        recommendation="rollback",
    )
    rollback_res = loop.refine_intervention(baseline, rollback_report, initial_recipe)
    assert rollback_res["status"] == "rollback_proposed"
    assert rollback_res["proposal"]["is_rollback"] is True
    # Verify inverse mapping: after of step 0 should match before of initial recipe
    assert rollback_res["proposal"]["steps"][0]["after"] == initial_recipe["steps"][-1]["before"]


def test_live_meter_fusion(mock_clashing_session):
    loop = AcousticCalibrationLoop()
    mock_meters = {
        0: {"erb_profile": [0.5] * 40},
        1: [0.2] * 40,
    }
    baseline = loop.capture_baseline("test-sess", mock_clashing_session, meters=mock_meters)
    assert baseline.track_energies[0] == [0.5] * 40
    assert baseline.track_energies[1] == [0.2] * 40
