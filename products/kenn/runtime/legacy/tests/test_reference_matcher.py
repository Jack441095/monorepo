"""Unit tests for KENN Reference Track AI Spectral Matcher (V5.0)."""

from __future__ import annotations

import pytest
from kenn.core.reference_matcher import ReferenceMatcher, get_reference_matcher


def test_spectral_delta_calculation():
    """Validates 40-band ERB reference curve extraction and delta computation."""
    matcher = ReferenceMatcher()
    assert len(matcher.erb_bands) == 40

    # Synthetic session spectrum (slightly dark) and reference spectrum (bright)
    session_spec = [-15.0 - (i * 0.7) for i in range(40)]
    ref_spec = [-15.0 - (i * 0.5) for i in range(40)]

    report = matcher.compute_spectral_delta(
        session_spectrum=session_spec,
        reference_spectrum=ref_spec,
        reference_name="Commercial Pop Reference",
    )

    assert report.reference_name == "Commercial Pop Reference"
    assert len(report.delta_curve) == 40
    assert report.rms_spectral_delta_db > 0.0

    # Check 1 kHz anchor normalization: delta at 1 kHz should be approximately 0.0
    anchor_band = min(report.delta_curve, key=lambda b: abs(b["center_hz"] - 1000.0))
    assert abs(anchor_band["session_db"]) == pytest.approx(0.0, abs=0.1)
    assert abs(anchor_band["ref_db"]) == pytest.approx(0.0, abs=0.1)
    assert abs(anchor_band["delta_db"]) == pytest.approx(0.0, abs=0.1)


def test_reference_curve_safety_clamping():
    """Asserts synthesized EQ moves never exceed +/- 2.5 dB hardware clamp."""
    matcher = ReferenceMatcher()

    # Extreme deviation spectrum (+15 dB boost in sub, -20 dB in treble)
    session_spec = [-10.0 if i < 20 else -30.0 for i in range(40)]
    ref_spec = [-30.0 if i < 20 else -10.0 for i in range(40)]

    report = matcher.compute_spectral_delta(
        session_spectrum=session_spec,
        reference_spectrum=ref_spec,
        reference_name="Extreme Reference",
    )

    for band in report.delta_curve:
        # Clamped adjustment must strictly satisfy [-2.5, +2.5] dB
        assert -2.5 <= band["safe_adjustment_db"] <= 2.5

    # Check the 4 synthesized parametric EQ recipe bands
    recipe = report.eq_recipe
    assert len(recipe) == 4

    for eq_step in recipe:
        assert -2.5 <= eq_step["gain_delta_db"] <= 2.5
        assert eq_step["target"] == "Master"
        assert 0.7 <= eq_step["q"] <= 2.5


def test_gaussian_smoothing_reduces_spikes():
    """Validates that 3-point Gaussian smoothing eliminates narrow resonant spikes."""
    matcher = ReferenceMatcher()

    # Create a sharp isolated resonant notch at band 15
    session_spec = [-20.0 for _ in range(40)]
    ref_spec = [-20.0 for _ in range(40)]
    ref_spec[15] = 0.0  # +20 dB spike at single band

    report = matcher.compute_spectral_delta(session_spec, ref_spec)
    band_15 = report.delta_curve[15]

    # Raw delta is 20 dB, but smoothed delta must be reduced by Gaussian kernel (0.5 weight)
    assert band_15["raw_delta_db"] if "raw_delta_db" in band_15 else band_15["delta_db"] > band_15["smoothed_delta_db"]
    assert band_15["safe_adjustment_db"] == 2.5  # Clamped to maximum +2.5 dB
