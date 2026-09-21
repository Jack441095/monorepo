"""Validation suite for KENN Closed-Loop Diagnostic & Surgical Masking Doctor."""

import pytest
from kenn.core.session_doctor import SessionDoctor


def test_formulate_surgical_remediation_clashing_sub_kick():
    session_state = {
        "tracks": [
            {"index": 0, "name": "Punchy Kick", "volume": 0.85, "panning": 0.0, "devices": []},
            {"index": 1, "name": "808 Sub Bass", "volume": 0.85, "panning": 0.0, "devices": []},
        ]
    }
    res = SessionDoctor.formulate_surgical_remediation_proposal(session_state, session_id="test_remedy_kick_sub")
    assert res["ok"] is True
    prop = res["proposal"]
    assert prop["is_doctor_remediation"] is True
    assert prop["requires_confirmation"] is True
    assert prop["confirmation_token"].startswith("doctor_remedy_")
    assert prop["step_count"] >= 1

    actions = [s["action"] for s in prop["steps"]]
    assert "configure_sidechain" in actions or "device_eq_cut" in actions

    metrics = prop["predicted_metrics"]
    assert metrics["masking_reduction_percent"] > 0.0
    assert "headroom_reclaimed_db" in metrics
    assert "mono_correlation_delta" in metrics


def test_formulate_surgical_remediation_low_mid_mud_and_vocal_masking():
    session_state = {
        "tracks": [
            {"index": 0, "name": "Lead Vocal", "volume": 0.80, "panning": 0.0, "devices": []},
            {"index": 1, "name": "Synth Lead", "volume": 0.80, "panning": 0.0, "devices": []},
            {"index": 2, "name": "Ambient Pad", "volume": 0.75, "panning": 0.0, "devices": []},
        ]
    }
    res = SessionDoctor.formulate_surgical_remediation_proposal(session_state, session_id="test_remedy_vocal_mud")
    assert res["ok"] is True
    prop = res["proposal"]
    assert prop["step_count"] >= 2

    # Should detect low-mid mud on synth/pad and vocal presence clash on synth
    steps = prop["steps"]
    eq_cuts = [s for s in steps if s["action"] == "device_eq_cut"]
    hp_inserts = [s for s in steps if s["action"] == "insert_device"]

    assert len(eq_cuts) >= 1 or len(hp_inserts) >= 1
    metrics = prop["predicted_metrics"]
    assert metrics["masking_reduction_percent"] > 50.0
    assert metrics["headroom_reclaimed_db"] >= 0.0


def test_formulate_surgical_remediation_phase_and_fader_overload():
    session_state = {
        "tracks": [
            {"index": 0, "name": "Overloaded Guitar", "volume": 0.94, "panning": 0.0, "devices": []},
            {"index": 1, "name": "Sub Bass", "volume": 0.80, "panning": 0.30, "devices": []},
        ]
    }
    meters = {"peak_dbfs": -0.2, "stereo_correlation": -0.35}
    res = SessionDoctor.formulate_surgical_remediation_proposal(session_state, meters=meters, session_id="test_remedy_phase")
    assert res["ok"] is True
    prop = res["proposal"]

    actions = {s["action"] for s in prop["steps"]}
    assert "set_volume" in actions
    assert "set_pan" in actions
    assert "insert_device" in actions

    metrics = prop["predicted_metrics"]
    assert metrics["headroom_reclaimed_db"] >= 0.8
    assert metrics["mono_correlation_delta"] > 0.0
