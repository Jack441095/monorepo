"""Native (C++) rolling-median/MAD adaptive threshold kernel used by
transient_groove.py's detect_transient_onsets -- must be bit-identical to the
Python/numpy reference, or it's worthless. Skips cleanly where no C++
compiler is available; the Python path is always the reference.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_analysis.analysis_core.transient_groove import (
    _rolling_median_mad_threshold_py,
    detect_transient_onsets,
)
from audio_analysis.dsp_engine import native

pytestmark = pytest.mark.skipif(
    not native.is_transient_threshold_available(),
    reason="native transient threshold kernel could not be built (no C++ compiler here)",
)


@pytest.mark.parametrize("seed", range(20))
def test_native_matches_python_reference(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n = int(rng.integers(1, 5000))
    radius = int(rng.integers(1, 20))
    flux = rng.uniform(0.0, 1.0, n).astype(np.float64)
    min_floor = float(rng.uniform(0.001, 0.05))
    mad_mult = float(rng.uniform(1.0, 5.0))

    native_out = native.native_rolling_median_mad_threshold(flux, radius, min_floor, mad_mult)
    py_out = _rolling_median_mad_threshold_py(flux, radius, min_floor, mad_mult)

    assert native_out.shape == py_out.shape
    assert np.max(np.abs(native_out - py_out)) == 0.0 if len(py_out) else True


@pytest.mark.parametrize("flux,radius", [
    (np.zeros(0), 8),
    (np.zeros(1), 8),
    (np.zeros(5), 8),          # n < window
    (np.full(100, 0.5), 8),    # constant signal
    (np.array([0.0, 1.0]), 1), # tiny even window
])
def test_native_matches_python_edge_cases(flux: np.ndarray, radius: int) -> None:
    native_out = native.native_rolling_median_mad_threshold(flux, radius, 0.015, 3.0)
    py_out = _rolling_median_mad_threshold_py(flux, radius, 0.015, 3.0)
    assert native_out.shape == py_out.shape
    if len(py_out):
        assert np.max(np.abs(native_out - py_out)) == 0.0


def test_detect_transient_onsets_native_matches_python() -> None:
    """End-to-end: the full onset-detection function, not just the kernel in
    isolation, since that's what actually ships."""
    rng = np.random.default_rng(7)
    sr = 44100
    n = sr * 5
    t = np.arange(n) / sr
    signal = 0.3 * np.sin(2 * np.pi * 100 * t)
    for onset_t in (0.5, 1.2, 2.0, 3.1, 4.0):
        idx = int(onset_t * sr)
        signal[idx:idx + 200] += np.hanning(200) * 0.8
    signal += rng.standard_normal(n) * 0.02

    native_result = detect_transient_onsets(signal, sr)

    original = native.is_transient_threshold_available
    native.is_transient_threshold_available = lambda: False
    try:
        py_result = detect_transient_onsets(signal, sr)
    finally:
        native.is_transient_threshold_available = original

    assert native_result == py_result
    assert len(native_result) >= 1
