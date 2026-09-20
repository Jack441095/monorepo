"""Unit tests for Transient Shaper DSP Primitive and AutoMix Integration."""

from __future__ import annotations

import numpy as np
import pytest
from audio_analysis.dsp_engine.transient_shaper import apply_transient_shaper


def test_transient_shaper_boosts_sharp_attacks():
    sr = 44100
    t = np.arange(sr) / sr
    
    # Signal with a sharp transient spike at t=0.1s
    sig = np.sin(2 * np.pi * 440 * t) * 0.1
    sig[4410:4450] += 0.8  # Spike

    out_l, _ = apply_transient_shaper(sig, None, attack_boost_db=4.0, sustain_trim_db=0.0, sample_rate=sr)
    
    # Peak at the transient spike should be boosted
    assert np.max(np.abs(out_l[4410:4450])) > np.max(np.abs(sig[4410:4450]))


def test_transient_shaper_zero_boost_is_passthrough():
    sig = np.random.randn(1000) * 0.1
    out_l, out_r = apply_transient_shaper(sig, sig.copy(), attack_boost_db=0.0, sustain_trim_db=0.0)
    
    np.testing.assert_allclose(out_l, sig)
    np.testing.assert_allclose(out_r, sig)
