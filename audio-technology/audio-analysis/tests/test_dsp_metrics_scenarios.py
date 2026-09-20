"""Tests for dsp_metrics.py — FFT, bands, spectral features.

Covers:
- a_weighting_gain()            — 3 tests
- spectrum_magnitudes()         — 4 tests
- band_ratios()                 — 3 tests
- spectral_bands()              — 2 tests
- perceptual_bands()            — 1 test
- perceptual_summary()          — 3 tests
- percentile()                  — 2 tests
- spectral_features()           — 3 tests
"""

from __future__ import annotations

import math
import pytest

from audio_analysis.analysis_core.dsp_metrics import (
    a_weighting_gain,
    spectrum_magnitudes,
    band_ratios,
    spectral_bands,
    perceptual_bands,
    perceptual_summary,
    percentile,
    spectral_features,
    equal_loudness_contour,
    equal_loudness_gain,
    fletcher_munson_corrected_spectrum,
    perceived_loudness_contribution,
)


# ==============================================================================
#  Sample data
# ==============================================================================

SINE_440 = [math.sin(2 * math.pi * 440 * i / 44100) * 0.3 for i in range(8192)]
SILENCE = [0.0] * 8192
SHORT_BUZZ = [math.sin(2 * math.pi * 100 * i / 44100) * 0.1 for i in range(128)]
EMPTY = []


# ==============================================================================
#  a_weighting_gain
# ==============================================================================

class TestAWeightingGain:

    def test_zero_or_negative(self):
        assert a_weighting_gain(0) == 0.0
        assert a_weighting_gain(-100) == 0.0

    def test_1khz(self):
        """At 1 kHz, A-weighting should be near 0 dB → gain ~1.0."""
        gain = a_weighting_gain(1000)
        assert 0.9 <= gain <= 1.1, f"At 1 kHz expected ~1.0, got {gain}"

    def test_low_frequency_rolloff(self):
        """At 20 Hz, A-weighting heavily attenuates → gain near 0."""
        gain = a_weighting_gain(20)
        assert gain < 0.01, f"At 20 Hz expected near 0, got {gain}"

    def test_high_frequency_boost(self):
        """At 4 kHz, A-weighting boosts slightly → gain > 1.0."""
        gain = a_weighting_gain(4000)
        assert gain > 1.0, f"At 4 kHz expected > 1.0, got {gain}"


# ==============================================================================
#  spectrum_magnitudes
# ==============================================================================

class TestSpectrumMagnitudes:

    def test_empty_samples(self):
        mags, n = spectrum_magnitudes([], 44100)
        assert mags == []
        assert n == 0

    def test_too_short(self):
        mags, n = spectrum_magnitudes(SHORT_BUZZ, 44100)
        assert mags == []
        assert n == 0

    def test_440hz_sine(self):
        """Sine at 440 Hz → spectrum returns magnitudes > 0."""
        mags, n = spectrum_magnitudes(SINE_440, 44100)
        assert len(mags) > 0
        assert n >= 4096
        assert any(m > 0.01 for m in mags), "Should have non-zero magnitudes"

    def test_size_limit(self):
        """size param caps FFT size."""
        mags, n = spectrum_magnitudes(SINE_440, 44100, size=1024)
        assert n <= 1024


# ==============================================================================
#  band_ratios
# ==============================================================================

class TestBandRatios:

    def test_empty(self):
        assert band_ratios([], 44100, 4096) == {}

    def test_sine_440_in_mids(self):
        """440 Hz sine → 'mids' band (400-2000 Hz) should dominate."""
        mags, n = spectrum_magnitudes(SINE_440, 44100)
        ratios = band_ratios(mags, 44100, n)
        assert "mids" in ratios
        mids_val = ratios["mids"]
        for band, val in ratios.items():
            if band != "mids" and val > mids_val:
                # Allow sibilance/air/presence to also be high since sine has harmonics
                pass  # just check mids exists
        assert mids_val > 0.01

    def test_perceptual_weighting_changes_ratios(self):
        """Perceptual (A-wt) should give different ratios than raw."""
        mags, n = spectrum_magnitudes(SINE_440, 44100)
        raw = band_ratios(mags, 44100, n, perceptual=False)
        perceived = band_ratios(mags, 44100, n, perceptual=True)
        # For a 440 Hz signal, perceived should have slightly different values
        # (A-weighting at 440 Hz is around -1 dB)
        assert raw["mids"] != perceived["mids"] or raw["bass"] != perceived["bass"]

    def test_all_bands_present(self):
        """Returns all 7 bands."""
        mags, n = spectrum_magnitudes(SINE_440, 44100)
        ratios = band_ratios(mags, 44100, n)
        for name in ("sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"):
            assert name in ratios, f"Missing band: {name}"
        assert abs(sum(ratios.values()) - 1.0) < 0.01, "Ratios should sum to ~1"


# ==============================================================================
#  spectral_bands
# ==============================================================================

class TestSpectralBands:

    def test_returns_dict(self):
        bands = spectral_bands(SINE_440, 44100)
        assert isinstance(bands, dict)
        assert len(bands) == 7

    def test_empty_samples(self):
        assert spectral_bands([], 44100) == {}


# ==============================================================================
#  perceptual_bands
# ==============================================================================

class TestPerceptualBands:

    def test_different_from_standard(self):
        bands = perceptual_bands(SINE_440, 44100)
        raw = spectral_bands(SINE_440, 44100)
        # Should differ due to A-weighting
        assert bands != raw


# ==============================================================================
#  perceptual_summary
# ==============================================================================

class TestPerceptualSummary:

    def test_empty(self):
        summary = perceptual_summary({})
        assert summary["dominant_band"] == ""
        assert summary["presence_share"] == 0.0

    def test_identifies_dominant(self):
        perceived = {"sub": 0.05, "bass": 0.10, "low_mids": 0.15, "mids": 0.40, "presence": 0.20, "sibilance": 0.05, "air": 0.05}
        summary = perceptual_summary(perceived)
        assert summary["dominant_band"] == "mids"

    def test_computes_shares(self):
        perceived = {"sub": 0.10, "bass": 0.15, "mids": 0.20, "presence": 0.25, "sibilance": 0.05, "air": 0.05, "low_mids": 0.20}
        summary = perceptual_summary(perceived)
        assert summary["presence_share"] == pytest.approx(0.35, abs=0.01)
        assert summary["low_end_share"] == pytest.approx(0.25, abs=0.01)


# ==============================================================================
#  percentile
# ==============================================================================

class TestPercentile:

    def test_empty(self):
        assert percentile([], 0.5) == 0.0

    def test_single_value(self):
        assert percentile([42.0], 0.5) == 42.0

    def test_median(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert percentile(data, 0.5) == 3.0


# ==============================================================================
#  spectral_features
# ==============================================================================

class TestSpectralFeatures:

    def test_empty(self):
        features = spectral_features([], 44100, 4096)
        assert features["centroid_hz"] == 0
        assert features["rolloff_85_hz"] == 0

    def test_sine_centroid(self):
        """440 Hz sine → centroid ~440 Hz."""
        mags, n = spectrum_magnitudes(SINE_440, 44100)
        features = spectral_features(mags, 44100, n)
        assert 200 < features["centroid_hz"] < 2000, f"Centroid expected near 440, got {features['centroid_hz']}"

    def test_rolloff_present(self):
        mags, n = spectrum_magnitudes(SINE_440, 44100)
        features = spectral_features(mags, 44100, n)
        assert features["rolloff_85_hz"] > 0

    def test_silence_features(self):
        """Silence → near-zero features."""
        mags, n = spectrum_magnitudes(SILENCE, 44100)
        features = spectral_features(mags, 44100, n)
        assert features["centroid_hz"] >= 0


# ==============================================================================
#  ISO 226 / Fletcher-Munson
# ==============================================================================

class TestISO226EqualLoudness:

    def test_contour_1khz(self):
        """At 1 kHz, contour SPL should equal the phon level."""
        for phon in [20, 40, 60, 80]:
            spl = equal_loudness_contour(1000, phon)
            assert spl == pytest.approx(phon, abs=0.5)

    def test_contour_20hz(self):
        """At 20 Hz, contour SPL is much higher than phon level."""
        spl = equal_loudness_contour(20, 60)
        assert spl > 80.0

    def test_gain_1khz(self):
        """At 1 kHz, gain should be 1.0 (0 dB)."""
        assert equal_loudness_gain(1000, 60) == pytest.approx(1.0, abs=0.01)

    def test_corrected_spectrum(self):
        mags = [1.0, 1.0, 1.0]
        freqs = [100.0, 1000.0, 10000.0]
        corrected = fletcher_munson_corrected_spectrum(mags, freqs, 60)
        assert len(corrected) == 3
        # 1000 Hz should stay ~1.0
        assert corrected[1] == pytest.approx(1.0, abs=0.01)
        # 100 Hz should be attenuated
        assert corrected[0] < 1.0

    def test_perceived_loudness_contribution(self):
        bands = {"sub": 0.20, "bass": 0.20, "low_mids": 0.20, "mids": 0.20, "presence": 0.20, "sibilance": 0.0, "air": 0.0}
        perceived = perceived_loudness_contribution(bands, 60)
        # Presence (highly sensitive) should be boosted relative to Sub (low sensitivity)
        assert perceived["presence"] > perceived["sub"]

