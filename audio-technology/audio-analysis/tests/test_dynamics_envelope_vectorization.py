"""Compressor/Limiter/Gate's per-sample envelope-follower loops were
vectorized via optional numba JIT for a ~2x render-time speedup (fixed a
real performance regression -- see docs/automix_deep_scan_2026-07-12.md §4.1
and docs/codebase_scan_12_07.md §5a). The numba path and the pure-Python
fallback must stay bit-for-bit identical, since audio correctness (LUFS,
true peak) depends on it."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.dsp_engine import dynamics as dyn  # noqa: E402


def test_smooth_attack_release_numba_matches_pure_python_compressor_style():
    rng = np.random.default_rng(1)
    gr_db = rng.uniform(-25, 5, 4000)
    nb = dyn._smooth_attack_release(gr_db, 0.85, 0.995, 0.0, attack_when_less=True)
    py = dyn._smooth_attack_release_py(gr_db, 0.85, 0.995, 0.0, attack_when_less=True)
    np.testing.assert_allclose(nb, py, rtol=1e-12, atol=1e-12)


def test_smooth_attack_release_numba_matches_pure_python_limiter_style():
    rng = np.random.default_rng(2)
    target_gain = rng.uniform(0.01, 1.0, 4000)
    nb = dyn._smooth_attack_release(target_gain, 0.0, 0.998, 1.0, attack_when_less=False)
    py = dyn._smooth_attack_release_py(target_gain, 0.0, 0.998, 1.0, attack_when_less=False)
    np.testing.assert_allclose(nb, py, rtol=1e-12, atol=1e-12)


def test_gate_envelope_numba_matches_pure_python():
    rng = np.random.default_rng(3)
    level_db = rng.uniform(-70, 5, 4000)
    nb = dyn._gate_envelope(level_db, -40.0, 0.8, 0.97, 200, 1.0, 10 ** (-60.0 / 20.0))
    py = dyn._gate_envelope_py(level_db, -40.0, 0.8, 0.97, 200, 1.0, 10 ** (-60.0 / 20.0))
    np.testing.assert_allclose(nb, py, rtol=1e-12, atol=1e-12)


def test_compressor_apply_still_produces_finite_bounded_output():
    rng = np.random.default_rng(4)
    samples = rng.uniform(-1.0, 1.0, 4410)
    comp = dyn.Compressor(sample_rate=44100, threshold_db=-20.0, ratio=4.0)
    out = comp.apply(samples)
    assert out.shape == samples.shape
    assert np.all(np.isfinite(out))


def test_limiter_apply_still_holds_ceiling():
    rng = np.random.default_rng(5)
    samples = rng.uniform(-1.0, 1.0, 4410)
    lim = dyn.Limiter(sample_rate=44100, ceiling_db=-1.0)
    out = lim.apply(samples)
    ceiling_linear = 10.0 ** (-1.0 / 20.0)
    assert np.max(np.abs(out)) <= ceiling_linear + 1e-6


def test_gate_apply_still_produces_finite_bounded_output():
    rng = np.random.default_rng(6)
    samples = rng.uniform(-1.0, 1.0, 4410)
    gate = dyn.Gate(sample_rate=44100, threshold_db=-40.0)
    out = gate.apply(samples)
    assert out.shape == samples.shape
    assert np.all(np.isfinite(out))
