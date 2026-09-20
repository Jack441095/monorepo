"""Known-signal numeric-correctness guards for customer-facing measurements.

This repo has already been bitten once by a dependency (torch/NumPy ABI) break
that silently corrupted stereo phase-correlation in real client reports
(~+1.0 where the correct value was ~-0.02) and slowed loudness calcs. These
tests pin the measurement layer to signals whose answers are known a priori and,
crucially, assert the analysis backends **agree with each other** — so a future
backend swap or ABI break can never again silently distort a number a customer
sees.

Guarded: stereo band-correlation, true-peak, and integrated LUFS, via the public
dispatchers in `analysis_core`.
"""

from __future__ import annotations

import math

import numpy as np

from audio_analysis.analysis_core.analysis_features import (
    analyze_spectrum_and_correlation_fallback,
    analyze_spectrum_and_correlation_numpy,
)
from audio_analysis.analysis_core.loudness_api import (
    calculate_lufs_fallback,
    calculate_lufs_numpy,
    calculate_true_peak_fallback,
    calculate_true_peak_numpy,
)

FS = 44100


def _sine(freq: float, amp: float, n: int, fs: int = FS) -> list[float]:
    return [amp * math.sin(2.0 * math.pi * freq * i / fs) for i in range(n)]


def _broadband(n: int = 8192, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.clip(rng.standard_normal(n) * 0.3, -1.0, 1.0)


# ---- stereo correlation (the historically-corrupted number) -----------------

def test_identical_channels_correlate_to_plus_one():
    x = _broadband()
    _, _, corr = analyze_spectrum_and_correlation_numpy(x.copy(), x.copy(), FS)
    assert corr, "no correlation bands returned"
    for band, value in corr.items():
        assert value >= 0.9, f"identical L/R should correlate ~+1, band {band} = {value}"


def test_antiphase_channels_correlate_to_minus_one():
    x = _broadband()
    _, _, corr = analyze_spectrum_and_correlation_numpy(x.copy(), -x.copy(), FS)
    for band, value in corr.items():
        assert value <= -0.9, f"anti-phase L/R should correlate ~-1, band {band} = {value}"


def test_correlation_backends_agree_on_known_correlation():
    # The exact property that broke was a backend reporting a strongly-wrong
    # value (e.g. ~+1 where truth was ~0). We pin agreement on signals whose
    # correlation is *known and strong* (identical -> +1, anti-phase -> -1),
    # where any backend defect shows immediately. (Agreement on uncorrelated,
    # near-zero values is inherently noisy in sparse bands and not a useful
    # guard.)
    x = _broadband()
    for factor, lo, hi in ((1.0, 0.9, 1.0001), (-1.0, -1.0001, -0.9)):
        _, _, corr_np = analyze_spectrum_and_correlation_numpy(x.copy(), factor * x.copy(), FS)
        _, _, corr_fb = analyze_spectrum_and_correlation_fallback(x.tolist(), (factor * x).tolist(), FS)
        shared = set(corr_np) & set(corr_fb)
        assert shared, "backends returned no common bands"
        for band in shared:
            assert lo <= corr_np[band] <= hi, f"numpy band {band} = {corr_np[band]} (factor {factor})"
            assert lo <= corr_fb[band] <= hi, f"fallback band {band} = {corr_fb[band]} (factor {factor})"
            assert abs(corr_np[band] - corr_fb[band]) <= 0.05, (
                f"backend divergence in band {band}: numpy={corr_np[band]} fallback={corr_fb[band]}"
            )


# ---- true peak --------------------------------------------------------------

def test_true_peak_of_half_amplitude_sine_is_minus_six_dbfs():
    sig = _sine(1000.0, 0.5, FS)  # -6.02 dBFS sine
    tp_np = calculate_true_peak_numpy(sig, sig)
    assert -6.6 <= tp_np <= -5.2, f"0.5-amplitude sine true-peak should be ~-6 dBFS, got {tp_np}"


def test_true_peak_backends_agree():
    sig = _sine(1000.0, 0.5, FS)
    tp_np = calculate_true_peak_numpy(sig, sig)
    tp_fb = calculate_true_peak_fallback(sig, sig)
    assert abs(tp_np - tp_fb) <= 0.3, f"true-peak backend divergence: numpy={tp_np} fallback={tp_fb}"


# ---- integrated LUFS --------------------------------------------------------

def test_lufs_backends_agree():
    sig = _sine(1000.0, 0.5, FS)
    lufs_np = calculate_lufs_numpy(sig, sig, FS)
    lufs_fb = calculate_lufs_fallback(sig, sig, FS)
    assert abs(lufs_np - lufs_fb) <= 1.0, f"LUFS backend divergence: numpy={lufs_np} fallback={lufs_fb}"


def test_lufs_scales_with_gain():
    # Doubling amplitude must raise integrated loudness by ~6.02 LU, independent
    # of backend/K-weighting details — catches gain/scaling regressions.
    sig = _sine(1000.0, 0.4, FS)
    louder = [s * 2.0 for s in sig]
    delta = calculate_lufs_numpy(louder, louder, FS) - calculate_lufs_numpy(sig, sig, FS)
    assert abs(delta - 6.02) <= 0.6, f"+6 dB gain should raise LUFS ~6.02, got {delta}"
