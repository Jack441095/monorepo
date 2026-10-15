"""Tests for SessionDoctor audit and autonomous remediation batch generation."""

import math

import pytest

from kenn.core.session_doctor import SessionDoctor


_MISSING_RMS = object()


def test_session_doctor_identifies_headroom_clipping_risk():
    session_state = {
        "tracks": [
            {"index": 0, "name": "Hot Lead", "volume": 0.95, "panning": 0.0, "devices": []},
            {"index": 1, "name": "Normal Pad", "volume": 0.75, "panning": 0.0, "devices": []},
        ]
    }
    report = SessionDoctor.audit(session_state)
    assert report.ok is True
    assert report.track_count == 2
    assert report.issues_found >= 1
    hot_issues = [i for i in report.issues if i.code == "HEADROOM_CLIPPING_RISK"]
    assert len(hot_issues) == 1
    assert hot_issues[0].track_index == 0
    assert hot_issues[0].proposed_value < 0.95

    # Remediation batch has the trimming action
    assert len(report.remediation_batch) == 1
    assert report.remediation_batch[0]["action"] == "set_volume"
    assert report.remediation_batch[0]["track_index"] == 0
    assert report.remediation_batch[0]["value"] == round(hot_issues[0].proposed_value, 3)


def test_session_doctor_flags_negative_stereo_correlation():
    session_state = {
        "tracks": [
            {"index": 0, "name": "Bass", "volume": 0.80, "panning": 0.0, "devices": []},
        ]
    }
    meters = {"peak_dbfs": -2.0, "rms_dbfs": -18.0, "stereo_correlation": -0.45}
    report = SessionDoctor.audit(session_state, meters=meters)
    phase_issues = [i for i in report.issues if i.code == "STEREO_PHASE_CANCELLATION"]
    assert len(phase_issues) == 1
    assert phase_issues[0].severity == "critical"


# Hot peak and phase readings can persist when RMS is near silence, but structural fader checks still apply.
@pytest.mark.parametrize("rms,active", [
    pytest.param(_MISSING_RMS, False, id="missing"),
    pytest.param(None, False, id="null"),
    pytest.param(True, False, id="boolean"),
    pytest.param(float("nan"), False, id="nan"),
    pytest.param(float("inf"), False, id="positive-infinity"),
    pytest.param(-float("inf"), False, id="negative-infinity"),
    pytest.param(10**1000, False, id="overflowing-integer"),
    pytest.param(-100.0, False, id="quiet"),
    pytest.param(-80.0, False, id="at-activity-floor"),
    pytest.param(-79.9, True, id="above-activity-floor"),
])
def test_session_doctor_gates_only_meter_findings_on_live_activity(rms, active) -> None:
    meters = {"peak_dbfs": 0.0, "stereo_correlation": -1.0}
    if rms is not _MISSING_RMS:
        meters["rms_dbfs"] = rms
    report = SessionDoctor.audit({"tracks": [
        {"index": 0, "name": "Hot Lead", "volume": 0.95, "devices": [{"name": "Compressor"}]},
    ]}, meters=meters)

    codes = {issue.code for issue in report.issues}
    assert "HEADROOM_CLIPPING_RISK" in codes
    assert "LOW_END_MUD_RISK" in codes
    assert ("MASTER_OVERLOAD_RISK" in codes) is active
    assert ("STEREO_PHASE_CANCELLATION" in codes) is active
    assert any(action["action"] == "set_volume" for action in report.remediation_batch)


@pytest.mark.parametrize("field,value", [
    ("peak_dbfs", None), ("peak_dbfs", True), ("peak_dbfs", math.nan), ("peak_dbfs", math.inf),
    ("peak_dbfs", 10**1000), ("stereo_correlation", None), ("stereo_correlation", False),
    ("stereo_correlation", math.nan), ("stereo_correlation", -math.inf), ("stereo_correlation", 10**1000),
])
def test_session_doctor_does_not_invent_missing_or_invalid_active_meter_values(field, value) -> None:
    meters = {"rms_dbfs": -18.0, "peak_dbfs": 0.0, "stereo_correlation": -1.0}
    meters[field] = value

    report = SessionDoctor.audit({"tracks": []}, meters=meters)
    codes = {issue.code for issue in report.issues}

    assert ("MASTER_OVERLOAD_RISK" in codes) is (field != "peak_dbfs")
    assert ("STEREO_PHASE_CANCELLATION" in codes) is (field != "stereo_correlation")


def test_session_doctor_flags_sub_bass_off_center():
    session_state = {
        "tracks": [
            {"index": 0, "name": "Sub Bass", "volume": 0.80, "panning": 0.35, "devices": []},
        ]
    }
    report = SessionDoctor.audit(session_state)
    sub_issues = [i for i in report.issues if i.code == "SUB_BASS_OFF_CENTER"]
    assert len(sub_issues) == 1
    assert sub_issues[0].proposed_value == 0.0
    assert report.remediation_batch[0]["action"] == "set_pan"
    assert report.remediation_batch[0]["value"] == 0.0


def test_session_doctor_flags_low_end_mud_on_non_bass_tracks():
    session_state = {
        "tracks": [
            {"index": 0, "name": "Lead Vocal", "volume": 0.80, "panning": 0.0, "devices": [{"name": "Compressor"}]},
            {"index": 1, "name": "Clean Guitar", "volume": 0.80, "panning": 0.0, "devices": [{"name": "EQ Eight"}]},
        ]
    }
    report = SessionDoctor.audit(session_state)
    mud_issues = [i for i in report.issues if i.code == "LOW_END_MUD_RISK"]
    assert len(mud_issues) == 1
    assert mud_issues[0].track_name == "Lead Vocal"


def test_session_doctor_flags_psychoacoustic_masking_clash():
    p1 = [0.0] * 40
    p1[10] = 1.0  # Dominant masker at band 10 (~300 Hz)
    p2 = [0.0] * 40
    p2[10] = 0.1  # Clashing victim at band 10

    session_state = {
        "tracks": [
            {"index": 0, "name": "Bass", "volume": 0.85, "panning": 0.0, "devices": [], "erb_profile": p1},
            {"index": 1, "name": "Synths", "volume": 0.80, "panning": 0.0, "devices": [], "erb_profile": p2},
        ]
    }
    report = SessionDoctor.audit(session_state)
    masking_issues = [i for i in report.issues if i.code == "PSYCHOACOUSTIC_MASKING_CLASH"]
    assert len(masking_issues) >= 1
    assert masking_issues[0].track_name == "Bass"
    assert -3.0 <= masking_issues[0].proposed_value < 0.0


def test_session_doctor_flags_dynamic_low_end_masking():
    session_state = {
        "tracks": [
            {"index": 0, "name": "Kick Punch", "volume": 0.85, "panning": 0.0, "devices": []},
            {"index": 1, "name": "808 Sub Bass", "volume": 0.80, "panning": 0.0, "devices": []},
        ]
    }
    report = SessionDoctor.audit(session_state)
    mask_issues = [i for i in report.issues if i.code == "DYNAMIC_LOW_END_MASKING"]
    assert len(mask_issues) == 1
    assert mask_issues[0].track_name == "808 Sub Bass"
    assert -3.0 <= mask_issues[0].proposed_value <= -1.0
    sidechain_actions = [a for a in report.remediation_batch if a["action"] == "configure_sidechain"]
    assert len(sidechain_actions) == 1
    assert sidechain_actions[0]["track_index"] == 1


def test_session_doctor_flags_multi_stem_summing_overload():
    session_state = {
        "tracks": [
            {"index": 0, "name": "Drums", "volume": 0.90, "panning": 0.0, "devices": []},
            {"index": 1, "name": "Bass", "volume": 0.88, "panning": 0.0, "devices": []},
            {"index": 2, "name": "Lead", "volume": 0.89, "panning": 0.0, "devices": []},
            {"index": 3, "name": "Vocals", "volume": 0.87, "panning": 0.0, "devices": []},
        ]
    }
    report = SessionDoctor.audit(session_state)
    overload_issues = [i for i in report.issues if i.code == "MULTI_STEM_SUMMING_OVERLOAD"]
    assert len(overload_issues) >= 3
