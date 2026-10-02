"""Unit tests for KENN Reference Track AI Spectral Matcher (V5.0)."""

from __future__ import annotations

import json
import math

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


@pytest.mark.parametrize(
    "session, reference",
    [
        (None, None),
        ([], []),
        ([], [-20.0] * 40),
        ([-20.0] * 40, []),
        (None, [-20.0] * 40),
        ([-20.0] * 40, None),
        ([-20.0] * 39, [-20.0] * 40),
        ([-20.0] * 40, [-20.0]),
        ([-20.0] * 41, [-20.0] * 40),
        ("x" * 40, [-20.0] * 40),
        ({}, [-20.0] * 40),
        ([None] * 40, [-20.0] * 40),
        ([True] * 40, [-20.0] * 40),
        (["-20.0"] * 40, [-20.0] * 40),
        ([-20.0] * 40, [float("nan")] * 40),
        ([float("inf")] * 40, [-20.0] * 40),
        ([-20.0] * 40, [float("-inf")] * 40),
    ],
)
def test_missing_invalid_or_incomplete_spectra_have_no_finding_or_recipe(session, reference):
    # Empty input used to fabricate a commercial-reference comparison and four EQ moves.
    report = ReferenceMatcher().compute_spectral_delta(session, reference, "Missing reference")
    result = report.to_dict()
    assert result["available"] is False
    assert result["reference_name"] == "Missing reference"
    assert result["diagnostic_reason"]
    assert result["delta_curve"] == []
    assert result["eq_recipe"] == []
    assert result["rms_spectral_delta_db"] is None
    json.dumps(result, allow_nan=False)


def test_nonfinite_normalized_delta_is_unavailable():
    matcher = ReferenceMatcher()
    anchor = min(range(40), key=lambda i: abs(matcher.erb_bands[i][0] - 1000.0))
    session = [-1e308] * 40
    session[anchor] = 1e308
    report = matcher.compute_spectral_delta(session, [-20.0] * 40)
    assert report.available is False
    assert report.eq_recipe == []
    assert report.rms_spectral_delta_db is None


def test_measured_erb_spectra_of_the_same_audio_ignore_overall_gain():
    # A real FFT-derived comparison must still work after rejecting missing data.
    import numpy as np
    from kenn.core.psychoacoustics import compute_erb_spectrum

    samples = np.random.default_rng(21).normal(0.0, 0.1, 8192)

    def measured_spectrum(audio):
        magnitudes = np.abs(np.fft.rfft(audio)).tolist()
        powers = compute_erb_spectrum(magnitudes, sample_rate=48000, fft_size=len(audio))
        return [10.0 * math.log10(power) for power in powers]

    session = measured_spectrum(samples)
    reference = measured_spectrum(samples * 2.0)
    before = list(session), list(reference)
    report = get_reference_matcher().compute_spectral_delta(session, reference, "Gain-offset fixture")
    assert report.available is True
    assert report.rms_spectral_delta_db == pytest.approx(0.0, abs=1e-12)
    assert len(report.delta_curve) == 40
    assert all(abs(step["gain_delta_db"]) < 1e-12 for step in report.eq_recipe)
    assert (session, reference) == before

    missing = get_reference_matcher().compute_spectral_delta([], [], "Different request")
    assert missing.available is False
    assert missing.delta_curve == []
    assert report.reference_name == "Gain-offset fixture"
    assert len(report.delta_curve) == 40
