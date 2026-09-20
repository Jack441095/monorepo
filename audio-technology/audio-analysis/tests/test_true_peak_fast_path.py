"""calculate_true_peak(left, right, fs) with no raw_bytes takes an array-native
fast path (calculate_true_peak_numpy) instead of encoding to WAV bytes and
re-parsing them (calculate_true_peak_numpy_efficient) -- used in
mix_renderer.py's gain-solve loop to skip write_wav on every candidate.

The two paths measure a genuinely different signal in principle (pre- vs
post-24-bit-quantization/dither), so this must be verified empirically, not
assumed: on real, band-limited music audio the two must stay within a tiny
fraction of the 0.15 dB true-peak safety margin used to accept/reject a gain
candidate, since a real divergence there would mean the gain-solve loop's
inner safety check no longer agrees with the shipped output. (A synthetic
full-bandwidth white-noise test signal is NOT representative here -- it makes
resample_poly's reconstruction filter ring by several dB, since real music
isn't full-energy up to Nyquist the way white noise is.)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from audio_analysis.analysis_core.loudness import (
    calculate_true_peak,
    calculate_true_peak_numpy,
    calculate_true_peak_numpy_efficient,
)
from audio_analysis.dsp_engine.dynamics import Limiter
from audio_analysis.mixdown.stem_prep import write_wav
from audio_analysis.utils.audio_io import read_wav_mono

ROOT = Path(__file__).resolve().parents[2]
STEMS_DIR = ROOT / "testing_track_stems" / "dream_of_you" / "WAVs"

pytestmark = pytest.mark.skipif(
    not STEMS_DIR.exists(), reason="real test-track stems not available in this checkout"
)


def _real_stem_arrays():
    paths = sorted(p for p in STEMS_DIR.glob("*.wav") if not p.name.startswith("."))
    for p in paths[:6]:
        wav_data = read_wav_mono(p.read_bytes(), max_samples=0, as_arrays=True)
        yield p.name, np.asarray(wav_data["samples"], dtype=np.float64), wav_data["sample_rate"]


def test_direct_and_byte_paths_agree_on_real_stems():
    for name, samples, sr in _real_stem_arrays():
        l = samples * 0.9
        r = l.copy()
        direct_db = calculate_true_peak_numpy(l, r)
        accurate_db = calculate_true_peak_numpy_efficient(write_wav(l, r, sr, bit_depth=24))
        assert abs(direct_db - accurate_db) < 0.01, (
            f"[{name}] fast path diverged from the byte-based path by "
            f"{abs(direct_db - accurate_db):.4f} dB (safety margin is 0.15 dB)"
        )


def test_direct_and_byte_paths_agree_on_near_ceiling_limited_candidate():
    """The regime that actually matters: a limited master-bus candidate near
    the true-peak ceiling, exactly what the gain-solve loop measures."""
    sr = None
    mix = None
    for _, samples, stem_sr in _real_stem_arrays():
        if sr is None:
            sr = stem_sr
        elif stem_sr != sr:
            continue  # real stems can be natively mixed-rate; keep this mock bus single-rate
        if mix is None:
            mix = np.zeros_like(samples)
        n = min(len(mix), len(samples))
        mix = mix[:n] + samples[:n]

    lim = Limiter(sample_rate=sr, ceiling_db=-1.0, threshold_db=6.0, release_ms=50.0, lookahead_ms=5.0, true_peak=True)
    candidate = lim.apply(mix)
    l, r = candidate, candidate * 0.98

    direct_db = calculate_true_peak_numpy(l, r)
    accurate_db = calculate_true_peak_numpy_efficient(write_wav(l, r, sr, bit_depth=24))
    assert abs(direct_db - accurate_db) < 0.01

    # calculate_true_peak(..., raw_bytes=None) must dispatch to the fast path
    # and produce the same number as calling calculate_true_peak_numpy directly.
    dispatched_db = calculate_true_peak(l, r, sr)
    assert dispatched_db == pytest.approx(direct_db, abs=1e-9)
