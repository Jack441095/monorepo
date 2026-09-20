"""detect_transient_onsets' spectral-flux stage was rewritten from a
per-frame Python loop (one np.fft.rfft call per frame, one np.sum call per
frame-pair for flux) to a batched numpy form: stack all frames via
sliding_window_view, one rfft(..., axis=1) call for every frame's spectrum,
and one vectorized diff+sum for flux. Measured 141,411 individual rfft calls
for one real render (~38% of this function's cost).

Must stay bit-identical to the original per-frame loop, since onset
detection feeds transient_density (a classification feature) and sidechain
trigger detection -- verified here against a preserved copy of the original
implementation.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_analysis.analysis_core.transient_groove import _as_mono, detect_transient_onsets


def _detect_transient_onsets_original(
    samples, sample_rate, frame_size: int = 1024, hop_size: int = 256, minimum_spacing_ms: float = 80.0
):
    """The original per-frame Python loop, preserved as the reference
    implementation for regression testing against the batched version."""
    signal = _as_mono(samples)
    if sample_rate <= 0 or len(signal) < frame_size * 2:
        return []
    window = np.hanning(frame_size)
    spectra = []
    for start in range(0, len(signal) - frame_size + 1, hop_size):
        magnitude = np.abs(np.fft.rfft(signal[start: start + frame_size] * window))
        magnitude /= max(float(np.sum(magnitude)), 1e-12)
        spectra.append(magnitude)
    if len(spectra) < 3:
        return []
    flux = np.zeros(len(spectra), dtype=np.float64)
    for index in range(1, len(spectra)):
        flux[index] = float(np.sum(np.maximum(spectra[index] - spectra[index - 1], 0.0)))

    threshold = np.zeros_like(flux)
    radius = 8
    for index in range(len(flux)):
        local = flux[max(0, index - radius): min(len(flux), index + radius + 1)]
        median = float(np.median(local))
        mad = float(np.median(np.abs(local - median)))
        threshold[index] = median + max(0.015, 3.0 * mad)

    minimum_frames = max(1, int(round(minimum_spacing_ms * sample_rate / (1000.0 * hop_size))))
    candidates = [
        index for index in range(1, len(flux) - 1)
        if flux[index] > threshold[index] and flux[index] >= flux[index - 1] and flux[index] >= flux[index + 1]
    ]
    selected: list[int] = []
    for index in candidates:
        if selected and index - selected[-1] < minimum_frames:
            if flux[index] > flux[selected[-1]]:
                selected[-1] = index
            continue
        selected.append(index)
    return [
        {
            "sample": int(index * hop_size),
            "time_seconds": round(index * hop_size / sample_rate, 6),
            "strength": round(float(flux[index]), 6),
            "threshold": round(float(threshold[index]), 6),
        }
        for index in selected
    ]


@pytest.mark.parametrize("seed", range(30))
def test_batched_matches_original_per_frame_loop(seed: int) -> None:
    rng = np.random.default_rng(seed)
    sr = int(rng.choice([44100, 48000]))
    n = int(rng.integers(3000, 100_000))
    signal = (rng.standard_normal(n) * rng.uniform(0.05, 0.9)).astype(np.float64)
    assert _detect_transient_onsets_original(signal, sr) == detect_transient_onsets(signal, sr)


@pytest.mark.parametrize("n,sr", [
    (0, 44100),
    (100, 44100),        # shorter than frame_size*2
    (2048, 44100),       # exactly frame_size*2
    (2049, 44100),       # one sample over the minimum
    (10000, 0),          # invalid sample rate
])
def test_batched_matches_original_edge_cases(n: int, sr: int) -> None:
    rng = np.random.default_rng(0)
    signal = (rng.standard_normal(n) * 0.3).astype(np.float64) if n else np.zeros(0)
    assert _detect_transient_onsets_original(signal, sr) == detect_transient_onsets(signal, sr)
