"""Unit tests for audio telemetry ingest and agentic mix planner in KENN."""

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


def test_a_meter_that_sends_nothing_leaves_every_reading_absent() -> None:
    # 14 Oct 2026: an empty frame read as -14 LUFS, -1 dBTP and 0.90 correlation, so the mix audit graded it healthy.
    frame = AudioTelemetryManager().ingest({})

    assert frame.true_peak_dbtp is None and frame.integrated_lufs is None
    assert frame.phase_correlation is None and frame.spectral_energy == {}
    assert set(frame.to_dict()) == {"timestamp"}


def test_a_reading_the_meter_did_not_send_is_not_diagnosed_or_quoted() -> None:
    manager = AudioTelemetryManager()
    frame = manager.ingest({"true_peak_dbtp": -3.0})

    assert manager.diagnose_anomalies(frame) == []
    context = manager.format_prompt_context(frame)
    assert "-3.0 dBTP" in context
    assert "LUFS" not in context and "Phase Correlation" not in context
    assert [fact.name for fact in manager.to_evidence_packet(frame).facts] == ["true_peak_dbtp"]


def test_junk_meter_values_count_as_not_sent() -> None:
    frame = AudioTelemetryManager().ingest({
        "integrated_lufs": "loud", "true_peak_dbtp": float("nan"), "phase_correlation": None,
        "spectral_energy": {"low_mid_200_500hz": "n/a", "sub_20_60hz": 0.2},
    })

    assert frame.integrated_lufs is None and frame.true_peak_dbtp is None and frame.phase_correlation is None
    assert frame.spectral_energy == {"sub_20_60hz": 0.2}


def test_an_empty_frame_does_not_earn_the_mix_audit_any_points() -> None:
    from kenn.core.mix_doctor import MixDoctor

    meters = AudioTelemetryManager().ingest({}).to_dict()
    report = MixDoctor().audit_session({"tracks": []}, meters=meters)

    assert report.grade == "UNRATED"
    assert report.points_available == 20.0  # stem separation needs no meter, and an empty session costs it nothing


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


def test_vst3_insert_features_preserve_units_and_leave_master_telemetry_untouched(monkeypatch) -> None:
    """An insert's RMS and sample peak must never become master LUFS or dBTP."""
    import kenn.audio_telemetry as telemetry
    import kenn.plugin_handoff as handoff

    manager = AudioTelemetryManager()
    master = manager.ingest({"integrated_lufs": -16.0, "true_peak_dbtp": -1.2})
    monkeypatch.setattr(telemetry, "_telemetry_manager", manager)
    monkeypatch.setattr(handoff, "_live_contexts", {})

    handoff_payload = {
        "schema": "kenn.plugin_handoff.v1",
        "kind": "mix_review_snapshot",
        "session_id": "test_vst3_session",
        "peak_dbfs": -0.15,
        "rms_dbfs": -11.5,
        "stereo_correlation": 0.22,
        "stereo_width": 0.85,
        "sample_rate": 48000,
        "analysed_samples": 48000,
        "crest_db": 11.35,
        "low_energy": 1.2,
        "mid_energy": 2.5,
        "high_energy": 0.8,
        "assistant_mode": "suggest",
        "plugin_state": {"assistant_mode": "suggest"},
    }

    res = handoff.ingest_live_context(handoff_payload, session_id="test_vst3_session")
    assert res.get("ok") is True
    context = res["live_context"]
    assert context["peak_dbfs"] == -0.15
    assert context["rms_dbfs"] == -11.5
    assert context["stereo_correlation"] == 0.22
    assert "integrated_lufs" not in context
    assert "true_peak_dbtp" not in context
    assert manager.get_latest() is master
