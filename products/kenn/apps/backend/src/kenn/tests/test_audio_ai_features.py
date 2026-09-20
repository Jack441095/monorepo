"""Unit tests for audio telemetry ingest and agentic mix planner in KENN."""

import time
import pytest
from kenn.audio_telemetry import AudioTelemetryManager, AudioTelemetryFrame
from kenn.agent.mix_planner import MixPlanner


def test_audio_telemetry_ingest_and_diagnose() -> None:
    mgr = AudioTelemetryManager()

    # Frame with clipping and low-mid mud
    data = {
        "integrated_lufs": -8.5,
        "short_term_lufs": -7.2,
        "true_peak_dbtp": +0.6,
        "spectral_energy": {
            "sub_20_60hz": 0.20,
            "low_mid_200_500hz": 0.38,
            "high_mid_2_6khz": 0.22,
            "air_10_20khz": 0.20,
        },
        "phase_correlation": 0.18,
        "crest_factor_db": 5.4,
    }

    frame = mgr.ingest(data)
    assert frame.true_peak_dbtp == 0.6
    assert frame.integrated_lufs == -8.5

    anomalies = mgr.diagnose_anomalies(frame)
    assert any("True Peak Overload" in a for a in anomalies)
    assert any("Mono Cancellation Risk" in a for a in anomalies)
    assert any("Low-Mid Mud" in a for a in anomalies)
    assert any("Squashed Dynamics" in a for a in anomalies)

    # Context formatting
    ctx = mgr.format_prompt_context(frame)
    assert "Live Audio Telemetry (DAW Master):" in ctx
    assert "+0.6 dBTP" in ctx

    # Evidence packet conversion
    packet = mgr.to_evidence_packet(frame)
    assert packet is not None
    assert packet.source == "audio_telemetry"
    assert len(packet.facts) >= 5


def test_mix_planner_dag_generation() -> None:
    planner = MixPlanner()

    telemetry = AudioTelemetryFrame(
        integrated_lufs=-11.0,
        short_term_lufs=-9.5,
        true_peak_dbtp=+0.4,
        phase_correlation=0.82,
        crest_factor_db=7.5,
    )

    query = "My vocal sounds muddy in the room and the master is clipping on Spotify."
    plan = planner.create_plan(query, telemetry=telemetry)

    assert plan.plan_id.startswith("plan_")
    assert len(plan.steps) >= 3

    step_names = [s.name for s in plan.steps]
    assert "Telemetry Diagnostic Check" in step_names
    assert "Carve Low-Mid Boxiness" in step_names
    assert "Clamp True Peak Ceiling" in step_names
    assert "Zero-Bias Loudness-Matched A/B Audition" in step_names

    # Check dependencies form a valid sequence
    for i in range(1, len(plan.steps)):
        assert plan.steps[i].depends_on == [plan.steps[i - 1].id]


def test_vst3_handoff_bridging_to_telemetry() -> None:
    """Verify that VST3 plugin handoff metrics bridge directly into AudioTelemetryManager."""
    from kenn.plugin_handoff import ingest_live_context
    from kenn.audio_telemetry import get_telemetry_manager

    handoff_payload = {
        "schema": "kenn.plugin_handoff.v1",
        "kind": "mix_review_snapshot",
        "session_id": "test_vst3_session",
        "peak_dbfs": -0.15,  # High peak
        "rms_dbfs": -11.5,
        "stereo_correlation": 0.22,  # Low correlation warning
        "stereo_width": 0.85,
        "sample_rate": 48000,
        "analysed_samples": 48000,
        "crest_db": 11.35,
        "low_energy": 1.2,
        "mid_energy": 2.5,  # High mid/low-mid
        "high_energy": 0.8,
        "assistant_mode": "suggest",
        "plugin_state": {"assistant_mode": "suggest"},
    }

    res = ingest_live_context(handoff_payload, session_id="test_vst3_session")
    assert res.get("ok") is True

    telemetry = get_telemetry_manager().get_latest()
    assert telemetry is not None
    assert telemetry.true_peak_dbtp == -0.15
    assert telemetry.phase_correlation == 0.22
    anomalies = get_telemetry_manager().diagnose_anomalies(telemetry)
    assert any("Mono Cancellation Risk" in a for a in anomalies)


def test_live_telemetry_poller_lifecycle() -> None:
    """Verify starting and stopping the background live meter poller."""
    from kenn.audio_telemetry import LiveTelemetryPoller
    poller = LiveTelemetryPoller(interval_seconds=0.05)
    poller.start()
    assert poller._running is True
    time.sleep(0.1)
    poller.stop()
    assert poller._running is False
