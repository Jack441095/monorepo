"""Numba-fallback verification for the DSP hot loops added in the 2026-07-16
perf pass (docs/audits/2026-07-16-detect-correct-and-perf.md), flagged as an
open gap in docs/PROJECT_ACTION_PLAN_2026-07-18.md §9.1 ("verify Numba
fallback paths ... falls back gracefully to pure-Python implementations on
machines without Numba compiler support").

Two things this file checks that no existing test did:

1. `dynamic_eq.py` and `dither.py` had zero numba/pure-Python parity coverage
   at all (only `dynamics.py`'s compressor/gate loops were covered, by
   test_dynamics_envelope_vectorization.py).
2. Every existing parity test calls the `_py` and `_nb` functions directly on
   a machine where numba IS installed -- none of them prove the *dispatcher*
   (the public `_smooth_attack_release`/`_envelope_follow`/
   `_noise_shape_quantise` functions actual render code calls) really falls
   back when numba is unavailable, only that the two implementations happen
   to agree. This file monkeypatches each module's `_nb` sentinel to None
   (the exact state after `except Exception: _nb = None` on an import
   failure) and drives the real dispatcher, so a regression that silently
   stops calling the pure-Python path on fallback would be caught.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.dsp_engine import dynamics as dyn  # noqa: E402
from audio_analysis.dsp_engine import dynamic_eq  # noqa: E402
from audio_analysis.dsp_engine import dither  # noqa: E402

pytestmark = pytest.mark.skipif(dyn._nb is None, reason="numba not installed on this machine")


# --- 1. Parity coverage for the two modules that had none ------------------


def test_envelope_follow_numba_matches_pure_python():
    rng = np.random.default_rng(11)
    level = rng.uniform(0.0, 1.0, 4000)
    nb = dynamic_eq._envelope_follow_nb(level, 0.85, 0.995)
    py = dynamic_eq._envelope_follow_py(level, 0.85, 0.995)
    assert np.array_equal(nb, py)


def test_envelope_follow_dispatcher_matches_direct_call():
    rng = np.random.default_rng(12)
    level = rng.uniform(0.0, 1.0, 4000)
    dispatched = dynamic_eq._envelope_follow(level, 44100.0, attack_ms=5.0, release_ms=80.0)
    direct = dynamic_eq._envelope_follow_nb(
        np.ascontiguousarray(level, dtype=np.float64),
        *_alpha_pair(44100.0, 5.0, 80.0),
    )
    assert np.array_equal(dispatched, direct)


def _alpha_pair(sample_rate: float, attack_ms: float, release_ms: float) -> tuple[float, float]:
    import math

    return (
        math.exp(-1.0 / (sample_rate * (attack_ms / 1000.0))),
        math.exp(-1.0 / (sample_rate * (release_ms / 1000.0))),
    )


def test_noise_shape_quantise_numba_matches_pure_python():
    rng = np.random.default_rng(13)
    n = 4000
    x64 = rng.uniform(-1.0, 1.0, n).astype(np.float64)
    tpdf = rng.uniform(-1e-4, 1e-4, n).astype(np.float64)
    lsb = 2.0 / (2 ** 16)
    nb = dither._noise_shape_quantise_nb(x64.copy(), tpdf.copy(), lsb, 0.5)
    py = dither._noise_shape_quantise_py(x64.copy(), tpdf.copy(), lsb, 0.5)
    assert np.array_equal(nb, py)


def test_sosfilt_numba_matches_scipy():
    from audio_analysis.dsp_engine import eq
    if eq._nb is None:
        pytest.skip("numba not available")
    rng = np.random.default_rng(15)
    samples = rng.uniform(-1.0, 1.0, 4000).astype(np.float64)
    peq = eq.ParametricEQ(sample_rate=44100)
    peq.add_band("peaking", 1000.0, gain_db=-3.0, q=1.5)
    peq.add_band("highpass", 80.0, q=0.707)
    sos = peq.get_sos(linear_phase=False)
    nb_res = eq._sosfilt_nb(sos, samples.copy())
    import scipy.signal as sig
    scipy_res = sig.sosfilt(sos, samples.copy())
    np.testing.assert_allclose(nb_res, scipy_res, rtol=1e-12, atol=1e-12)


def test_native_biquad_kernel_matches_scipy():
    from audio_analysis.dsp_engine.native import biquad_sos_filter, is_eq_available
    from audio_analysis.dsp_engine import eq
    if not is_eq_available():
        pytest.skip("native eq kernel unavailable")
    rng = np.random.default_rng(16)
    samples = rng.uniform(-1.0, 1.0, 8000).astype(np.float64)
    peq = eq.ParametricEQ(sample_rate=44100)
    peq.add_band("peaking", 2500.0, gain_db=4.5, q=1.2)
    peq.add_band("lowshelf", 120.0, gain_db=-2.0, q=0.707)
    sos = peq.get_sos(linear_phase=False)
    native_res = biquad_sos_filter(sos, samples.copy())
    import scipy.signal as sig
    scipy_res = sig.sosfilt(sos, samples.copy())
    np.testing.assert_allclose(native_res, scipy_res, rtol=1e-12, atol=1e-12)


def test_native_reverb_kernel_matches_python():
    from audio_analysis.dsp_engine.native import native_lbcf_comb_filter, native_allpass_filter, is_reverb_available
    from audio_analysis.dsp_engine import spatial
    if not is_reverb_available():
        pytest.skip("native reverb kernel unavailable")
    rng = np.random.default_rng(17)
    samples = rng.uniform(-1.0, 1.0, 4000).astype(np.float64)
    c_native = native_lbcf_comb_filter(samples, 120, 0.7, 0.2)
    c_py = spatial._lbcf_comb_py(samples, 120, 0.7, 0.2)
    np.testing.assert_allclose(c_native, c_py, rtol=1e-12, atol=1e-12)

    a_native = native_allpass_filter(samples, 85, 0.5)
    a_py = spatial._allpass_py(samples, 85, 0.5)
    np.testing.assert_allclose(a_native, a_py, rtol=1e-12, atol=1e-12)


def test_native_smooth_envelope_matches_python():
    from audio_analysis.dsp_engine.native import (
        native_smooth_attack_release, native_gate_envelope, is_smooth_envelope_available
    )
    from audio_analysis.dsp_engine import dynamics
    if not is_smooth_envelope_available():
        pytest.skip("native smooth envelope kernel unavailable")
    rng = np.random.default_rng(18)
    vals = rng.uniform(-40.0, 0.0, 5000).astype(np.float64)
    s_native = native_smooth_attack_release(vals, 0.9, 0.99, -20.0, True)
    s_py = dynamics._smooth_attack_release_py(vals, 0.9, 0.99, -20.0, True)
    np.testing.assert_allclose(s_native, s_py, rtol=1e-12, atol=1e-12)

    g_native = native_gate_envelope(vals, -24.0, 0.8, 0.95, 200, 1.0, 0.01)
    g_py = dynamics._gate_envelope_py(vals, -24.0, 0.8, 0.95, 200, 1.0, 0.01)
    np.testing.assert_allclose(g_native, g_py, rtol=1e-12, atol=1e-12)


def test_native_full_schroeder_reverb_matches_python(monkeypatch):
    from audio_analysis.dsp_engine.native import native_schroeder_reverb, is_reverb_full_available
    from audio_analysis.dsp_engine import spatial
    if not is_reverb_full_available():
        pytest.skip("native full reverb kernel unavailable")
    rng = np.random.default_rng(19)
    left = rng.uniform(-1.0, 1.0, 6000).astype(np.float64)
    right = rng.uniform(-1.0, 1.0, 6000).astype(np.float64)
    rev = spatial.Reverb(sample_rate=44100, pre_delay_ms=15.0, room_size=0.6, decay_time=1.2, damping=0.25, wet_dry=0.3)
    out_l_native, out_r_native = rev.apply(left, right)

    monkeypatch.setattr(spatial._native, "is_reverb_full_available", lambda: False)
    out_l_py, out_r_py = rev.apply(left, right)

    np.testing.assert_allclose(out_l_native, out_l_py, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(out_r_native, out_r_py, rtol=1e-12, atol=1e-12)


def test_native_saturator_matches_python(monkeypatch):
    from audio_analysis.dsp_engine.native import native_saturator_waveshape, is_saturator_available
    from audio_analysis.dsp_engine import saturation
    if not is_saturator_available():
        pytest.skip("native saturator kernel unavailable")
    rng = np.random.default_rng(20)
    samples = rng.uniform(-1.0, 1.0, 5000).astype(np.float64)
    sat_native = saturation.apply_saturation(samples, drive_db=4.0, even_harmonics=0.3, mix=0.8, oversample=False)

    monkeypatch.setattr(saturation._native, "is_saturator_available", lambda: False)
    sat_py = saturation.apply_saturation(samples, drive_db=4.0, even_harmonics=0.3, mix=0.8, oversample=False)

    np.testing.assert_allclose(sat_native, sat_py, rtol=1e-12, atol=1e-12)


def test_apply_noise_shaped_dither_still_bounded_near_original():
    rng = np.random.default_rng(14)
    samples = rng.uniform(-1.0, 1.0, 8000).astype(np.float64)
    out = dither.apply_noise_shaped_dither(samples, bit_depth=16, rng=np.random.default_rng(15))
    assert out.shape == samples.shape
    assert np.all(np.isfinite(out))
    # Noise-shaped quantisation must stay within a few LSB of the source.
    lsb = 2.0 / (2 ** 16)
    assert np.max(np.abs(out - samples)) < 8 * lsb


# --- 2. Genuine "numba unavailable" fallback activation ---------------------
# Simulates the exact state after `except Exception: _nb = None` and drives
# the real public dispatcher, not the private _py function directly.


def test_dynamics_smooth_attack_release_falls_back_when_numba_unavailable(monkeypatch):
    monkeypatch.setattr(dyn, "_nb", None)
    monkeypatch.setattr(dyn, "_native", None)
    rng = np.random.default_rng(21)
    gr_db = rng.uniform(-25, 5, 4000)
    out = dyn._smooth_attack_release(gr_db, 0.85, 0.995, 0.0, attack_when_less=True)
    expected = dyn._smooth_attack_release_py(gr_db, 0.85, 0.995, 0.0, attack_when_less=True)
    assert np.array_equal(out, expected)
    assert np.all(np.isfinite(out))


def test_dynamics_gate_envelope_falls_back_when_numba_unavailable(monkeypatch):
    monkeypatch.setattr(dyn, "_nb", None)
    monkeypatch.setattr(dyn, "_native", None)
    rng = np.random.default_rng(22)
    level_db = rng.uniform(-70, 5, 4000)
    out = dyn._gate_envelope(level_db, -40.0, 0.8, 0.97, 200, 1.0, 10 ** (-60.0 / 20.0))
    expected = dyn._gate_envelope_py(level_db, -40.0, 0.8, 0.97, 200, 1.0, 10 ** (-60.0 / 20.0))
    assert np.array_equal(out, expected)


def test_dynamics_compressor_still_works_end_to_end_when_numba_unavailable(monkeypatch):
    monkeypatch.setattr(dyn, "_nb", None)
    rng = np.random.default_rng(23)
    samples = rng.uniform(-1.0, 1.0, 4410)
    comp = dyn.Compressor(sample_rate=44100, threshold_db=-20.0, ratio=4.0)
    out = comp.apply(samples)
    assert out.shape == samples.shape
    assert np.all(np.isfinite(out))


def test_dynamic_eq_envelope_follow_falls_back_when_numba_unavailable(monkeypatch):
    monkeypatch.setattr(dynamic_eq, "_nb", None)
    rng = np.random.default_rng(24)
    level = rng.uniform(0.0, 1.0, 4000)
    out = dynamic_eq._envelope_follow(level, 44100.0, attack_ms=5.0, release_ms=80.0)
    expected = dynamic_eq._envelope_follow_py(
        np.ascontiguousarray(level, dtype=np.float64), *_alpha_pair(44100.0, 5.0, 80.0)
    )
    assert np.array_equal(out, expected)
    assert np.all(np.isfinite(out))


def test_dynamic_eq_band_still_works_end_to_end_when_numba_unavailable(monkeypatch):
    monkeypatch.setattr(dynamic_eq, "_nb", None)
    rng = np.random.default_rng(25)
    sr = 44100
    left = rng.uniform(-0.5, 0.5, sr).astype(np.float64)
    right = rng.uniform(-0.5, 0.5, sr).astype(np.float64)
    out_l, out_r = dynamic_eq.apply_dynamic_eq_band(
        left, right, frequency_hz=2500.0, sample_rate=sr, q=6.0, threshold_db=-24.0, ratio=3.0
    )
    assert out_l.shape == left.shape
    assert out_r.shape == right.shape
    assert np.all(np.isfinite(out_l))
    assert np.all(np.isfinite(out_r))


def test_dither_noise_shape_quantise_falls_back_when_numba_unavailable(monkeypatch):
    monkeypatch.setattr(dither, "_nb", None)
    rng = np.random.default_rng(26)
    n = 4000
    x64 = rng.uniform(-1.0, 1.0, n).astype(np.float64)
    tpdf = rng.uniform(-1e-4, 1e-4, n).astype(np.float64)
    lsb = 2.0 / (2 ** 16)
    out = dither._noise_shape_quantise(x64.copy(), tpdf.copy(), lsb, 0.5)
    expected = dither._noise_shape_quantise_py(x64.copy(), tpdf.copy(), lsb, 0.5)
    assert np.array_equal(out, expected)


def test_dither_apply_noise_shaped_still_works_end_to_end_when_numba_unavailable(monkeypatch):
    monkeypatch.setattr(dither, "_nb", None)
    rng = np.random.default_rng(27)
    samples = rng.uniform(-1.0, 1.0, 8000).astype(np.float64)
    out = dither.apply_noise_shaped_dither(samples, bit_depth=16, rng=np.random.default_rng(28))
    assert out.shape == samples.shape
    assert np.all(np.isfinite(out))


# --- 3. mix_renderer.py's compressor path (imports dynamics._smooth_attack_release
#        directly, no separate numba pair of its own -- confirms it also degrades
#        gracefully through the shared dispatcher rather than assuming numba). ---


def test_mix_renderer_stereo_compressor_still_works_when_numba_unavailable(monkeypatch):
    monkeypatch.setattr(dyn, "_nb", None)
    from audio_analysis.mixdown import mix_renderer

    rng = np.random.default_rng(29)
    sr = 44100
    left = rng.uniform(-0.5, 0.5, sr).astype(np.float64)
    right = rng.uniform(-0.5, 0.5, sr).astype(np.float64)
    comp_config = {"threshold_db": -18.0, "ratio": 3.0, "attack_ms": 5.0, "release_ms": 100.0}
    out_l, out_r = mix_renderer._apply_stereo_compressor(left, right, comp_config, sr)
    assert out_l.shape == left.shape
    assert out_r.shape == right.shape
    assert np.all(np.isfinite(out_l))
    assert np.all(np.isfinite(out_r))
