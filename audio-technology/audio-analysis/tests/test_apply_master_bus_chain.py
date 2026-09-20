"""Tests for apply_master_bus_chain() -- the master bus processing chain
(saturation -> glue compressor -> multiband compressor -> master EQ -> M/S
stereo enhancer -> dynamic EQ), extracted (2026-08-01, pure refactor) out of
what used to be inline in mix_and_render_stems' "8. Master Bus Processing"
stage. That extraction was verified bit-identical against the pre-refactor
code (same output samples for both a plain and a resonance-planted input)
via a git-worktree A/B comparison -- this file is the permanent, fast,
committed regression coverage for the extracted function on its own,
independent of the full stem-mixing pipeline mix_and_render_stems' own
tests already exercise it through.
"""

from __future__ import annotations

import math
import random

import numpy as np

from audio_analysis.analysis_core.stereo_analysis import stereo_image_analysis
from audio_analysis.mixdown.mix_decision_engine import BusMixConfig
from audio_analysis.mixdown.mix_renderer import apply_master_bus_chain

SR = 44100
DURATION_S = 3.0
N = int(SR * DURATION_S)
_T = np.arange(N) / SR


def _tone(freq: float, *, amplitude: float = 0.3, seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    harm = sum(np.sin(2 * np.pi * freq * k * _T) / k for k in (1, 2, 3))
    noise = rng.normal(0, 1, N) * 0.02
    sig = (harm * amplitude + noise).astype(np.float64)
    return sig.copy(), sig.copy()


def _white_noise(duration_s: float, *, amplitude: float = 0.15, seed: int = 42) -> list[float]:
    rng = random.Random(seed)
    n = int(duration_s * SR)
    return [amplitude * (rng.random() * 2.0 - 1.0) for _ in range(n)]


def _sine_list(freq: float, duration_s: float, *, amplitude: float = 0.35) -> list[float]:
    n = int(duration_s * SR)
    return [amplitude * math.sin(2.0 * math.pi * freq * t / SR) for t in range(n)]


def test_bus_config_none_is_a_no_op():
    left, right = _tone(220.0)
    out_l, out_r, dyn_bands = apply_master_bus_chain(left.copy(), right.copy(), SR, None, "pop")
    assert np.array_equal(out_l, left)
    assert np.array_equal(out_r, right)
    assert dyn_bands == []


def test_deterministic_same_input_same_output():
    left, right = _tone(220.0, amplitude=0.2)
    bus_config = BusMixConfig(
        bus_compressor={"threshold_db": -18.0, "ratio": 2.5, "attack_ms": 10.0, "release_ms": 100.0},
        bus_eq_bands=[{"type": "peaking", "frequency": 3000.0, "gain_db": 2.0, "q": 1.0}],
        reference_width_factor=1.05,
        saturation_drive_db=3.0,
        saturation_mix=0.4,
    )
    out_l_a, out_r_a, _ = apply_master_bus_chain(left.copy(), right.copy(), SR, bus_config, "pop")
    out_l_b, out_r_b, _ = apply_master_bus_chain(left.copy(), right.copy(), SR, bus_config, "pop")
    assert np.array_equal(out_l_a, out_l_b)
    assert np.array_equal(out_r_a, out_r_b)


def test_bus_compressor_makeup_gain_is_applied():
    """Locks in the 2026-07-17 fix: _apply_stereo_compressor only computes
    gain reduction, so makeup_gain_db must be applied separately via
    apply_gain() afterward -- a bus_compressor with makeup gain must measure
    louder than the same compressor with makeup gain zeroed out."""
    left, right = _tone(220.0, amplitude=0.3)
    base_kwargs = dict(threshold_db=-18.0, ratio=3.0, attack_ms=10.0, release_ms=100.0)

    bus_no_makeup = BusMixConfig(bus_compressor={**base_kwargs, "makeup_gain_db": 0.0})
    bus_with_makeup = BusMixConfig(bus_compressor={**base_kwargs, "makeup_gain_db": 6.0})

    out_l_no, out_r_no, _ = apply_master_bus_chain(left.copy(), right.copy(), SR, bus_no_makeup, "pop")
    out_l_yes, out_r_yes, _ = apply_master_bus_chain(left.copy(), right.copy(), SR, bus_with_makeup, "pop")

    rms_no = float(np.sqrt(np.mean(out_l_no ** 2)))
    rms_yes = float(np.sqrt(np.mean(out_l_yes ** 2)))
    assert rms_yes > rms_no


def test_reference_width_factor_widens_the_stereo_image():
    rng = np.random.default_rng(9)
    mid = 0.25 * np.sin(2 * np.pi * 300 * _T)
    side = 0.05 * rng.standard_normal(N)
    left = (mid + side).astype(np.float64)
    right = (mid - side).astype(np.float64)

    narrow = BusMixConfig(reference_width_factor=1.0)
    wide = BusMixConfig(reference_width_factor=1.15)

    out_l_narrow, out_r_narrow, _ = apply_master_bus_chain(left.copy(), right.copy(), SR, narrow, "jazz")
    out_l_wide, out_r_wide, _ = apply_master_bus_chain(left.copy(), right.copy(), SR, wide, "jazz")

    width_narrow = stereo_image_analysis(out_l_narrow.tolist(), out_r_narrow.tolist(), SR)["overall_width"]
    width_wide = stereo_image_analysis(out_l_wide.tolist(), out_r_wide.tolist(), SR)["overall_width"]
    assert width_wide > width_narrow


def test_genre_width_boost_applies_for_commercial_genres_only():
    rng = np.random.default_rng(11)
    mid = 0.25 * np.sin(2 * np.pi * 300 * _T)
    side = 0.05 * rng.standard_normal(N)
    left = (mid + side).astype(np.float64)
    right = (mid - side).astype(np.float64)
    bus_config = BusMixConfig(reference_width_factor=1.0)

    out_l_pop, out_r_pop, _ = apply_master_bus_chain(left.copy(), right.copy(), SR, bus_config, "pop")
    out_l_jazz, out_r_jazz, _ = apply_master_bus_chain(left.copy(), right.copy(), SR, bus_config, "jazz")

    width_pop = stereo_image_analysis(out_l_pop.tolist(), out_r_pop.tolist(), SR)["overall_width"]
    width_jazz = stereo_image_analysis(out_l_jazz.tolist(), out_r_jazz.tolist(), SR)["overall_width"]
    assert width_pop > width_jazz


def test_dynamic_eq_detects_and_corrects_a_planted_resonance():
    """Same planted-resonance recipe as test_resonance_detection.py's own
    acceptance test (white noise + a much-louder 2kHz tone) -- proves the
    detect_resonant_bands -> apply_dynamic_eq_bands wiring inside the
    extracted chain still engages, not just that the other stages pass
    through untouched."""
    noise_l = _white_noise(DURATION_S, seed=42)
    noise_r = _white_noise(DURATION_S, seed=43)
    resonance = _sine_list(2000.0, DURATION_S, amplitude=0.35)
    left = np.asarray([n + r for n, r in zip(noise_l, resonance)], dtype=np.float64)
    right = np.asarray([n + r for n, r in zip(noise_r, resonance)], dtype=np.float64)

    bus_config = BusMixConfig()
    out_l, out_r, dyn_bands = apply_master_bus_chain(left.copy(), right.copy(), SR, bus_config, "pop")

    assert dyn_bands, "expected at least one flagged/corrected resonant band"
    closest = min(dyn_bands, key=lambda b: abs(b["frequency_hz"] - 2000.0))
    assert abs(closest["frequency_hz"] - 2000.0) < 200.0


def test_returns_numpy_arrays_of_the_same_length_as_input():
    left, right = _tone(220.0, amplitude=0.2)
    bus_config = BusMixConfig(saturation_drive_db=2.0, saturation_mix=0.3)
    out_l, out_r, dyn_bands = apply_master_bus_chain(left.copy(), right.copy(), SR, bus_config, "pop")
    assert isinstance(out_l, np.ndarray) and isinstance(out_r, np.ndarray)
    assert len(out_l) == len(left)
    assert len(out_r) == len(right)
    assert isinstance(dyn_bands, list)
