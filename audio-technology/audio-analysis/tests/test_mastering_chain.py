"""Unit tests for the master bus processors and reference analyzer."""

from __future__ import annotations

import numpy as np

from audio_analysis.mixdown.mix_renderer import _apply_multiband_compressor, _apply_ms_stereo_enhancer
from audio_analysis.mixdown.mix_decision_engine import analyze_reference_track
from audio_analysis.mixdown.stem_prep import write_wav


def test_ms_stereo_enhancer():
    sample_rate = 44100
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    
    # Generate simple stereo signal (L and R have different phases)
    left = np.sin(2 * np.pi * 440.0 * t)
    right = np.cos(2 * np.pi * 440.0 * t)

    # 1. Collapsed mono (width = 0)
    mono_l, mono_r = _apply_ms_stereo_enhancer(left, right, 0.0)
    # L and R must be identical in mono collapse
    assert np.allclose(mono_l, mono_r)

    # 2. Enhanced wide (width = 1.5)
    wide_l, wide_r = _apply_ms_stereo_enhancer(left, right, 1.5)
    # Check that difference (side channel) has been scaled
    orig_side = left - right
    new_side = wide_l - wide_r
    assert np.allclose(new_side, orig_side * 1.5)


def test_multiband_compressor():
    sample_rate = 44100
    duration = 0.5
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    
    # Mix containing Low (50 Hz), Mid (1000 Hz), and High (8000 Hz) tones
    sig_low = np.sin(2 * np.pi * 50.0 * t)
    sig_mid = np.sin(2 * np.pi * 1000.0 * t)
    sig_high = np.sin(2 * np.pi * 8000.0 * t)
    
    # Make it loud to trigger compression threshold
    test_sig = (sig_low + sig_mid + sig_high) * 0.8
    
    comp_l, comp_r = _apply_multiband_compressor(test_sig, test_sig, sample_rate)
    
    assert comp_l.shape == test_sig.shape
    assert comp_r.shape == test_sig.shape
    # Compression should reduce overall gain/amplitude
    assert np.max(np.abs(comp_l)) < np.max(np.abs(test_sig))


def test_reference_analyzer():
    sample_rate = 44100
    duration = 0.5
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    
    # Generate dummy stereo WAV bytes
    left = np.sin(2 * np.pi * 1000.0 * t) * 0.5
    right = np.sin(2 * np.pi * 1000.0 * t) * 0.5
    wav_bytes = write_wav(left.tolist(), right.tolist(), sample_rate, bit_depth=16)
    
    ref_profile = analyze_reference_track(wav_bytes)
    
    assert "bands" in ref_profile
    assert "loudness" in ref_profile
    assert isinstance(ref_profile["loudness"], float)
    assert "mids" in ref_profile["bands"]
    # mids should be dominant since we generated a 1000 Hz tone
    assert ref_profile["bands"]["mids"] > 0.1
