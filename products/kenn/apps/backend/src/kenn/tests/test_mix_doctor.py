"""Unit and integration tests for KENN Full-Session Mix Doctor (0-100 MQM)."""

from __future__ import annotations

import pytest
from kenn.core.mix_doctor import MixDoctor, get_mix_doctor


def _build_synthetic_16_track_session():
    """Build realistic 16-track Ableton Live session snapshot."""
    track_configs = [
        ("Kick Drum", 0.85, 0.0, ["Eq8", "Compressor"]),
        ("Snare Top", 0.80, 0.0, ["Eq8"]),
        ("Snare Bottom", 0.70, 0.0, []),
        ("Hi-Hats Closed", 0.65, -0.2, ["Eq8"]),
        ("Hi-Hats Open", 0.65, 0.25, ["Eq8"]),
        ("Toms Bus", 0.75, 0.0, ["Compressor"]),
        ("Sub Bass", 0.85, 0.0, ["Eq8"]),
        ("Reese Mid-Bass", 0.75, 0.0, ["Saturator", "Eq8"]),
        ("Lead Vocal", 0.88, 0.0, ["VocalStrip", "Compressor", "Eq8"]),
        ("Backing Vocal L", 0.70, -0.45, ["Eq8"]),
        ("Backing Vocal R", 0.70, 0.45, ["Eq8"]),
        ("Electric Rhythm Guitar", 0.75, -0.35, ["Amp", "Eq8"]),
        ("Acoustic Lead Guitar", 0.75, 0.35, ["Eq8"]),
        ("Main Synth Pad", 0.72, 0.0, ["Chorus", "Eq8"]),
        ("Arp Lead Synth", 0.74, 0.15, ["Delay", "Eq8"]),
        ("FX Riser / Impacts", 0.65, 0.0, ["Reverb"]),
    ]
    tracks = [
        {
            "index": idx,
            "name": name,
            "volume": vol,
            "panning": pan,
            "devices": [{"name": d} for d in dev_list],
            "mute": False,
            "solo": False,
        }
        for idx, (name, vol, pan, dev_list) in enumerate(track_configs)
    ]
    return {
        "tracks": tracks,
        "master": {"volume": 0.85, "panning": 0.0, "devices": [{"name": "Limiter"}]},
    }


def test_mix_doctor_audit_synthetic_session():
    doctor = MixDoctor()
    session = _build_synthetic_16_track_session()
    meters = {
        "integrated_lufs": -13.8,
        "true_peak_dbtp": -1.2,
        "phase_correlation": 0.88,
        "crest_factor_db": 10.5,
        "spectral_energy": {
            "sub_20_60hz": 0.25,
            "low_mid_200_500hz": 0.26,
            "high_mid_2_6khz": 0.25,
            "air_10_20khz": 0.24,
        },
    }

    report = doctor.audit_session(session, meters=meters)

    assert 70.0 <= report.mqm_score <= 100.0
    assert report.grade in ("S", "A", "B")
    assert "dynamic_health" in report.dimension_scores
    assert "low_end_control" in report.dimension_scores
    assert "spectral_balance" in report.dimension_scores
    assert "stem_separation" in report.dimension_scores
    assert "stereo_imaging" in report.dimension_scores
    assert report.dimension_scores["dynamic_health"] == 20.0
    assert report.dimension_scores["stereo_imaging"] == 20.0


def test_mix_doctor_detects_clipping_and_boxiness():
    doctor = MixDoctor()
    session = _build_synthetic_16_track_session()
    # Add volume fader clipping
    session["tracks"][0]["volume"] = 1.25

    # Meters showing True Peak clipping and low-mid mud buildup
    meters = {
        "integrated_lufs": -10.0,
        "true_peak_dbtp": +0.6,  # Clipping!
        "phase_correlation": 0.85,
        "crest_factor_db": 5.0,  # Squashed!
        "spectral_energy": {
            "sub_20_60hz": 0.20,
            "low_mid_200_500hz": 0.42,  # Boxy!
            "high_mid_2_6khz": 0.25,
            "air_10_20khz": 0.13,
        },
    }

    report = doctor.audit_session(session, meters=meters)

    assert report.mqm_score < 75.0
    assert report.dimension_scores["dynamic_health"] <= 10.0
    assert report.dimension_scores["spectral_balance"] <= 15.0

    critical_dynamic = [i for i in report.critical_issues if i.category == "dynamic"]
    assert len(critical_dynamic) >= 1
    assert "True Peak" in critical_dynamic[0].message
    assert critical_dynamic[0].severity == "CRITICAL"

    # Verify remediation DAG includes Master Limiter clamp to -1.0 dBTP
    limiter_recs = [r for r in report.remediation_dag if r.get("parameter") == "Limiter Ceiling"]
    assert len(limiter_recs) == 1
    assert limiter_recs[0]["target_value"] == -1.0


def test_mix_doctor_mono_correlation_penalty():
    doctor = MixDoctor()
    session = _build_synthetic_16_track_session()
    meters = {
        "integrated_lufs": -14.0,
        "true_peak_dbtp": -1.5,
        "phase_correlation": -0.35,  # Destructive out-of-phase!
        "crest_factor_db": 10.0,
        "spectral_energy": {
            "sub_20_60hz": 0.25,
            "low_mid_200_500hz": 0.25,
            "high_mid_2_6khz": 0.25,
            "air_10_20khz": 0.25,
        },
    }

    report = doctor.audit_session(session, meters=meters)

    assert report.dimension_scores["stereo_imaging"] == 5.0  # -15 pt penalty
    stereo_issues = [i for i in report.critical_issues if i.category == "stereo"]
    assert len(stereo_issues) >= 1
    assert "out-of-phase" in stereo_issues[0].message
    assert stereo_issues[0].severity == "CRITICAL"


# E2 step 1 (14 Oct 2026): a missing meter used to be filled with a healthy-looking default (-14 LUFS, -1 dBTP,
# correlation 0.88, 25% in every band), so a session with no meters at all scored a full 100 and an "S".

def test_a_session_with_no_meters_is_not_graded():
    report = MixDoctor().audit_session(_build_synthetic_16_track_session(), meters=None)

    assert report.grade == "UNRATED"
    assert report.dimension_scores["dynamic_health"] is None
    assert report.dimension_scores["spectral_balance"] is None
    assert report.dimension_scores["stereo_imaging"] is None
    # Only the fader-based dimension could be judged, so only its 20 points are on offer.
    assert report.points_available == 20.0
    assert report.mqm_score <= report.points_available


def test_a_missing_reading_stays_missing_in_the_telemetry():
    report = MixDoctor().audit_session(_build_synthetic_16_track_session(), meters={"true_peak_dbtp": -1.5})

    assert report.loudness_telemetry["true_peak_dbtp"] == -1.5
    assert report.loudness_telemetry["integrated_lufs"] is None
    assert "integrated_lufs" in report.unmeasured
    assert "phase_correlation" in report.unmeasured
    assert report.to_dict()["loudness_telemetry"]["phase_correlation"] is None


def test_peak_to_loudness_is_skipped_without_a_loudness_reading():
    # Only a peak reading: the peak check runs, the PLR check has nothing to compare against.
    report = MixDoctor().audit_session(_build_synthetic_16_track_session(), meters={"true_peak_dbtp": -1.5})

    assert report.dimension_scores["dynamic_health"] == 20.0
    assert not [i for i in report.all_issues if "PLR" in i.message]


def test_a_loudness_reading_alone_does_not_earn_the_dynamics_points():
    report = MixDoctor().audit_session(_build_synthetic_16_track_session(), meters={"integrated_lufs": -14.0})

    assert report.dimension_scores["dynamic_health"] is None


def test_a_bad_reading_still_costs_points_when_the_rest_are_missing():
    report = MixDoctor().audit_session(_build_synthetic_16_track_session(), meters={"phase_correlation": -0.4})

    assert report.dimension_scores["stereo_imaging"] == 5.0
    assert report.grade == "UNRATED"
    assert report.points_available == 40.0  # stereo + stem separation
    assert any(i.severity == "CRITICAL" for i in report.critical_issues)


def test_a_full_set_of_meters_is_still_graded_out_of_100():
    meters = {
        "integrated_lufs": -13.8, "true_peak_dbtp": -1.2, "phase_correlation": 0.88,
        "spectral_energy": {"sub_20_60hz": 0.25, "low_mid_200_500hz": 0.26, "high_mid_2_6khz": 0.25, "air_10_20khz": 0.24},
    }
    report = MixDoctor().audit_session(_build_synthetic_16_track_session(), meters=meters)

    assert report.points_available == 100.0
    assert report.grade != "UNRATED"
    assert report.unmeasured == ["crest_factor_db"]  # reported, but no check scores on it today


def test_tracks_without_fader_or_device_data_cost_nothing():
    # Before: no volume read as 0.85 (feeding the collision checks) and no device list read as "no EQ".
    session = {"tracks": [{"index": 0, "name": "Kick"}, {"index": 1, "name": "Sub Bass"}, {"index": 2, "name": "Lead Vocal"},
                          {"index": 3, "name": "Synth Pad"}], "master": {}}

    report = MixDoctor().audit_session(session, meters=None)

    assert report.dimension_scores["stem_separation"] == 20.0
    assert not [i for i in report.all_issues if i.category == "low_end"]


def test_a_non_numeric_meter_value_counts_as_missing():
    report = MixDoctor().audit_session(_build_synthetic_16_track_session(),
                                       meters={"true_peak_dbtp": "n/a", "phase_correlation": float("nan")})

    assert report.loudness_telemetry["true_peak_dbtp"] is None
    assert report.loudness_telemetry["phase_correlation"] is None
