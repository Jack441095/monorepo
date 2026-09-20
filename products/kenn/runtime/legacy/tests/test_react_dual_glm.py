"""Tests for KENN Dual-GLM ReAct Autonomous Orchestration and Closed-Loop Calibration."""

import pytest
from kenn.autonomous_agent import KennAutonomousAgent
from kenn.core.acoustic_calibration import AcousticCalibrationLoop
from kenn.audio_telemetry import AudioTelemetryFrame, get_telemetry_manager


def test_react_deliberate_with_live_telemetry():
    """Verify that react_deliberate ingests live telemetry, clamps clipping, and respects safety bounds."""
    manager = get_telemetry_manager()
    # Ingest a live telemetry frame simulating true peak overload and mud
    frame = AudioTelemetryFrame(
        integrated_lufs=-11.2,
        short_term_lufs=-9.8,
        true_peak_dbtp=+0.4,  # Overload!
        spectral_energy={
            "sub_20_60hz": 0.35,
            "low_mid_200_500hz": 0.40,  # Mud alert!
            "high_mid_2_6khz": 0.15,
            "air_10_20khz": 0.10,
        },
        phase_correlation=0.18,  # Mono cancellation risk!
        crest_factor_db=5.2,
    )
    manager.ingest(frame.to_dict())

    session_snapshot = {
        "tracks": [
            {"index": 0, "name": "Kick", "volume": 0.85, "panning": 0.0},
            {"index": 1, "name": "Sub Bass", "volume": 0.88, "panning": -0.1},
            {"index": 2, "name": "Lead Synth", "volume": 0.80, "panning": 0.3},
        ]
    }

    agent = KennAutonomousAgent()
    result = agent.react_deliberate("Unmask the low end and fix headroom issues", session_snapshot=session_snapshot)

    assert result["ok"] is True
    assert result["status"] == "confirmation_required"
    assert "proposal" in result
    assert result["requires_confirmation"] is True
    assert result["confirmation_token"].startswith("react_")

    steps = result["proposal"]["steps"]
    assert len(steps) > 0

    # Verify limiter ceiling clamping step was generated due to +0.4 dBTP overload
    limiter_steps = [
        s for s in steps
        if s.get("track_name") == "Master" and s.get("device_name") == "Limiter" and s.get("parameter") == "Ceiling"
    ]
    assert len(limiter_steps) == 1
    assert limiter_steps[0]["after"] == -1.0

    # Verify hardware safety clamps: Master volume fader is NEVER touched
    for s in steps:
        if s.get("action") == "set_volume":
            assert "master" not in str(s.get("track_name", "")).lower()
            before = float(s.get("before", 0.85))
            after = float(s.get("after", before))
            # Delta gain clamp <= 3.0 dB (~ 0.20 normalized)
            assert abs(after - before) <= 0.205

    # Verify trajectory contains telemetry sensing and ERB psychoacoustic diagnosis
    phases = [t.get("phase") for t in result["trajectory"]]
    assert "perception" in phases
    assert "telemetry_sensing" in phases
    assert "diagnosis" in phases
    assert "synthesis" in phases


def test_acoustic_calibration_loop_with_telemetry_and_lufs_delta():
    """Verify closed-loop calibration delta verification and predicted delta LUFS."""
    loop = AcousticCalibrationLoop()
    session_snapshot = {
        "tracks": [
            {"index": 0, "name": "Kick", "volume": 0.90, "panning": 0.0},
            {"index": 1, "name": "Sub Bass", "volume": 0.88, "panning": 0.0},
        ]
    }

    meters = {
        "phase_correlation": 0.95,
        "spectral_energy": {
            "sub_20_60hz": 0.40,
            "low_mid_200_500hz": 0.30,
            "high_mid_2_6khz": 0.15,
            "air_10_20khz": 0.15,
        }
    }

    baseline = loop.capture_baseline("test_session", session_snapshot, meters=meters)
    assert len(baseline.track_energies) == 2
    assert baseline.stereo_correlations[0] == 0.95

    clashes = loop.diagnose_clashes(baseline)
    recipe = loop.formulate_calibration_recipe(baseline, clashes)
    assert recipe["ok"] is True

    # Simulate post-intervention tracks with reduced faders
    post_tracks = [
        {"index": 0, "name": "Kick", "volume": 0.83, "panning": 0.0},
        {"index": 1, "name": "Sub Bass", "volume": 0.85, "panning": 0.0},
    ]
    delta_report = loop.verify_acoustic_delta(baseline, post_tracks)

    assert delta_report.session_id == "test_session"
    assert isinstance(delta_report.predicted_delta_lufs, float)
    assert delta_report.recommendation in ["commit", "refine", "rollback"]

