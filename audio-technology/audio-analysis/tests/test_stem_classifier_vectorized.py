"""_crest_factor_db, _transient_density, and classify_stem's own peak/RMS
computation (stem_classifier.py) were rewritten from pure-Python
max()/sum()-over-generator-expression loops to vectorized numpy. Profiling
classify_stems (measured 2026-07-30) found these full-signal Python loops
were a real, previously-unexamined cost, running once per stem on every
render.

_crest_factor_db and the inline peak/RMS computation are NOT bit-exact
against the original (numpy's pairwise summation vs Python's sequential
sum() differ at the ~1e-14 dB level) -- verified negligible here (both
feed only coarse dB-range classification decisions, nowhere near a
few-dB-wide rule boundary). _transient_density and _detect_dc_offset are
exact.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from audio_analysis.mixdown.stem_classifier import (
    _crest_factor_db,
    _detect_dc_offset,
    _transient_density,
)


def _crest_factor_db_original(samples: list[float]) -> float:
    if not samples:
        return 0.0
    peak = max(abs(s) for s in samples)
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    if rms < 1e-12:
        return 0.0
    return 20.0 * math.log10(max(peak / rms, 1e-12))


def _detect_dc_offset_original(samples: list[float], threshold: float = 0.005) -> bool:
    if not samples:
        return False
    mean = sum(samples) / len(samples)
    return abs(mean) > threshold


def _transient_density_original(
    samples: list[float], sample_rate: int, window_ms: float = 10.0, threshold_db: float = 6.0
) -> float:
    if not samples or sample_rate <= 0:
        return 0.0
    window_size = max(64, int(sample_rate * window_ms / 1000.0))
    hop = window_size // 2
    if len(samples) < window_size * 2:
        return 0.0
    energies: list[float] = []
    for start in range(0, len(samples) - window_size + 1, hop):
        chunk = samples[start: start + window_size]
        energy = sum(s * s for s in chunk) / window_size
        energies.append(energy)
    if len(energies) < 3:
        return 0.0
    threshold_ratio = 10.0 ** (threshold_db / 10.0)
    onset_count = 0
    for i in range(1, len(energies)):
        if energies[i - 1] > 1e-12:
            if energies[i] / energies[i - 1] > threshold_ratio:
                onset_count += 1
        elif energies[i] > 1e-9:
            onset_count += 1
    duration = len(samples) / sample_rate
    return onset_count / max(duration, 0.01)


@pytest.mark.parametrize("seed", range(20))
def test_crest_factor_db_matches_original_within_float_noise(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n = int(rng.integers(1, 200_000))
    samples = (rng.standard_normal(n) * rng.uniform(0.01, 1.0)).tolist()
    original = _crest_factor_db_original(samples)
    vectorized = _crest_factor_db(samples)
    # Coarse dB-range classification rules are the only consumer -- 1e-9 dB
    # is many orders of magnitude below the narrowest rule width (a few dB).
    assert abs(original - vectorized) < 1e-9


@pytest.mark.parametrize("samples", [[], [0.5], [0.0] * 100, [1.0, -1.0, 1.0, -1.0]])
def test_crest_factor_db_edge_cases(samples: list[float]) -> None:
    original = _crest_factor_db_original(samples)
    vectorized = _crest_factor_db(samples)
    assert abs(original - vectorized) < 1e-9


@pytest.mark.parametrize("seed", range(15))
def test_detect_dc_offset_matches_original(seed: int) -> None:
    rng = np.random.default_rng(seed + 100)
    n = int(rng.integers(1, 50_000))
    offset = float(rng.uniform(-0.02, 0.02))
    samples = (rng.standard_normal(n) * 0.1 + offset).tolist()
    assert _detect_dc_offset_original(samples) == _detect_dc_offset(samples)


@pytest.mark.parametrize("seed", range(15))
def test_transient_density_matches_original(seed: int) -> None:
    rng = np.random.default_rng(seed + 200)
    sr = int(rng.choice([44100, 48000]))
    n = int(rng.integers(1000, 200_000))
    samples = (rng.standard_normal(n) * rng.uniform(0.05, 0.5)).tolist()
    # occasionally inject sharp transients to exercise the onset-counting path
    if rng.random() < 0.5 and n > 1000:
        idx = int(rng.integers(0, n - 500))
        samples[idx:idx + 50] = (rng.standard_normal(50) * 2.0).tolist()
    original = _transient_density_original(samples, sr)
    vectorized = _transient_density(samples, sr)
    assert original == vectorized


@pytest.mark.parametrize("samples,sr", [
    ([], 44100),
    ([0.1] * 10, 44100),      # shorter than one window
    ([0.0] * 100_000, 44100), # silence
    ([0.1] * 1000, 0),        # invalid sample rate
])
def test_transient_density_edge_cases(samples: list[float], sr: int) -> None:
    original = _transient_density_original(samples, sr)
    vectorized = _transient_density(samples, sr)
    assert original == vectorized
