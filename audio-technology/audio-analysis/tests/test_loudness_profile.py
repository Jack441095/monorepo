"""Tests for BS.1770-4 gated loudness and LRA companion metrics.

Covers:
- loudness: calculate_loudness_profile_fallback, calculate_loudness_profile_numpy, calculate_loudness_profile
- analysis_interpretation: review_flags() for over-compression, dynamics, and spikes
- mix_features: extract_feature_vector() with new metrics
"""

from __future__ import annotations

import math

# Try to import numpy
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from audio_analysis.analysis_core.loudness import (
    calculate_loudness_profile,
    calculate_loudness_profile_fallback,
    calculate_loudness_profile_numpy,
)
from audio_analysis.analysis_core.analysis_interpretation import review_flags, LESSON_LIBRARY
from mix_features import extract_feature_vector, FEATURE_VECTOR_KEYS
from audio_analysis.analysis_core.anomaly_detector import ANOMALY_FEATURES
from audio_analysis.integration.quality_predictor import QUALITY_FEATURES


def _generate_sine(freq: float, fs: int, duration: float, amp: float) -> tuple[list[float], list[float]]:
    """Helper to generate a stereo sine wave."""
    n = int(fs * duration)
    samples = [amp * math.sin(2.0 * math.pi * freq * i / fs) for i in range(n)]
    return list(samples), list(samples)  # mono-in-stereo


class TestLoudnessProfileCorrectness:
    """Correctness tests for calculate_loudness_profile with various inputs."""

    def test_constant_sine(self):
        """Constant amplitude sine tone should have steady loudness and low LRA."""
        fs = 16000  # low sample rate for fast test execution
        left, right = _generate_sine(1000.0, fs, 5.0, 0.2)  # 5 seconds

        # Fallback path
        res_fb = calculate_loudness_profile_fallback(left, right, fs)
        assert isinstance(res_fb, dict)
        assert res_fb["integrated_lufs"] != -99.0
        assert res_fb["momentary_max_lufs"] != -99.0
        assert res_fb["short_term_max_lufs"] != -99.0
        assert abs(res_fb["momentary_max_lufs"] - res_fb["short_term_max_lufs"]) < 2.0
        assert res_fb["loudness_range_lu"] < 1.0

        # NumPy path (if available)
        if HAS_NUMPY:
            res_np = calculate_loudness_profile_numpy(np.array(left), np.array(right), fs)
            assert isinstance(res_np, dict)
            assert abs(res_fb["integrated_lufs"] - res_np["integrated_lufs"]) < 0.5
            assert abs(res_fb["momentary_max_lufs"] - res_np["momentary_max_lufs"]) < 0.5
            assert abs(res_fb["short_term_max_lufs"] - res_np["short_term_max_lufs"]) < 0.5
            assert abs(res_fb["loudness_range_lu"] - res_np["loudness_range_lu"]) < 0.5

        # Dynamic selection path
        res = calculate_loudness_profile(left, right, fs)
        assert res["integrated_lufs"] != -99.0
        assert res["loudness_range_lu"] < 1.0

    def test_quiet_then_loud_signal(self):
        """Dynamic signal should produce significant LRA."""
        fs = 16000
        # 4 seconds quiet, 4 seconds loud
        left_q, right_q = _generate_sine(1000.0, fs, 4.0, 0.02)
        left_l, right_l = _generate_sine(1000.0, fs, 4.0, 0.4)
        left = left_q + left_l
        right = right_q + right_l

        res_fb = calculate_loudness_profile_fallback(left, right, fs)
        assert res_fb["loudness_range_lu"] > 5.0
        assert res_fb["momentary_max_lufs"] > res_fb["integrated_lufs"]

        if HAS_NUMPY:
            res_np = calculate_loudness_profile_numpy(np.array(left), np.array(right), fs)
            assert res_np["loudness_range_lu"] > 5.0
            assert abs(res_fb["loudness_range_lu"] - res_np["loudness_range_lu"]) < 1.0

    def test_very_quiet_signal(self):
        """Zeros / silent signal should return empty/fallback values below gate."""
        fs = 16000
        left = [0.0] * (fs * 4)
        right = [0.0] * (fs * 4)

        res_fb = calculate_loudness_profile_fallback(left, right, fs)
        assert res_fb["integrated_lufs"] == -99.0
        assert res_fb["momentary_max_lufs"] == -99.0
        assert res_fb["short_term_max_lufs"] == -99.0
        assert res_fb["loudness_range_lu"] == 0.0

        if HAS_NUMPY:
            res_np = calculate_loudness_profile_numpy(np.array(left), np.array(right), fs)
            assert res_np["integrated_lufs"] == -99.0
            assert res_np["momentary_max_lufs"] == -99.0
            assert res_np["short_term_max_lufs"] == -99.0
            assert res_np["loudness_range_lu"] == 0.0

    def test_short_file(self):
        """File shorter than 3s should fallback and return 0 LRA."""
        fs = 16000
        left, right = _generate_sine(1000.0, fs, 1.5, 0.2)  # 1.5s

        res_fb = calculate_loudness_profile_fallback(left, right, fs)
        assert res_fb["loudness_range_lu"] == 0.0
        assert res_fb["short_term_max_lufs"] == res_fb["momentary_max_lufs"]

        if HAS_NUMPY:
            res_np = calculate_loudness_profile_numpy(np.array(left), np.array(right), fs)
            assert res_np["loudness_range_lu"] == 0.0
            assert res_np["short_term_max_lufs"] == res_np["momentary_max_lufs"]


class TestLoudnessFlagsAndInterpretation:
    """Tests for interpretation flags matching EBU R128 loudness metrics."""

    def test_flag_over_compressed_lra(self):
        """Low LRA triggers Over-compressed (LRA) flag."""
        metrics = {
            "integrated_lufs": -10.0,
            "momentary_max_lufs": -9.0,
            "short_term_max_lufs": -9.5,
            "loudness_range_lu": 1.5,  # Below minimum (2.0 default as of the 2026-07-17 calibration pass)
            "mix_goal": {"key": "master", "label": "master", "target": "master"},
        }
        flags = review_flags(metrics)
        assert any(f["label"] == "Over-compressed (LRA)" for f in flags)
        assert "Over-compressed (LRA)" in LESSON_LIBRARY

    def test_flag_very_dynamic(self):
        """High LRA triggers Very dynamic flag."""
        metrics = {
            "integrated_lufs": -24.0,
            "momentary_max_lufs": -14.0,
            "short_term_max_lufs": -16.0,
            "loudness_range_lu": 18.0,  # Above maximum (15.0 default)
            "mix_goal": {"key": "master", "label": "master", "target": "master"},
        }
        flags = review_flags(metrics)
        assert any(f["label"] == "Very dynamic" for f in flags)
        assert "Very dynamic" in LESSON_LIBRARY

    def test_flag_loudness_spike(self):
        """Momentary max significantly higher than integrated triggers Loudness spike."""
        metrics = {
            "integrated_lufs": -16.0,
            "momentary_max_lufs": -3.0,  # Spike of 13.0 LU > 12.0
            "short_term_max_lufs": -10.0,
            "loudness_range_lu": 5.0,
            "mix_goal": {"key": "master", "label": "master", "target": "master"},
        }
        flags = review_flags(metrics)
        assert any(f["label"] == "Loudness spike" for f in flags)
        assert "Loudness spike" in LESSON_LIBRARY


class TestMLPipelineIntegration:
    """Verifies that the new features are present in the ML/feature vectors and models."""

    def test_feature_vector_extraction(self):
        """Extracted feature vector should include the new loudness metrics."""
        metrics = {
            "duration_seconds": 120.0,
            "sample_rate": 44100,
            "peak_dbfs": -3.0,
            "left_peak_dbfs": -3.5,
            "right_peak_dbfs": -3.5,
            "rms_dbfs_estimate": -18.0,
            "loudest_section_rms_dbfs": -12.0,
            "dynamic_range_estimate_db": 28.0,
            "crest_factor_db": 15.0,
            "true_peak_dbfs": -2.5,
            "integrated_lufs": -15.0,
            "momentary_max_lufs": -11.5,
            "short_term_max_lufs": -12.5,
            "loudness_range_lu": 6.5,
            "leading_silence_seconds": 0.05,
            "trailing_silence_seconds": 0.1,
            "stereo_balance": 1.0,
            "stereo_correlation": 0.8,
            "stereo_width_ratio": 0.5,
            "dc_offset": 0.001,
            "clipping_risk": False,
            "clipped_frames_estimate": 0,
            "technical_score": 85,
            "mix_goal": {"key": "premaster", "label": "premaster", "target": "premaster"},
        }
        vec = extract_feature_vector(metrics)
        assert vec["momentary_max_lufs"] == -11.5
        assert vec["short_term_max_lufs"] == -12.5
        assert vec["loudness_range_lu"] == 6.5

        # Check in FEATURE_VECTOR_KEYS
        assert "momentary_max_lufs" in FEATURE_VECTOR_KEYS
        assert "short_term_max_lufs" in FEATURE_VECTOR_KEYS
        assert "loudness_range_lu" in FEATURE_VECTOR_KEYS

    def test_anomaly_and_quality_features_list(self):
        """Anomaly detector and quality predictor should expect the new keys."""
        assert "momentary_max_lufs" in ANOMALY_FEATURES
        assert "short_term_max_lufs" in ANOMALY_FEATURES
        assert "loudness_range_lu" in ANOMALY_FEATURES

        assert "momentary_max_lufs" in QUALITY_FEATURES
        assert "short_term_max_lufs" in QUALITY_FEATURES
        assert "loudness_range_lu" in QUALITY_FEATURES
