"""Unit tests for KENN Autonomous Mastering Engine (V5.0)."""

from __future__ import annotations

import pytest
from kenn.core.mastering_engine import MasteringEngine, get_mastering_engine, PROFILES


def test_mastering_profiles_compliance():
    """Asserts each delivery profile generates compliant LUFS and True Peak targets."""
    engine = MasteringEngine()
    profiles = engine.get_supported_profiles()

    assert "SPOTIFY_STREAMING" in profiles
    assert "APPLE_DIGITAL_MASTER" in profiles
    assert "CLUB_FESTIVAL" in profiles
    assert "DYNAMIC_ACOUSTIC" in profiles

    # 1. Spotify Target Check (-14.0 LUFS, -1.0 dBTP)
    spotify = profiles["SPOTIFY_STREAMING"]
    assert spotify.target_integrated_lufs == -14.0
    assert spotify.max_true_peak_dbtp == -1.0
    assert spotify.target_crest_factor_db >= 8.0

    # 2. Apple Digital Master (-16.0 LUFS, -1.0 dBTP)
    apple = profiles["APPLE_DIGITAL_MASTER"]
    assert apple.target_integrated_lufs == -16.0
    assert apple.max_true_peak_dbtp == -1.0
    assert apple.limiter_lookahead_ms >= 3.0

    # 3. Club / Festival (-8.5 LUFS, -0.3 dBTP)
    club = profiles["CLUB_FESTIVAL"]
    assert club.target_integrated_lufs == -8.5
    assert club.max_true_peak_dbtp == -0.3

    # 4. Dynamic Acoustic (-18.0 LUFS, -1.5 dBTP)
    acoustic = profiles["DYNAMIC_ACOUSTIC"]
    assert acoustic.target_integrated_lufs == -18.0
    assert acoustic.max_true_peak_dbtp == -1.5


def test_mastering_chain_dag_synthesis():
    """Asserts 5-stage mastering DAG adheres strictly to safety clamping."""
    engine = get_mastering_engine()
    meters = {
        "integrated_lufs": -22.0,
        "true_peak_dbtp": -3.5,
        "spectral_energy": {"low_mid_200_500hz": 0.40},
    }

    report = engine.synthesize_mastering_dag("SPOTIFY_STREAMING", meters=meters)
    dag = report.mastering_dag

    # Must generate 5 distinct stages
    assert len(dag) == 5
    stages = [step["stage"] for step in dag]
    assert stages == [1, 2, 3, 4, 5]

    # Stage 1: Subsonic filter (< 25 Hz)
    s1 = dag[0]
    assert s1["stage"] == 1
    assert s1["device_type"] == "Eq8"
    assert s1["frequency_hz"] <= 25.0
    assert s1["filter_type"] == "HighPass18"

    # Stage 2: Mid/Side Mono Bass (< 120 Hz)
    s2 = dag[1]
    assert s2["stage"] == 2
    assert s2["device_type"] == "Utility"
    assert s2["parameter"] == "Bass Mono"
    assert s2["frequency_hz"] == 120.0

    # Stage 3: Surgical Tonal Balance (310 Hz mud cut)
    s3 = dag[2]
    assert s3["stage"] == 3
    assert s3["device_type"] == "Eq8"
    assert s3["frequency_hz"] == 310.0
    assert -2.5 <= s3["gain_db"] <= 0.0

    # Stage 4: Analog Harmonic Saturation
    s4 = dag[3]
    assert s4["stage"] == 4
    assert s4["device_type"] == "Saturator"
    assert 0.05 <= s4["drive"] <= 0.20

    # Stage 5: True Peak Lookahead Limiter Calibration
    s5 = dag[4]
    assert s5["stage"] == 5
    assert s5["device_type"] == "Limiter"
    assert s5["value"] == -1.0  # Clamped to Spotify profile True Peak
    assert s5["lookahead_ms"] == 3.0
    # Safe gain boost clamp: delta should be clamped <= 3.0 dB
    assert s5["gain_boost_db"] <= 3.0


def test_mastering_gain_deficit_clamping():
    """Asserts that extreme LUFS deficit is clamped within safe gain delta limits."""
    engine = MasteringEngine()
    # Extremely quiet session (-40 LUFS)
    quiet_meters = {"integrated_lufs": -40.0}
    report = engine.synthesize_mastering_dag("SPOTIFY_STREAMING", meters=quiet_meters)
    # Deficit is +26 dB, but safe boost must be clamped to +3.0 dB
    assert report.estimated_gain_change_db == 3.0

