"""Unit tests for KENN Vocal Resonance & Sibilance Surgeon (V6.0)."""

from __future__ import annotations

import pytest
from kenn.core.vocal_surgeon import VocalSurgeon, get_vocal_surgeon


def test_harshness_detection_and_dynamic_notch():
    """Validates 2.5–4.5 kHz resonance detection and dynamic notch synthesis."""
    surgeon = VocalSurgeon()
    peaks = [
        {"frequency": 3300.0, "prominence": 4.8},  # Vocal harshness
        {"frequency": 7500.0, "prominence": 5.0},  # Sibilance
    ]

    report = surgeon.audit_vocal_track("Lead Vocal Main", spectral_peaks=peaks)

    assert report.anomalies_detected == 2
    harsh = next((a for a in report.anomalies if a.anomaly_type == "HARSHNESS_RESONANCE"), None)
    assert harsh is not None
    assert harsh.center_frequency_hz == 3300.0
    assert -3.0 <= harsh.recommended_cut_db <= -1.0
    assert 3.5 <= harsh.recommended_q <= 8.0


def test_sibilance_burst_suppression():
    """Validates 6.0–9.0 kHz burst detection and dynamic notch cut."""
    surgeon = get_vocal_surgeon()
    peaks = [
        {"frequency": 7800.0, "prominence": 6.0}
    ]

    report = surgeon.audit_vocal_track("Lead Vocal Vox", spectral_peaks=peaks)

    assert report.anomalies_detected == 1
    sib = report.anomalies[0]
    assert sib.anomaly_type == "SIBILANCE_BURST"
    assert sib.center_frequency_hz == 7800.0
    assert sib.recommended_cut_db == -3.0  # Clamped to safe maximum -3.0 dB
    assert sib.recommended_q >= 4.5


def test_vocal_notch_q_and_gain_clamping():
    """Asserts gain cut never exceeds -3.0 dB and Q remains in [3.5, 8.0] range."""
    surgeon = VocalSurgeon()
    extreme_peaks = [
        {"frequency": 3800.0, "prominence": 15.0}  # Excessive spike
    ]

    report = surgeon.audit_vocal_track("Screaming Vocal", spectral_peaks=extreme_peaks)
    assert len(report.eq_recipe) == 1

    recipe_step = report.eq_recipe[0]
    assert recipe_step["gain_db"] >= -3.0  # Clamped to -3.0 dB
    assert 3.5 <= recipe_step["q"] <= 8.0
    assert recipe_step["frequency_hz"] == 3800.0
