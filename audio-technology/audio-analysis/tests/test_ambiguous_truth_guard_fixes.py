"""Regression guard for the "ambiguous truth value" class of bug: an empty-input
guard written as ``if not samples`` raises ``ValueError: The truth value of an
array with more than one element is ambiguous`` the moment a numpy ndarray with
more than one element is passed in (numpy refuses to coerce a multi-element
array to a single bool).

``log_band_ratios_track_average`` (dsp_metrics.py) and ``stereo_image_analysis``
(stereo_analysis.py) both had this bug -- found because their callers in
spectral_match.py (compute_reference_match_bands / compute_reference_width_factor)
call ``read_wav_mono(..., as_arrays=True)`` to avoid a slow list<->array round
trip, which hands these functions ndarray samples. Fixed to guard with an
explicit ``len(...) == 0`` / ``is None`` check instead, matching the
already-correct idiom used by ``spectrum_magnitudes`` in the same dsp_metrics.py
module.

These tests pin: (a) the guard no longer raises on ndarray input, and (b) list
input and ndarray input of the same data produce IDENTICAL output -- this is a
guard fix, not a numeric change, so there is no tolerance here.
"""

from __future__ import annotations

import math

import numpy as np

from audio_analysis.analysis_core.dsp_metrics import log_band_ratios_track_average
from audio_analysis.analysis_core.stereo_analysis import stereo_image_analysis


SR = 44100


def _sine(freq: float, seconds: float, amp: float = 0.4, sr: int = SR) -> list[float]:
    n = int(sr * seconds)
    return [amp * math.sin(2.0 * math.pi * freq * i / sr) for i in range(n)]


# ---------------------------------------------------------------------------
# log_band_ratios_track_average
# ---------------------------------------------------------------------------

class TestLogBandRatiosTrackAverageNdarrayGuard:

    def test_ndarray_input_does_not_raise(self):
        samples = np.asarray(_sine(220.0, 3.0), dtype=np.float64)
        # Pre-fix this raised: "ValueError: The truth value of an array with
        # more than one element is ambiguous."
        result = log_band_ratios_track_average(samples, SR)
        assert len(result) == 40

    def test_list_and_ndarray_give_identical_output(self):
        samples_list = _sine(220.0, 3.0)
        samples_arr = np.asarray(samples_list, dtype=np.float64)

        from_list = log_band_ratios_track_average(samples_list, SR)
        from_array = log_band_ratios_track_average(samples_arr, SR)

        assert from_list == from_array

    def test_list_and_ndarray_identical_for_short_signal_path(self):
        # Exercises the `total_samples < window_size` early-return branch too.
        samples_list = _sine(220.0, 0.02)  # well under window_size=4096
        samples_arr = np.asarray(samples_list, dtype=np.float64)

        assert log_band_ratios_track_average(samples_list, SR) == log_band_ratios_track_average(samples_arr, SR)

    def test_empty_list_returns_zeros(self):
        assert log_band_ratios_track_average([], SR) == [0.0] * 40

    def test_empty_ndarray_returns_zeros(self):
        # The exact case that used to crash: `not np.array([])` is fine (False,
        # numpy special-cases zero/one-element arrays), but the bug was for
        # *non-empty* arrays -- covered by test_ndarray_input_does_not_raise.
        # Still worth pinning the empty-array path explicitly.
        assert log_band_ratios_track_average(np.asarray([], dtype=np.float64), SR) == [0.0] * 40

    def test_none_samples_returns_zeros(self):
        assert log_band_ratios_track_average(None, SR) == [0.0] * 40

    def test_non_positive_sample_rate_returns_zeros(self):
        samples = np.asarray(_sine(220.0, 1.0), dtype=np.float64)
        assert log_band_ratios_track_average(samples, 0) == [0.0] * 40
        assert log_band_ratios_track_average(samples, -1) == [0.0] * 40


# ---------------------------------------------------------------------------
# stereo_image_analysis
# ---------------------------------------------------------------------------

class TestStereoImageAnalysisNdarrayGuard:

    def test_ndarray_input_does_not_raise(self):
        left = np.asarray(_sine(440.0, 2.0), dtype=np.float64)
        right = np.asarray(_sine(445.0, 2.0), dtype=np.float64)
        # Pre-fix this raised the same ambiguous-truth-value ValueError.
        result = stereo_image_analysis(left, right, SR)
        assert "overall_correlation" in result

    def test_list_and_ndarray_give_identical_output(self):
        left_list = _sine(440.0, 2.0)
        right_list = _sine(445.0, 2.0)
        left_arr = np.asarray(left_list, dtype=np.float64)
        right_arr = np.asarray(right_list, dtype=np.float64)

        from_list = stereo_image_analysis(left_list, right_list, SR)
        from_array = stereo_image_analysis(left_arr, right_arr, SR)

        assert from_list.keys() == from_array.keys()
        for key in from_list:
            assert from_list[key] == from_array[key], f"mismatch on {key!r}"

    def test_empty_ndarray_returns_neutral_default(self):
        result = stereo_image_analysis(np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64), SR)
        assert result["overall_correlation"] == 1.0
        assert result["overall_width"] == 0.0
        assert result["mono_safe"] is True

    def test_none_channels_return_neutral_default(self):
        result = stereo_image_analysis(None, None, SR)
        assert result["mono_safe"] is True

    def test_mismatched_lengths_ndarray_still_truncates_correctly(self):
        # min_len logic must still work once left/right are ndarrays.
        left = np.asarray(_sine(440.0, 2.0), dtype=np.float64)
        right = np.asarray(_sine(445.0, 1.5), dtype=np.float64)  # shorter
        result = stereo_image_analysis(left, right, SR)
        assert "overall_correlation" in result
