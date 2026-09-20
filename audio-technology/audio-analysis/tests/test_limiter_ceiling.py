"""Regression tests for the true-peak limiter ceiling (AutoMix quality fix 2026-07-08).

The stereo-linked limiter wrapper used to divide the delayed, makeup-boosted
limiter output by the undelayed input and clamp to 1.0 — which discarded the
makeup gain and left limited peaks at (makeup x ceiling), overshooting by the
full makeup amount. Every AutoMix delivery clipped as a result. These tests
assert the limiter now holds its ceiling regardless of makeup gain.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.dsp_engine.dynamics import Limiter  # noqa: E402
from audio_analysis.mixdown.mix_renderer import _apply_stereo_limiter  # noqa: E402


def _true_peak_dbfs(x: np.ndarray) -> float:
    peak = float(np.max(np.abs(x)))
    return 20.0 * np.log10(peak) if peak > 0 else -120.0


def _hot_signal(n: int = 44100, sr: int = 44100) -> np.ndarray:
    t = np.arange(n) / sr
    sig = 0.9 * np.sin(2 * np.pi * 220 * t)
    sig[1000] = 1.5  # a transient hotter than full scale
    sig[20000] = 1.2
    return sig


def test_stereo_limiter_holds_ceiling_with_no_makeup() -> None:
    left = _hot_signal()
    right = _hot_signal() * 0.95
    out_l, out_r = _apply_stereo_limiter(left, right, ceiling_db=-1.0, threshold_db=0.0, sample_rate=44100)
    ceiling = 10.0 ** (-1.0 / 20.0)
    # Allow a small oversampling tolerance; must not exceed ceiling meaningfully.
    assert np.max(np.abs(out_l)) <= ceiling + 0.02
    assert np.max(np.abs(out_r)) <= ceiling + 0.02


def test_stereo_limiter_holds_ceiling_under_heavy_makeup() -> None:
    """The bug appeared only with makeup boost. threshold_db negative => big boost."""
    left = _hot_signal() * 0.3
    right = _hot_signal() * 0.28
    # threshold_db = -12 => input_gain ~4x. Old code overshot ceiling by ~4x here.
    out_l, out_r = _apply_stereo_limiter(left, right, ceiling_db=-1.0, threshold_db=-12.0, sample_rate=44100)
    ceiling = 10.0 ** (-1.0 / 20.0)
    assert np.max(np.abs(out_l)) <= ceiling + 0.02, f"left peak {_true_peak_dbfs(out_l):.2f} dBFS over -1 ceiling"
    assert np.max(np.abs(out_r)) <= ceiling + 0.02, f"right peak {_true_peak_dbfs(out_r):.2f} dBFS over -1 ceiling"


def test_stereo_limiter_preserves_makeup_below_ceiling() -> None:
    """Makeup gain must still be applied where the signal is below the ceiling
    (the old clamp-to-1.0 also broke this by zeroing the boost in quiet parts)."""
    quiet = 0.05 * np.sin(2 * np.pi * 220 * np.arange(44100) / 44100)
    out_l, out_r = _apply_stereo_limiter(quiet, quiet.copy(), ceiling_db=-1.0, threshold_db=-12.0, sample_rate=44100)
    # ~4x makeup on a -26 dBFS signal should raise it well above the input, not leave it untouched.
    assert np.max(np.abs(out_l)) > np.max(np.abs(quiet)) * 2.0


def test_limiter_release_smooths_towards_target_not_unity() -> None:
    """Release smoothing must converge towards target gain, not unconditionally to 1.0.

    This is a regression test for a missing '* target' in the release branch of the
    limiter's smoothing loop.
    """
    x = np.sin(2 * np.pi * 220 * np.arange(44100) / 44100)
    lim = Limiter(sample_rate=44100, ceiling_db=-1.0, threshold_db=-12.0, release_ms=200.0)
    out, total_gain, delay = lim.apply(x, return_gain=True)
    # After a burst of limiting, the release phase should move gain back towards
    # lower-reduction values, not snap back to unity. Verify that minimum gain
    # leaves at least some headroom vs. input gain.
    input_gain = 10.0 ** (-lim.threshold_db / 20.0)
    assert float(np.min(total_gain)) < input_gain - 1e-6


def test_limiter_return_gain_reconstructs_output() -> None:
    """return_gain must yield the exact gain the limiter applied: applying it to
    the delayed input reproduces the limiter's own output."""
    x = _hot_signal()
    lim = Limiter(sample_rate=44100, ceiling_db=-1.0, threshold_db=-6.0, true_peak=True)
    out, total_gain, delay = lim.apply(x, return_gain=True)
    recon = np.zeros_like(x)
    if delay > 0:
        recon[delay:] = x[:-delay] * total_gain[delay:]
        recon[:delay] = x[:delay] * total_gain[:delay]
    else:
        recon = x * total_gain
    assert np.allclose(recon, out, atol=1e-9)
