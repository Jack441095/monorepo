"""Native (C++) limiter kernel — must be bit-identical to the Python/offline
limiter, or it's worthless. Skips cleanly where no C++ compiler is available
(e.g. CI without build tools); the Python path is always the reference.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from audio_analysis.dsp_engine import dynamics, native
from audio_analysis.dsp_engine.streaming import StreamingLimiter

pytestmark = pytest.mark.skipif(
    not native.is_available(),
    reason="native C++ limiter kernel could not be built (no C++ compiler here)",
)


def _spiky(seconds: float = 2.0, sample_rate: int = 48000) -> np.ndarray:
    t = np.arange(int(sample_rate * seconds)) / sample_rate
    rng = np.random.default_rng(2)
    x = (0.7 * np.sin(2 * np.pi * 150 * t) + 0.5 * np.sin(2 * np.pi * 2000 * t)
         + 0.2 * rng.standard_normal(len(t)))
    x[5000:5010] += 3.0
    return x.astype(np.float64)


@pytest.mark.parametrize("cfg", [
    {"threshold_db": 0.0, "ceiling_db": -1.0, "release_ms": 50.0, "lookahead_ms": 5.0},
    {"threshold_db": -3.0, "ceiling_db": -0.3, "release_ms": 100.0, "lookahead_ms": 2.0},
])
def test_native_matches_python_limiter(cfg: dict) -> None:
    sr = 48000
    x = _spiky(sample_rate=sr)
    py_out, py_gain = StreamingLimiter(sr, **cfg).process_stream(x, block_size=128)

    input_gain = 10.0 ** (-cfg["threshold_db"] / 20.0)
    ceiling = 10.0 ** (cfg["ceiling_db"] / 20.0)
    alpha_rel = math.exp(-1.0 / (sr * (cfg["release_ms"] / 1000.0)))
    lookahead = max(1, int(sr * cfg["lookahead_ms"] / 1000.0))
    c_gain, c_out = native.limiter_gain_envelope(x, input_gain, ceiling, alpha_rel, lookahead)

    assert c_gain.shape == py_gain.shape
    # audio output is exact; gain differs only by the float reconstruction in the
    # Python reference (it recovers gain via output/x_g), so allow rounding there.
    assert np.max(np.abs(c_out - py_out)) < 1e-12
    assert np.max(np.abs(c_gain - py_gain)) < 1e-12
    ceiling_lin = 10.0 ** (cfg["ceiling_db"] / 20.0)
    assert np.max(np.abs(c_out)) <= ceiling_lin + 1e-12


def test_native_empty_input() -> None:
    gain, audio = native.limiter_gain_envelope(np.zeros(0), 1.0, 0.9, 0.99, 240)
    assert gain.shape == (0,)
    assert audio.shape == (0,)


@pytest.mark.parametrize("true_peak", [True, False])
@pytest.mark.parametrize("seed", range(5))
def test_native_limiter_matches_offline_dynamics_limiter(true_peak: bool, seed: int) -> None:
    """dsp_engine.dynamics.Limiter.apply() wires the native kernel into the
    offline (non-streaming) render path -- the peak-follower/target-gain/
    release-smoothing sequence is identical whether or not the signal was
    4x-oversampled for true-peak detection (same math, different L/alpha_rel),
    so the kernel that was originally proven against StreamingLimiter above
    also drop-in replaces this path. Must stay bit-identical to the
    scipy+numba fallback in both true_peak modes, or the native path must not
    be used."""
    rng = np.random.default_rng(1000 + seed)
    sr = int(rng.choice([44100, 48000]))
    n = int(rng.integers(200, 20000))
    x = (rng.standard_normal(n) * rng.uniform(0.1, 4.0)).astype(np.float64)
    if n > 20:
        idx = int(rng.integers(0, n - 10))
        x[idx:idx + 10] += rng.uniform(1.0, 6.0)

    lim = dynamics.Limiter(
        sample_rate=sr,
        ceiling_db=float(rng.uniform(-3.0, -0.1)),
        threshold_db=float(rng.uniform(-12.0, 6.0)),
        release_ms=float(rng.uniform(5.0, 300.0)),
        lookahead_ms=float(rng.uniform(1.0, 10.0)),
        true_peak=true_peak,
    )

    out_native, gain_native, delay_native = lim.apply(x, return_gain=True)

    original_is_available = dynamics._native.is_available
    dynamics._native.is_available = lambda: False
    try:
        out_py, gain_py, delay_py = lim.apply(x, return_gain=True)
    finally:
        dynamics._native.is_available = original_is_available

    assert delay_native == delay_py
    assert np.max(np.abs(out_native - out_py)) == 0.0
    assert np.max(np.abs(gain_native - gain_py)) == 0.0
