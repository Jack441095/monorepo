"""Tests for analysis_core/waveform.py's downsampled peaks computation."""

from __future__ import annotations

import numpy as np

from audio_analysis.analysis_core.waveform import (
    DEFAULT_POINTS,
    MAX_POINTS,
    MIN_POINTS,
    compute_waveform_peaks,
)

SR = 44100


def test_returns_requested_point_count_for_a_long_track():
    samples = np.sin(2 * np.pi * 440 * np.arange(SR * 10) / SR)  # 10 seconds

    result = compute_waveform_peaks(samples, SR, target_points=500)

    assert result["points"] == 500
    assert len(result["peaks"]) == 500
    assert result["sample_rate"] == SR
    assert result["duration_seconds"] == 10.0


def test_peaks_are_bounded_within_the_true_signal_range():
    samples = 0.4 * np.sin(2 * np.pi * 440 * np.arange(SR * 2) / SR)

    result = compute_waveform_peaks(samples, SR, target_points=100)

    for lo, hi in result["peaks"]:
        assert -0.41 <= lo <= 0.41
        assert -0.41 <= hi <= 0.41
        assert lo <= hi


def test_a_loud_transient_is_captured_even_in_a_quiet_track():
    samples = np.zeros(SR * 5)
    samples[SR * 2] = 0.9  # one loud sample buried in silence
    result = compute_waveform_peaks(samples, SR, target_points=200)

    assert max(hi for _lo, hi in result["peaks"]) >= 0.89


def test_target_points_is_clamped_to_the_valid_range():
    samples = np.zeros(SR * 3)

    too_few = compute_waveform_peaks(samples, SR, target_points=1)
    too_many = compute_waveform_peaks(samples, SR, target_points=10_000_000)

    assert too_few["points"] >= MIN_POINTS
    assert too_many["points"] <= MAX_POINTS


def test_default_target_points_matches_the_documented_default():
    samples = np.zeros(SR * 30)
    result = compute_waveform_peaks(samples, SR)
    assert result["points"] == DEFAULT_POINTS


def test_empty_samples_returns_an_empty_peaks_list_not_an_error():
    result = compute_waveform_peaks(np.array([]), SR)
    assert result == {"sample_rate": SR, "duration_seconds": 0.0, "points": 0, "peaks": []}


def test_short_clip_shorter_than_min_points_does_not_crash():
    samples = np.linspace(-0.5, 0.5, 10)
    result = compute_waveform_peaks(samples, SR, target_points=800)
    assert 0 < result["points"] <= 10
