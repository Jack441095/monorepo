"""reference_matching.py's rolling-window dynamics-comparison helpers
(``_rolling_rms``, ``_rolling_peak``, ``_envelope_attack_slope``) were
rewritten from pure-Python loops to vectorized numpy (``sliding_window_view``
+ reduction; a two-piece cumsum-ramp/sliding-window-mean form for the
envelope, whose original window grows from 1 sample up to a fixed width).
Motivation: these ran over a full rendered mixdown on every reference-based
AutoMix job (``compute_reference_dynamics_comp``), and the old
``_envelope_attack_slope`` in particular was O(n * window) -- ~9M x ~23
scalar adds per call on a 205s track.

Bit-exactness expectations differ per function:
  * ``_rolling_peak`` -- max-of-window is exact regardless of summation
    order, so this IS bit-exact against the original loop.
  * ``_rolling_rms`` and ``_envelope_attack_slope`` -- involve summation
    (mean), and float64 summation order differs between a per-window Python
    ``sum()`` and numpy's reduction. NOT bit-exact by design. Empirically
    (see the fuzz trials below and the ~205s-scale manual timing run this
    change was verified with) the divergence is at the float64 noise floor
    (observed max relative error ~2e-16, i.e. 1 ULP) -- this repo's
    established convention for "vectorized, not bit-exact" pairs (see
    test_stem_classifier_vectorized.py, test_dynamics_envelope_vectorization.py)
    uses a tolerance well above the observed noise floor but far tighter than
    anything that could mask a real bug; 1e-9 relative / 1e-9 absolute is used
    here for the same reason.

The guard bug fixed alongside this (``if not samples`` raising "ambiguous
truth value" on ndarray input, same class as dsp_metrics.py /
stereo_analysis.py) is also covered here: both list and ndarray input are
exercised in every parametrized case.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from audio_analysis.analysis_core.reference_matching import (
    _rolling_rms,
    _rolling_peak,
    _envelope_attack_slope,
    _crest_factor_series,
    dynamics_comparison,
)

SR = 44100
RTOL = 1e-9
ATOL = 1e-9


# ---------------------------------------------------------------------------
# Preserved pre-vectorization reference implementations (verbatim copies of
# the original loops, kept ONLY for this regression test).
# ---------------------------------------------------------------------------

def _rolling_rms_original(samples, window_samples):
    if not samples or window_samples <= 0:
        return []
    hop = max(1, window_samples // 2)
    values = []
    for start in range(0, len(samples) - window_samples + 1, hop):
        chunk = samples[start:start + window_samples]
        ms = sum(s * s for s in chunk) / len(chunk)
        values.append(math.sqrt(max(ms, 0.0)))
    return values


def _rolling_peak_original(samples, window_samples):
    if not samples or window_samples <= 0:
        return []
    hop = max(1, window_samples // 2)
    values = []
    for start in range(0, len(samples) - window_samples + 1, hop):
        chunk = samples[start:start + window_samples]
        values.append(max(abs(s) for s in chunk))
    return values


def _envelope_attack_slope_original(samples, sample_rate):
    if not samples or sample_rate <= 0:
        return 0.0
    abs_s = [abs(s) for s in samples]
    smooth_len = max(1, int(sample_rate * 0.0005))
    smoothed = []
    for i in range(len(abs_s)):
        start = max(0, i - smooth_len)
        smoothed.append(sum(abs_s[start:i + 1]) / (i - start + 1))

    max_slope = 0.0
    step_samples = max(1, int(sample_rate * 0.001))
    for i in range(step_samples, len(smoothed)):
        v_now = smoothed[i]
        v_prev = smoothed[i - step_samples]
        if v_prev > 1e-9 and v_now > v_prev:
            db_rise = 20 * math.log10(v_now / v_prev)
            max_slope = max(max_slope, db_rise)
    return round(max_slope, 2)


# ---------------------------------------------------------------------------
# Synthetic signals covering the shapes that matter: silence, tone, noise,
# transient bursts, a ramp (monotonic envelope), and edge-length signals.
# ---------------------------------------------------------------------------

def _signals() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(42)
    sigs: dict[str, np.ndarray] = {}
    sigs["silence_1s"] = np.zeros(SR, dtype=np.float64)
    sigs["sine_2s"] = (0.5 * np.sin(2 * np.pi * 440 * np.arange(SR * 2) / SR)).astype(np.float64)
    sigs["noise_3s"] = (0.3 * rng.standard_normal(SR * 3)).astype(np.float64)
    t = np.arange(SR * 5)
    sigs["bursty_5s"] = np.where((t % 4410) < 441, 0.9, 0.05).astype(np.float64)
    sigs["ramp_1s"] = np.linspace(0.0, 1.0, SR).astype(np.float64)
    sigs["tiny_10"] = np.array([0.1, -0.2, 0.3, -0.4, 0.05, 0.0, 0.9, -0.9, 0.01, -0.01])
    sigs["single_sample"] = np.array([0.42])
    sigs["empty"] = np.array([], dtype=np.float64)
    return sigs


SIGNALS = _signals()


# ---------------------------------------------------------------------------
# _rolling_peak -- bit-exact
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", list(SIGNALS.keys()))
def test_rolling_peak_bit_exact_vs_original(name: str) -> None:
    sig = SIGNALS[name]
    ws = max(256, SR)  # 1-second window, matches _crest_factor_series' usage
    original = _rolling_peak_original(sig.tolist(), ws)
    vectorized_list = _rolling_peak(sig.tolist(), ws)
    vectorized_arr = _rolling_peak(sig, ws)

    assert vectorized_list == original
    assert vectorized_arr == original


# ---------------------------------------------------------------------------
# _rolling_rms -- numerically close, not bit-exact
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", list(SIGNALS.keys()))
def test_rolling_rms_matches_original_within_tolerance(name: str) -> None:
    sig = SIGNALS[name]
    ws = max(256, SR)
    original = _rolling_rms_original(sig.tolist(), ws)
    vectorized_list = _rolling_rms(sig.tolist(), ws)
    vectorized_arr = _rolling_rms(sig, ws)

    assert len(vectorized_list) == len(original)
    assert len(vectorized_arr) == len(original)
    if original:
        np.testing.assert_allclose(vectorized_list, original, rtol=RTOL, atol=ATOL)
        np.testing.assert_allclose(vectorized_arr, original, rtol=RTOL, atol=ATOL)


# ---------------------------------------------------------------------------
# _envelope_attack_slope -- numerically close, not bit-exact
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", list(SIGNALS.keys()))
def test_envelope_attack_slope_matches_original_within_tolerance(name: str) -> None:
    sig = SIGNALS[name]
    original = _envelope_attack_slope_original(sig.tolist(), SR)
    vectorized_list = _envelope_attack_slope(sig.tolist(), SR)
    vectorized_arr = _envelope_attack_slope(sig, SR)

    assert vectorized_list == pytest.approx(original, rel=RTOL, abs=ATOL)
    assert vectorized_arr == pytest.approx(original, rel=RTOL, abs=ATOL)


@pytest.mark.parametrize("seed", range(15))
def test_envelope_attack_slope_fuzz(seed: int) -> None:
    """Random bursty signals -- the shape most likely to expose a
    leading-edge-ramp/fixed-window boundary bug in the vectorized rewrite."""
    rng = np.random.default_rng(seed)
    n = int(rng.integers(50, SR * 2))
    sig = (rng.uniform(-1.0, 1.0, n) * rng.choice([0.05, 0.3, 0.9])).astype(np.float64)

    original = _envelope_attack_slope_original(sig.tolist(), SR)
    vectorized = _envelope_attack_slope(sig, SR)
    assert vectorized == pytest.approx(original, rel=RTOL, abs=ATOL)


@pytest.mark.parametrize("seed", range(15))
def test_rolling_rms_fuzz(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n = int(rng.integers(50, SR * 2))
    sig = (rng.uniform(-1.0, 1.0, n) * rng.choice([0.05, 0.3, 0.9])).astype(np.float64)
    ws = int(rng.choice([256, 1024, 4096, 44100]))

    original = _rolling_rms_original(sig.tolist(), ws)
    vectorized = _rolling_rms(sig, ws)
    assert len(vectorized) == len(original)
    if original:
        np.testing.assert_allclose(vectorized, original, rtol=RTOL, atol=ATOL)


# ---------------------------------------------------------------------------
# Guard: None / empty / non-positive-rate no longer raise "ambiguous truth
# value" on ndarray input.
# ---------------------------------------------------------------------------

class TestGuardsAcceptNdarray:

    def test_rolling_rms_empty_ndarray(self):
        assert _rolling_rms(np.asarray([], dtype=np.float64), 100) == []

    def test_rolling_rms_none(self):
        assert _rolling_rms(None, 100) == []

    def test_rolling_peak_empty_ndarray(self):
        assert _rolling_peak(np.asarray([], dtype=np.float64), 100) == []

    def test_rolling_peak_none(self):
        assert _rolling_peak(None, 100) == []

    def test_envelope_attack_slope_empty_ndarray(self):
        assert _envelope_attack_slope(np.asarray([], dtype=np.float64), SR) == 0.0

    def test_envelope_attack_slope_none(self):
        assert _envelope_attack_slope(None, SR) == 0.0

    def test_ndarray_shorter_than_window_returns_empty(self):
        short = np.asarray([0.1, 0.2, 0.3], dtype=np.float64)
        assert _rolling_rms(short, 1000) == []
        assert _rolling_peak(short, 1000) == []


# ---------------------------------------------------------------------------
# End-to-end: dynamics_comparison (the public entry point) with ndarray
# input, matching how compute_reference_dynamics_comp / spectral_match.py
# now flows data through as_arrays=True reads.
# ---------------------------------------------------------------------------

class TestDynamicsComparisonNdarrayInput:

    def test_ndarray_input_does_not_raise_and_matches_list_input(self):
        rng = np.random.default_rng(7)
        mix_list = (0.4 * np.sin(2 * np.pi * 440 * np.arange(SR * 3) / SR)).tolist()
        ref_arr = (0.3 * rng.standard_normal(SR * 3)).astype(np.float64)

        result_list = dynamics_comparison(mix_list, ref_arr.tolist(), SR)
        result_arr = dynamics_comparison(np.asarray(mix_list, dtype=np.float64), ref_arr, SR)

        assert result_list["mix_crest_avg_db"] == pytest.approx(result_arr["mix_crest_avg_db"], abs=1e-6)
        assert result_list["ref_crest_avg_db"] == pytest.approx(result_arr["ref_crest_avg_db"], abs=1e-6)
        assert result_list["crest_delta_db"] == pytest.approx(result_arr["crest_delta_db"], abs=1e-6)
        assert result_list["mix_attack_slope_db_per_ms"] == pytest.approx(
            result_arr["mix_attack_slope_db_per_ms"], abs=1e-6
        )
        assert result_list["suggested_settings"] == result_arr["suggested_settings"]

    def test_empty_ndarray_input_does_not_raise(self):
        result = dynamics_comparison(np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64), SR)
        assert result["mix_crest_avg_db"] == 0.0
        assert result["crest_delta_db"] == 0.0
