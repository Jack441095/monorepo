"""compute_erb_profile (erb_masking.py) was rewritten from a per-FFT-bin
Python loop (calling hz_to_erb() 3x per in-range bin, including the
loop-invariant e_min/e_max recomputed every iteration -- measured 2026-07-30
at ~5570 hz_to_erb calls per real render call of this function, and this
function dominated infer_relationships' render-time share) to a vectorized
numpy form using np.bincount to sum energy grouped by ERB band index.

Must stay bit-identical to the original loop, since this feeds real masking/
relationship decisions -- verified here against a preserved copy of the
original implementation across fuzz trials and edge cases.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_analysis.analysis_core.erb_masking import compute_erb_profile, hz_to_erb


def _compute_erb_profile_original(magnitudes, sample_rate, fft_size, num_bands=40):
    """The original per-bin Python loop, preserved here as the reference
    implementation for regression testing against the vectorized version."""
    energies = [0.0] * num_bands
    if not magnitudes or sample_rate <= 0 or fft_size <= 0:
        return energies
    bin_freq_step = sample_rate / fft_size
    for bin_idx, mag in enumerate(magnitudes):
        freq = bin_idx * bin_freq_step
        if freq < 20.0 or freq > 20000.0:
            continue
        erb_val = hz_to_erb(freq)
        e_min = hz_to_erb(20.0)
        e_max = hz_to_erb(20000.0)
        band_idx = int((erb_val - e_min) / (e_max - e_min) * num_bands)
        if 0 <= band_idx < num_bands:
            energies[band_idx] += mag * mag
    return energies


@pytest.mark.parametrize("seed", range(30))
def test_vectorized_matches_original_loop(seed: int) -> None:
    rng = np.random.default_rng(seed)
    sample_rate = int(rng.choice([44100, 48000]))
    fft_size = int(rng.choice([1024, 2048, 4096, 8192]))
    n_bins = fft_size // 2
    magnitudes = rng.uniform(0.0, 5.0, n_bins).tolist()
    num_bands = int(rng.choice([20, 40, 60]))

    original = _compute_erb_profile_original(magnitudes, sample_rate, fft_size, num_bands)
    vectorized = compute_erb_profile(magnitudes, sample_rate, fft_size, num_bands)

    assert len(original) == len(vectorized)
    assert max(abs(a - b) for a, b in zip(original, vectorized)) == 0.0


@pytest.mark.parametrize("magnitudes,sample_rate,fft_size,num_bands", [
    ([], 44100, 4096, 40),
    ([1.0], 44100, 4096, 40),
    ([0.0] * 100, 44100, 4096, 40),
    ([1.0] * 10, 0, 4096, 40),        # sample_rate <= 0
    ([1.0] * 10, 44100, 0, 40),       # fft_size <= 0
    ([1.0] * 5, 8, 4096, 40),         # very low sample rate
    ([1.0] * 2049, 44100, 4096, 1),   # single band
    ([1.0] * 2049, 44100, 4096, 200), # many bands
])
def test_vectorized_matches_original_loop_edge_cases(magnitudes, sample_rate, fft_size, num_bands) -> None:
    original = _compute_erb_profile_original(magnitudes, sample_rate, fft_size, num_bands)
    vectorized = compute_erb_profile(magnitudes, sample_rate, fft_size, num_bands)
    assert len(original) == len(vectorized)
    if original:
        assert max(abs(a - b) for a, b in zip(original, vectorized)) == 0.0
